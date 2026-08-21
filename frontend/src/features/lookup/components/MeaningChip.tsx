import { Check } from 'lucide-react';

import { cn } from '@/shared/lib/cn';
import type { Meaning } from '@/shared/api/types';

/** A selectable meaning. The user keeps the ones worth keeping (SPEC §10). */
export function MeaningChip({
  meaning,
  selected,
  onToggle,
}: {
  meaning: Meaning;
  selected: boolean;
  onToggle: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onToggle}
      aria-pressed={selected}
      className={cn(
        'focus-ring flex w-full items-start gap-3 rounded-card border px-4 py-3 text-left transition-colors',
        selected
          ? 'border-indigo bg-indigo/[0.07]'
          : 'border-line bg-surface hover:border-line hover:bg-raised',
      )}
    >
      <span
        aria-hidden
        className={cn(
          'mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center rounded-md border transition-colors',
          selected ? 'border-indigo bg-indigo text-white' : 'border-line',
        )}
      >
        {selected ? <Check className="h-3.5 w-3.5" strokeWidth={3} /> : null}
      </span>

      <span className="min-w-0">
        {meaning.pos ? (
          <span className="mb-0.5 block font-mono text-[0.65rem] uppercase tracking-widest text-faint">
            {meaning.pos}
          </span>
        ) : null}
        <span className="block text-[1.05rem] leading-snug text-body">{meaning.definition}</span>
        {meaning.gloss_en && meaning.gloss_en !== meaning.definition ? (
          <span className="mt-1 block text-sm leading-snug text-faint">{meaning.gloss_en}</span>
        ) : null}
      </span>
    </button>
  );
}
