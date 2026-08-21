/**
 * Haptics (SPEC §10).
 *
 * "The cheapest quality signal available in a Mini App." Every call is guarded, so a
 * client without haptics support degrades to silence rather than an exception.
 */
import {
  hapticFeedbackImpactOccurred,
  hapticFeedbackNotificationOccurred,
  hapticFeedbackSelectionChanged,
  isHapticFeedbackSupported,
} from '@telegram-apps/sdk-react';

function supported(): boolean {
  try {
    return isHapticFeedbackSupported();
  } catch {
    return false;
  }
}

/** Fired on card flip. */
export function hapticFlip(): void {
  if (!supported()) return;
  try {
    hapticFeedbackImpactOccurred('light');
  } catch {
    /* unsupported client */
  }
}

/** Fired on rating. */
export function hapticRating(kind: 'success' | 'warning' | 'error' = 'success'): void {
  if (!supported()) return;
  try {
    hapticFeedbackNotificationOccurred(kind);
  } catch {
    /* unsupported client */
  }
}

/** Fired when a meaning chip is toggled. */
export function hapticSelect(): void {
  if (!supported()) return;
  try {
    hapticFeedbackSelectionChanged();
  } catch {
    /* unsupported client */
  }
}
