/**
 * Telegram Mini App SDK integration (SPEC §10).
 *
 * Everything here runs once, before React renders, so the app never flashes at half
 * height or with Telegram's loading placeholder still up.
 */
import {
  backButton,
  disableVerticalSwipes,
  expandViewport,
  init as initSdk,
  isTMA,
  mainButton,
  miniAppReady,
  mountBackButton,
  mountMainButton,
  mountMiniApp,
  mountSwipeBehavior,
  mountViewport,
  retrieveLaunchParams,
  viewportStableHeight,
} from '@telegram-apps/sdk-react';

export type ColorScheme = 'light' | 'dark';

export type LaunchContext = {
  /** Present only inside a real Telegram client. */
  initDataRaw: string | null;
  /** `?startapp=` value — `review` deep-links straight into a session. */
  startParam: string | null;
  colorScheme: ColorScheme;
  insideTelegram: boolean;
};

let launchContext: LaunchContext | null = null;

/** True when running inside a Telegram webview rather than a plain browser tab. */
export function insideTelegram(): boolean {
  try {
    return isTMA('simple');
  } catch {
    return false;
  }
}

/**
 * SPEC §10: read `colorScheme` only.
 *
 * Telegram's individual `themeParams` colours vary per client and would dissolve the
 * design into generic Telegram chrome, so they are deliberately never consumed.
 */
function detectColorScheme(): ColorScheme {
  const telegram = window.Telegram?.WebApp;
  if (telegram?.colorScheme) {
    return telegram.colorScheme;
  }
  return window.matchMedia?.('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
}

function applyColorScheme(scheme: ColorScheme): void {
  document.documentElement.dataset.mode = scheme;
}

/**
 * SPEC §10, §13: never `100vh`. In the Telegram webview it is wrong the moment the
 * keyboard opens, which on the lookup screen is always. `--app-height` drives every
 * full-height surface in the stylesheet instead.
 */
function bindViewportHeight(): void {
  const apply = (height: number | undefined) => {
    const value = height && height > 0 ? height : window.innerHeight;
    document.documentElement.style.setProperty('--app-height', `${value}px`);
  };

  apply(safeStableHeight());
  try {
    viewportStableHeight.sub(apply);
  } catch {
    // Viewport signal unavailable outside Telegram; the resize listener covers it.
  }
  window.addEventListener('resize', () => apply(safeStableHeight()));
}

function safeStableHeight(): number | undefined {
  try {
    return viewportStableHeight();
  } catch {
    return undefined;
  }
}

/**
 * Initialise the SDK. Called once, before `createRoot().render()`.
 *
 * Outside Telegram (a plain browser tab during development) every call is skipped and
 * the app still renders — but there is no initData, so the API will answer 401.
 */
export async function initTelegram(): Promise<LaunchContext> {
  if (launchContext) {
    return launchContext;
  }

  const scheme = detectColorScheme();
  applyColorScheme(scheme);
  window
    .matchMedia?.('(prefers-color-scheme: dark)')
    .addEventListener?.('change', () => applyColorScheme(detectColorScheme()));

  const inTelegram = insideTelegram();

  if (inTelegram) {
    safely(() => initSdk());

    // Dismiss Telegram's loading placeholder FIRST, before anything that can block.
    // If this waits behind the mounts and one of them never answers, the user is left
    // staring at Telegram's placeholder with the app invisible behind it.
    safely(() => miniAppReady());

    // Each mount asks Telegram a question and waits for the answer. A client that
    // never replies would otherwise hang boot forever, so every one is bounded.
    await Promise.all([
      tryMount(mountMiniApp),
      tryMount(mountViewport),
      tryMount(mountBackButton),
      tryMount(mountMainButton),
      tryMount(mountSwipeBehavior),
    ]);

    safely(() => miniAppReady());
    // Without this the app opens at half height.
    safely(() => expandViewport());
    // SPEC §13: without this a downward drag anywhere — including on a review card —
    // closes the Mini App, and the user loses the session mid-review.
    safely(() => disableVerticalSwipes());
  }

  bindViewportHeight();

  // Launch parameters are read regardless of the environment probe: `isTMA('simple')`
  // is deliberately conservative and answers false in clients that did launch us with
  // real parameters, so it decides only whether SDK *components* mount.
  const { initDataRaw, startParam } = readLaunchParams();

  launchContext = {
    initDataRaw,
    startParam,
    colorScheme: scheme,
    insideTelegram: inTelegram,
  };
  return launchContext;
}

/**
 * Read `initDataRaw` and `startParam`, preferring the SDK but never depending on it.
 *
 * `retrieveLaunchParams()` validates the *parsed* initData against a strict schema —
 * it currently requires a `signature` field, for instance — and throws the whole
 * result away if any single field is missing or new. That is the wrong trade for us:
 * the raw string is the only thing we send onward, and its authenticity is established
 * by the server's HMAC check (SPEC §7), not by a client-side shape check. A parser
 * that is one Telegram release behind would otherwise lock every user out.
 *
 * So: try the SDK, then fall back to reading `tgWebAppData` from where Telegram puts
 * it. The server rejects anything that does not verify, exactly as before.
 */
function readLaunchParams(): { initDataRaw: string | null; startParam: string | null } {
  try {
    const params = retrieveLaunchParams();
    if (params.initDataRaw) {
      return {
        initDataRaw: params.initDataRaw,
        startParam: params.startParam ?? null,
      };
    }
  } catch {
    // Strict parse failed — fall through to the raw source below.
  }

  for (const source of [window.location.hash.slice(1), rawSessionParams()]) {
    if (!source) continue;
    const params = new URLSearchParams(source);
    const data = params.get('tgWebAppData');
    if (data) {
      return { initDataRaw: data, startParam: params.get('tgWebAppStartParam') };
    }
  }

  return { initDataRaw: null, startParam: null };
}

/** Telegram's own launch parameters, as the SDK caches them for a reload. */
function rawSessionParams(): string | null {
  try {
    const stored = sessionStorage.getItem('__telegram__initParams');
    if (!stored) return null;

    const parsed: unknown = JSON.parse(stored);
    if (!parsed || typeof parsed !== 'object') return null;

    const entries = Object.entries(parsed as Record<string, unknown>)
      .filter((entry): entry is [string, string] => typeof entry[1] === 'string');
    return new URLSearchParams(entries).toString();
  } catch {
    return null;
  }
}

export function getLaunchContext(): LaunchContext {
  return (
    launchContext ?? {
      initDataRaw: null,
      startParam: null,
      colorScheme: 'light',
      insideTelegram: false,
    }
  );
}

/** How long any single SDK mount may take before boot stops waiting for it. */
const MOUNT_TIMEOUT_MS = 3_000;

async function tryMount(mount: () => unknown): Promise<void> {
  try {
    await Promise.race([
      Promise.resolve(mount()),
      new Promise<void>((resolve) => {
        window.setTimeout(resolve, MOUNT_TIMEOUT_MS);
      }),
    ]);
  } catch {
    // A component the current client does not support must not stop the app.
  }
}

function safely(action: () => unknown): void {
  try {
    action();
  } catch {
    // Same reasoning: unsupported is not fatal.
  }
}

export { backButton, mainButton };
