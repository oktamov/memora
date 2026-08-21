import { cn } from '@/shared/lib/cn';

export function StatTile({
  label,
  value,
  hint,
  accent = false,
}: {
  label: string;
  value: string;
  hint?: string;
  accent?: boolean;
}) {
  return (
    <div className="rounded-card border border-line bg-surface px-4 py-3.5">
      <p className="font-mono text-[0.62rem] uppercase tracking-[0.18em] text-faint">{label}</p>
      <p
        className={cn(
          'mt-1.5 font-display text-3xl font-bold leading-none',
          accent ? 'text-saffron' : 'text-body',
        )}
      >
        {value}
      </p>
      {hint ? <p className="mt-1.5 text-sm text-muted">{hint}</p> : null}
    </div>
  );
}
