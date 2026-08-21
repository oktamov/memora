/**
 * A single-slot toast.
 *
 * SPEC §10 copy rule: action names stay constant through the flow — the button says
 * "Saqlash", the toast says "Saqlandi".
 */
import { useCallback, useMemo, useRef, useState } from 'react';
import type { ReactNode } from 'react';

import { cn } from '@/shared/lib/cn';
import { ToastContext } from '@/shared/ui/toastContext';
import type { ToastTone } from '@/shared/ui/toastContext';

type Toast = { message: string; tone: ToastTone };

export function ToastProvider({ children }: { children: ReactNode }) {
  const [toast, setToast] = useState<Toast | null>(null);
  const timer = useRef<number | undefined>(undefined);

  const show = useCallback((message: string, tone: ToastTone = 'ok') => {
    window.clearTimeout(timer.current);
    setToast({ message, tone });
    timer.current = window.setTimeout(() => setToast(null), 2600);
  }, []);

  const value = useMemo(() => show, [show]);

  return (
    <ToastContext.Provider value={value}>
      {children}
      <div
        aria-live="polite"
        className="pointer-events-none fixed inset-x-0 bottom-0 z-50 flex justify-center px-4"
        style={{ paddingBottom: 'calc(1.25rem + var(--safe-bottom))' }}
      >
        {toast ? (
          <div
            className={cn(
              'animate-fade-up rounded-full px-5 py-2.5 text-sm font-medium shadow-card',
              toast.tone === 'ok' ? 'bg-ink text-paper' : 'bg-madder text-white',
            )}
          >
            {toast.message}
          </div>
        ) : null}
      </div>
    </ToastContext.Provider>
  );
}
