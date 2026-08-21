/**
 * The sliver of `window.Telegram.WebApp` we read directly.
 *
 * Only `colorScheme` — SPEC §10 forbids consuming individual `themeParams`.
 */
declare global {
  interface Window {
    Telegram?: {
      WebApp?: {
        colorScheme?: 'light' | 'dark';
      };
    };
  }
}

export {};
