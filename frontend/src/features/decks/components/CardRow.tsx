import { Pencil } from 'lucide-react';

import { cn } from '@/shared/lib/cn';
import type { Card } from '@/shared/api/types';

export function CardRow({ card, onEdit }: { card: Card; onEdit: () => void }) {
  const suspended = card.state?.suspended ?? false;

  return (
    <div
      className={cn(
        'flex items-start gap-3 rounded-card border border-line bg-surface px-4 py-3',
        suspended && 'opacity-55',
      )}
    >
      <div className="min-w-0 flex-1">
        <div className="flex items-baseline gap-2">
          <h3 className="truncate font-display text-[1.05rem] font-semibold text-body">
            {card.display_term}
          </h3>
          {card.ipa ? <span className="font-mono text-xs text-faint">{card.ipa}</span> : null}
        </div>
        <p className="mt-0.5 truncate text-sm text-muted">
          {card.meanings.map((meaning) => meaning.definition).join(', ')}
        </p>
      </div>

      <button
        type="button"
        aria-label={`${card.display_term} kartasini tahrirlash`}
        onClick={onEdit}
        className="focus-ring shrink-0 rounded-lg p-2 text-faint hover:bg-raised hover:text-body"
      >
        <Pencil className="h-4 w-4" />
      </button>
    </div>
  );
}
