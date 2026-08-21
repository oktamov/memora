import type { ReactNode } from 'react';

/**
 * SPEC §10: empty states are invitations — they say what to do next, never
 * "Ma'lumot yo'q".
 */
export function EmptyState({
  title,
  hint,
  action,
}: {
  title: string;
  hint: string;
  action?: ReactNode;
}) {
  return (
    <div className="animate-fade-up rounded-card border border-dashed border-line bg-surface/60 px-6 py-10 text-center">
      <p className="font-display text-lg font-semibold text-body">{title}</p>
      <p className="mx-auto mt-2 max-w-xs text-[0.95rem] leading-relaxed text-muted">{hint}</p>
      {action ? <div className="mt-5 flex justify-center">{action}</div> : null}
    </div>
  );
}
