import { cn } from '@/shared/lib/cn';
import { languagePair } from '@/shared/lib/format';
import type { Deck } from '@/shared/api/types';

export function DeckCard({ deck }: { deck: Deck }) {
  const isDaily = deck.kind === 'daily';

  return (
    <article
      className={cn(
        'rounded-card border bg-surface px-4 py-3.5 shadow-card transition-colors',
        isDaily ? 'border-saffron/45' : 'border-line',
      )}
    >
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="flex items-center gap-2">
            {isDaily ? (
              <span className="rounded-full bg-saffron/15 px-2 py-0.5 font-mono text-[0.65rem] uppercase tracking-widest text-saffron">
                bugun
              </span>
            ) : null}
            <h2 className="truncate font-display text-lg font-semibold text-body">{deck.name}</h2>
          </div>
          <p className="mt-1 font-mono text-xs tracking-wide text-faint">
            {languagePair(deck.source_lang, deck.target_lang)}
          </p>
        </div>

        <dl className="flex shrink-0 gap-4 text-right">
          <div>
            <dt className="font-mono text-[0.65rem] uppercase tracking-widest text-faint">karta</dt>
            <dd className="font-mono text-lg text-body">{deck.card_count}</dd>
          </div>
          <div>
            <dt className="font-mono text-[0.65rem] uppercase tracking-widest text-faint">navbat</dt>
            <dd
              className={cn(
                'font-mono text-lg',
                deck.due_count > 0 ? 'text-saffron' : 'text-faint',
              )}
            >
              {deck.due_count}
            </dd>
          </div>
        </dl>
      </div>
    </article>
  );
}
