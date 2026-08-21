import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';

import { App } from '@/app/App';
import { getLaunchContext, initTelegram } from '@/shared/telegram/sdk';
import '@/index.css';

const container = document.getElementById('root');
if (!container) {
  throw new Error('Root element #root is missing from index.html');
}

/**
 * SPEC §10: initialise the SDK *before* anything renders — otherwise the app flashes
 * at half height with Telegram's loading placeholder still up.
 */
async function bootstrap(): Promise<void> {
  await initTelegram();

  // SPEC §10: `?startapp=review` deep-links straight into a review session. The bot's
  // reminder button depends on this. Rewritten before the router reads the URL.
  const { startParam } = getLaunchContext();
  if (startParam === 'review' && window.location.pathname === '/') {
    window.history.replaceState(null, '', '/review');
  }

  createRoot(container!).render(
    <StrictMode>
      <App />
    </StrictMode>,
  );
}

void bootstrap();
