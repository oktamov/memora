/**
 * A last resort.
 *
 * There is no browser chrome inside a Mini App — a crashed render leaves the user
 * staring at a blank webview with no way to reload. This gives them one.
 */
import { Component } from 'react';
import type { ErrorInfo, ReactNode } from 'react';

import { Button } from '@/shared/ui/Button';

type Props = { children: ReactNode };
type State = { failed: boolean };

export class ErrorBoundary extends Component<Props, State> {
  state: State = { failed: false };

  static getDerivedStateFromError(): State {
    return { failed: true };
  }

  componentDidCatch(error: Error, info: ErrorInfo): void {
    console.error('Memora render error', error, info.componentStack);
  }

  render(): ReactNode {
    if (!this.state.failed) {
      return this.props.children;
    }

    return (
      <div className="mx-auto flex min-h-full max-w-md flex-col items-center justify-center gap-5 px-6 py-16 text-center">
        <div>
          <h1 className="font-display text-2xl font-bold text-body">Nimadir noto‘g‘ri ketdi</h1>
          <p className="mt-2 text-[0.95rem] leading-relaxed text-muted">
            Ilovani qayta yuklang. Saqlangan so‘zlaringiz joyida.
          </p>
        </div>
        <Button onClick={() => window.location.reload()}>Qayta yuklash</Button>
      </div>
    );
  }
}
