/**
 * Telegram's native BackButton, driven by the router (SPEC §10).
 *
 * The app never draws its own back arrow — this is the only back affordance.
 */
import { useEffect } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';

import { backButton } from '@/shared/telegram/sdk';

export function useNativeBackButton(): void {
  const location = useLocation();
  const navigate = useNavigate();

  useEffect(() => {
    const atRoot = location.pathname === '/';

    try {
      if (atRoot) {
        backButton.hide();
        return;
      }
      backButton.show();
    } catch {
      // Not inside Telegram, or the client does not support it.
      return;
    }

    const off = backButton.onClick(() => {
      navigate(-1);
    });

    return () => {
      off();
    };
  }, [location.pathname, navigate]);
}
