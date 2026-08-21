/**
 * Telegram's MainButton — one primary action per screen (SPEC §10).
 *
 * Deliberately unused in review: there, the rating ladder is the action.
 */
import { useEffect, useRef } from 'react';

import { mainButton } from '@/shared/telegram/sdk';

type Options = {
  text: string;
  visible: boolean;
  enabled?: boolean;
  loading?: boolean;
  onClick: () => void;
};

export function useMainButton({ text, visible, enabled = true, loading = false, onClick }: Options) {
  const handler = useRef(onClick);
  handler.current = onClick;

  useEffect(() => {
    try {
      mainButton.setParams({
        text,
        isVisible: visible,
        isEnabled: enabled,
        isLoaderVisible: loading,
        // Indigo is the primary (SPEC §10). Telegram's own button colour would be
        // whatever the client theme says, which is exactly what we are avoiding.
        backgroundColor: '#2E4374',
        textColor: '#FFFFFF',
      });
    } catch {
      return;
    }

    if (!visible) {
      return;
    }

    const off = mainButton.onClick(() => handler.current());
    return () => {
      off();
      try {
        mainButton.setParams({ isVisible: false });
      } catch {
        /* unmounting outside Telegram */
      }
    };
  }, [text, visible, enabled, loading]);
}
