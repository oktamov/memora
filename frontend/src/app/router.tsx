import { createBrowserRouter, RouterProvider } from 'react-router-dom';

import { AppLayout } from '@/app/layout/AppLayout';
import { DeckDetailPage } from '@/features/decks/pages/DeckDetailPage';
import { DecksPage } from '@/features/decks/pages/DecksPage';
import { LookupPage } from '@/features/lookup/pages/LookupPage';
import { ReviewPage } from '@/features/review/pages/ReviewPage';
import { StatsPage } from '@/features/stats/pages/StatsPage';

const router = createBrowserRouter([
  {
    path: '/',
    element: <AppLayout />,
    children: [
      { index: true, element: <DecksPage /> },
      { path: 'lookup', element: <LookupPage /> },
      { path: 'decks/:deckId', element: <DeckDetailPage /> },
      { path: 'stats', element: <StatsPage /> },
    ],
  },
  // Review sits outside the browsing layout on purpose: no nav, no chrome (SPEC §10).
  { path: '/review', element: <ReviewPage /> },
]);

export function AppRouter() {
  return <RouterProvider router={router} />;
}
