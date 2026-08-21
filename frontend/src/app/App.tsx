import { ErrorBoundary } from '@/app/ErrorBoundary';
import { AppProviders } from '@/app/providers';
import { AppRouter } from '@/app/router';

export function App() {
  return (
    <ErrorBoundary>
      <AppProviders>
        <AppRouter />
      </AppProviders>
    </ErrorBoundary>
  );
}
