/**
 * The HTTP client.
 *
 * One session token in memory, silent re-authentication from initData on 401, and
 * every error surfaced as an `ApiError` carrying the backend's machine-readable code.
 */
import { getLaunchContext } from '@/shared/telegram/sdk';

import type { ApiErrorBody } from './types';

const BASE_URL = import.meta.env.VITE_API_BASE_URL ?? '/api/v1';

export class ApiError extends Error {
  readonly code: string;
  readonly status: number;
  readonly details: Record<string, unknown>;

  constructor(status: number, code: string, message: string, details: Record<string, unknown>) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
    this.code = code;
    this.details = details;
  }
}

let accessToken: string | null = null;
let refreshInFlight: Promise<string | null> | null = null;

export function getAccessToken(): string | null {
  return accessToken;
}

export function setAccessToken(token: string | null): void {
  accessToken = token;
}

/**
 * Exchange initData for a session JWT (SPEC §7).
 *
 * Concurrent callers share one in-flight request — on a cold start every screen's
 * query fires at once, and five parallel auth calls would trip the per-IP rate limit.
 */
export async function authenticate(): Promise<string | null> {
  if (refreshInFlight) {
    return refreshInFlight;
  }

  const { initDataRaw } = getLaunchContext();
  if (!initDataRaw) {
    return null;
  }

  refreshInFlight = (async () => {
    try {
      const response = await fetch(`${BASE_URL}/auth/telegram`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ init_data: initDataRaw }),
      });
      if (!response.ok) {
        throw await toApiError(response);
      }
      const body = (await response.json()) as { access_token: string };
      accessToken = body.access_token;
      return accessToken;
    } finally {
      refreshInFlight = null;
    }
  })();

  return refreshInFlight;
}

type RequestOptions = {
  method?: string;
  body?: unknown;
  query?: Record<string, string | number | boolean | undefined | null>;
  signal?: AbortSignal;
  /** Internal: prevents an infinite re-auth loop. */
  retryOnUnauthorized?: boolean;
};

export async function request<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const { method = 'GET', body, query, signal, retryOnUnauthorized = true } = options;

  if (!accessToken) {
    await authenticate();
  }

  const url = new URL(`${BASE_URL}${path}`, window.location.origin);
  for (const [key, value] of Object.entries(query ?? {})) {
    if (value !== undefined && value !== null && value !== '') {
      url.searchParams.set(key, String(value));
    }
  }

  const headers: Record<string, string> = {};
  if (body !== undefined) {
    headers['Content-Type'] = 'application/json';
  }
  if (accessToken) {
    headers.Authorization = `Bearer ${accessToken}`;
  }

  const response = await fetch(url.toString().replace(window.location.origin, ''), {
    method,
    headers,
    body: body === undefined ? undefined : JSON.stringify(body),
    signal,
  });

  // SPEC §7: the frontend re-calls /auth/telegram on 401.
  if (response.status === 401 && retryOnUnauthorized) {
    accessToken = null;
    const refreshed = await authenticate();
    if (refreshed) {
      return request<T>(path, { ...options, retryOnUnauthorized: false });
    }
  }

  if (!response.ok) {
    throw await toApiError(response);
  }

  if (response.status === 204) {
    return undefined as T;
  }
  return (await response.json()) as T;
}

async function toApiError(response: Response): Promise<ApiError> {
  let code = 'http_error';
  let message = 'Nimadir noto‘g‘ri ketdi.';
  let details: Record<string, unknown> = {};

  try {
    const body = (await response.json()) as Partial<ApiErrorBody>;
    if (body.error) {
      code = body.error.code ?? code;
      message = body.error.message ?? message;
      details = body.error.details ?? {};
    }
  } catch {
    // A non-JSON error body (a proxy timeout, say) keeps the defaults above.
  }

  return new ApiError(response.status, code, message, details);
}
