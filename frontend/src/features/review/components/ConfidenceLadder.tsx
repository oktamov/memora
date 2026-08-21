/**
 * The signature element (SPEC §10).
 *
 * Not four equal buttons: one continuous track running madder → sage, with four stops
 * and the next-due interval printed under each. The user sees the consequence of the
 * answer before choosing it. Everything else on the review screen is silent, so all
 * the boldness is spent here.
 */
import { cn } from '@/shared/lib/cn';
import type { Rating } from '@/shared/api/types';

export type LadderStop = {
  rating: Rating;
  label: string;
  interval: string;
};

const STOPS: { rating: Rating; label: string; dot: string; text: string }[] = [
  { rating: 1, label: 'Yana', dot: 'bg-madder', text: 'text-madder' },
  { rating: 2, label: 'Qiyin', dot: 'bg-[#C9713C]', text: 'text-[#C9713C]' },
  { rating: 3, label: 'Yaxshi', dot: 'bg-saffron', text: 'text-saffron' },
  { rating: 4, label: 'Oson', dot: 'bg-sage', text: 'text-sage' },
];

export function ConfidenceLadder({
  intervals,
  onRate,
  disabled = false,
}: {
  intervals: Record<Rating, string>;
  onRate: (rating: Rating) => void;
  disabled?: boolean;
}) {
  return (
    <div className="w-full select-none">
      {/* The continuous track. */}
      <div
        aria-hidden
        className="mx-1 h-[3px] rounded-full"
        style={{
          background:
            'linear-gradient(90deg, #B4432E 0%, #C9713C 33%, #E0A32E 67%, #6E8B6B 100%)',
        }}
      />

      <div className="mt-0 grid grid-cols-4">
        {STOPS.map((stop) => (
          <button
            key={stop.rating}
            type="button"
            disabled={disabled}
            onClick={() => onRate(stop.rating)}
            aria-label={`${stop.label}, keyingi takror ${intervals[stop.rating]}`}
            className={cn(
              'group -mt-[7px] flex flex-col items-center gap-1.5 rounded-xl px-1 pb-2 pt-0',
              'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-paper/60',
              'disabled:opacity-40',
            )}
          >
            <span
              className={cn(
                'h-[11px] w-[11px] rounded-full ring-4 ring-ink transition-transform',
                'group-active:scale-125',
                stop.dot,
              )}
            />
            <span className={cn('text-[0.95rem] font-medium leading-none', stop.text)}>
              {stop.label}
            </span>
            <span className="font-mono text-[0.68rem] leading-none text-paper/40">
              {intervals[stop.rating]}
            </span>
          </button>
        ))}
      </div>
    </div>
  );
}
