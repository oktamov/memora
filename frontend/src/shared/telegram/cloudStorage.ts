/**
 * CloudStorage — trivial client preferences only (SPEC §10).
 *
 * The last deck the user saved into, and nothing else. Card data lives on the backend,
 * which is the source of truth; this is a convenience, and it falls back to
 * `localStorage` outside Telegram so development behaves the same.
 */
import {
  getCloudStorageItem,
  isCloudStorageSupported,
  setCloudStorageItem,
} from '@telegram-apps/sdk-react';

const LAST_DECK_KEY = 'memora:last_deck';

function usable(): boolean {
  try {
    return isCloudStorageSupported();
  } catch {
    return false;
  }
}

export async function readLastDeckId(): Promise<string | null> {
  if (!usable()) {
    return localStorage.getItem(LAST_DECK_KEY);
  }
  try {
    return (await getCloudStorageItem(LAST_DECK_KEY)) || null;
  } catch {
    return null;
  }
}

export async function writeLastDeckId(deckId: string): Promise<void> {
  if (!usable()) {
    localStorage.setItem(LAST_DECK_KEY, deckId);
    return;
  }
  try {
    await setCloudStorageItem(LAST_DECK_KEY, deckId);
  } catch {
    /* a failed preference write is not worth surfacing */
  }
}
