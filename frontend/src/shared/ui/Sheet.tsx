import { X } from 'lucide-react';
import { useEffect } from 'react';
import type { ReactNode } from 'react';

/** A bottom sheet. Dismissed with the ✕ or by tapping the scrim — never a back arrow. */
export function Sheet({
  open,
  title,
  onClose,
  children,
}: {
  open: boolean;
  title: string;
  onClose: () => void;
  children: ReactNode;
}) {
  useEffect(() => {
    if (!open) return;
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') onClose();
    };
    window.addEventListener('keydown', onKeyDown);
    return () => window.removeEventListener('keydown', onKeyDown);
  }, [open, onClose]);

  if (!open) return null;

  return (
    <div className="fixed inset-0 z-40 flex items-end justify-center">
      <button
        type="button"
        aria-label="Yopish"
        className="absolute inset-0 bg-ink/45 backdrop-blur-[2px]"
        onClick={onClose}
      />
      <div
        role="dialog"
        aria-modal="true"
        aria-label={title}
        className="animate-fade-up relative w-full max-w-lg rounded-t-3xl border border-line bg-surface p-5 shadow-card"
        style={{ paddingBottom: 'calc(1.5rem + var(--safe-bottom))' }}
      >
        <div className="mb-4 flex items-center justify-between">
          <h2 className="font-display text-lg font-semibold text-body">{title}</h2>
          <button
            type="button"
            aria-label="Yopish"
            onClick={onClose}
            className="focus-ring rounded-lg p-1.5 text-faint hover:bg-raised hover:text-body"
          >
            <X className="h-5 w-5" />
          </button>
        </div>
        {children}
      </div>
    </div>
  );
}
