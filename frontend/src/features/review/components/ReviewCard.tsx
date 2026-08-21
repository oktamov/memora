/**
 * One card, flipped (SPEC §10).
 *
 * The term is set large with tight tracking; definitions are noticeably smaller and
 * lighter. That gap is what makes the card scannable in under a second.
 *
 * The flip is the single orchestrated motion in the app, and it cross-fades instead of
 * rotating when the user prefers reduced motion.
 */
import { cn } from '@/shared/lib/cn';
import type { Card } from '@/shared/api/types';

export function ReviewCard({
  card,
  revealed,
  onReveal,
}: {
  card: Card;
  revealed: boolean;
  onReveal: () => void;
}) {
  return (
    <button
      type="button"
      onClick={revealed ? undefined : onReveal}
      aria-label={revealed ? card.display_term : `${card.display_term} — ma’nosini ko‘rish`}
      className={cn(
        'flip-scene w-full text-left',
        revealed ? 'cursor-default' : 'cursor-pointer',
      )}
    >
      <div className={cn('flip-inner', revealed && 'is-flipped')}>
        {/* Front: the word alone. */}
        <div className="flip-face">
          <div className="flex min-h-[46vh] flex-col items-center justify-center px-6 text-center">
            <h1 className="font-display text-term-lg font-bold text-paper">{card.display_term}</h1>
            {card.ipa ? (
              <p className="mt-3 font-mono text-base text-paper/45">{card.ipa}</p>
            ) : null}
            <p className="mt-10 font-mono text-[0.68rem] uppercase tracking-[0.2em] text-paper/25">
              ko‘rish uchun bosing
            </p>
          </div>
        </div>

        {/* Back: the meanings. */}
        <div className="flip-face flip-back">
          <div className="flex min-h-[46vh] flex-col justify-center px-1 py-4">
            <h2 className="font-display text-3xl font-bold leading-none text-paper">
              {card.display_term}
            </h2>
            {card.ipa ? (
              <p className="mt-1.5 font-mono text-sm text-paper/40">{card.ipa}</p>
            ) : null}

            <ul className="mt-6 space-y-4">
              {card.meanings.map((meaning, index) => (
                <li key={`${meaning.definition}-${index}`}>
                  {meaning.pos ? (
                    <span className="mb-1 block font-mono text-[0.62rem] uppercase tracking-[0.18em] text-paper/30">
                      {meaning.pos}
                    </span>
                  ) : null}
                  <p className="text-[1.15rem] font-light leading-snug text-paper/90">
                    {meaning.definition}
                  </p>
                  {meaning.gloss_en && meaning.gloss_en !== meaning.definition ? (
                    <p className="mt-1 text-sm font-light leading-snug text-paper/40">
                      {meaning.gloss_en}
                    </p>
                  ) : null}
                </li>
              ))}
            </ul>

            {card.examples.length > 0 ? (
              <figure className="mt-7 border-l-2 border-saffron/45 pl-4">
                <blockquote className="text-[0.95rem] font-light italic leading-relaxed text-paper/65">
                  {card.examples[0]?.text}
                </blockquote>
                {card.examples[0]?.translation ? (
                  <figcaption className="mt-1.5 text-sm font-light text-paper/35">
                    {card.examples[0].translation}
                  </figcaption>
                ) : null}
              </figure>
            ) : null}

            {card.note ? (
              <p className="mt-5 font-mono text-xs leading-relaxed text-paper/35">{card.note}</p>
            ) : null}
          </div>
        </div>
      </div>
    </button>
  );
}
