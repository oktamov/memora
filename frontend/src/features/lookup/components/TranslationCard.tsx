import { Check } from 'lucide-react';

import type { TranslateResult } from '@/shared/api/types';

/**
 * The whole result: the word, every translation on one line, and where it went.
 *
 * There is nothing to select and nothing to confirm — the word is already saved by the
 * time this renders.
 */
export function TranslationCard({ result }: { result: TranslateResult }) {
  return (
    <article className="animate-fade-up rounded-card border border-line bg-surface px-5 py-5 shadow-card">
      <header className="flex items-baseline gap-3">
        <h2 className="font-display text-3xl font-bold leading-none tracking-tight text-body">
          {result.term}
        </h2>
        {result.ipa ? <span className="font-mono text-sm text-faint">{result.ipa}</span> : null}
      </header>

      <p className="mt-3 text-[1.35rem] font-light leading-snug text-body">
        {result.translation}
      </p>

      <footer className="mt-4 flex items-center gap-2 border-t border-line pt-3">
        <Check className="h-4 w-4 shrink-0 text-sage" strokeWidth={2.5} />
        <p className="text-sm text-muted">
          {result.already_saved ? (
            <>
              <span className="text-body">{result.deck_name}</span> to‘plamida bor
            </>
          ) : (
            <>
              Saqlandi → <span className="text-body">{result.deck_name}</span>
            </>
          )}
        </p>
      </footer>
    </article>
  );
}
