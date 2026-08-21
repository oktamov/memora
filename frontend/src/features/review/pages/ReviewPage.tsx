/**
 * Review — the focus mode (SPEC §10).
 *
 * "A dark room with one lamp on": `--ink` ground in both themes, no nav, no chrome,
 * no progress bar competing for attention. Telegram's MainButton is deliberately not
 * used here — the rating ladder is the action.
 */
import { useCallback, useEffect, useMemo } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';

import { ConfidenceLadder } from '@/features/review/components/ConfidenceLadder';
import { ReviewCard } from '@/features/review/components/ReviewCard';
import { useInvalidateAfterSession, useReviewQueue } from '@/features/review/hooks';
import { useReviewSession } from '@/features/review/store';
import { formatInterval } from '@/shared/lib/format';
import { hapticFlip, hapticRating } from '@/shared/telegram/haptics';
import type { Rating } from '@/shared/api/types';
import { Button } from '@/shared/ui/Button';
import { ErrorState } from '@/shared/ui/ErrorState';
import { Spinner } from '@/shared/ui/Spinner';

/**
 * Interval estimates shown under each ladder stop.
 *
 * Deliberately client-side: the server would have to run FSRS four times per card to
 * answer exactly, and the point of the ladder is a sense of the consequence, not a
 * contract. The real interval comes back from `/review/answer`.
 */
function estimateIntervals(stability: number | null, reps: number): Record<Rating, string> {
  const now = new Date();
  const plus = (minutes: number) => formatInterval(now, new Date(now.getTime() + minutes * 60_000));

  if (reps === 0 || stability === null) {
    return { 1: plus(1), 2: plus(6), 3: plus(10), 4: plus(60 * 24 * 4) };
  }

  const day = 60 * 24;
  return {
    1: plus(10),
    2: plus(Math.max(stability * 0.6, 1) * day),
    3: plus(Math.max(stability * 1.4, 1) * day),
    4: plus(Math.max(stability * 2.6, 2) * day),
  };
}

export function ReviewPage() {
  const [searchParams] = useSearchParams();
  const deckId = searchParams.get('deck_id');
  const navigate = useNavigate();

  const queue = useReviewQueue(deckId);
  const invalidate = useInvalidateAfterSession();

  const session = useReviewSession();
  const { start, reveal, rate, flush, end, reset } = session;
  const current = session.queue[session.index];

  // Seed the session once the queue arrives.
  useEffect(() => {
    if (queue.data) {
      start(queue.data.items, deckId);
    }
  }, [queue.data, deckId, start]);

  useEffect(() => () => reset(), [reset]);

  // SPEC §10: flush on `visibilitychange` too — a backgrounded webview can be killed.
  useEffect(() => {
    const onHidden = () => {
      if (document.visibilityState === 'hidden') {
        void flush();
      }
    };
    document.addEventListener('visibilitychange', onHidden);
    return () => document.removeEventListener('visibilitychange', onHidden);
  }, [flush]);

  // ...and on session end.
  useEffect(() => {
    if (session.finished && session.pending.length > 0) {
      void end().then(invalidate);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [session.finished]);

  const onReveal = useCallback(() => {
    hapticFlip();
    reveal();
  }, [reveal]);

  const onRate = useCallback(
    (rating: Rating) => {
      hapticRating(rating === 1 ? 'warning' : 'success');
      rate(rating);
    },
    [rate],
  );

  const intervals = useMemo(
    () => estimateIntervals(current?.state.stability ?? null, current?.state.reps ?? 0),
    [current],
  );

  return (
    <div
      className="flex min-h-full flex-col bg-ink"
      style={{ minHeight: 'var(--app-height, 100%)' }}
    >
      <div className="mx-auto flex w-full max-w-lg flex-1 flex-col px-5 pb-6 pt-6">
        {queue.isPending ? (
          <Centered>
            <Spinner className="border-paper/20 border-t-saffron" />
          </Centered>
        ) : null}

        {queue.isError ? (
          <Centered>
            <div className="w-full">
              <ErrorState error={queue.error} onRetry={() => void queue.refetch()} />
            </div>
          </Centered>
        ) : null}

        {queue.data && !current ? (
          <Centered>
            <div className="text-center">
              <p className="font-display text-3xl font-bold text-paper">
                {session.answeredCount > 0 ? 'Tugadi' : 'Hozircha bo‘sh'}
              </p>
              <p className="mx-auto mt-3 max-w-xs text-[0.95rem] font-light leading-relaxed text-paper/50">
                {session.answeredCount > 0
                  ? `Bugun ${session.answeredCount} ta kartani takrorladingiz. Ertaga davom etamiz.`
                  : 'Takrorlash uchun karta yo‘q. Yangi so‘z qo‘shsangiz, u shu yerda paydo bo‘ladi.'}
              </p>
              <Button
                variant="ghost"
                className="mt-7 border-paper/15 bg-transparent text-paper hover:bg-paper/10"
                onClick={() => {
                  void end().then(invalidate);
                  navigate('/');
                }}
              >
                To‘plamlarga qaytish
              </Button>
            </div>
          </Centered>
        ) : null}

        {current ? (
          <>
            <div className="flex flex-1 items-center">
              <ReviewCard
                key={`${current.card.id}-${session.index}`}
                card={current.card}
                revealed={session.revealed}
                onReveal={onReveal}
              />
            </div>

            <div className="pt-6" style={{ paddingBottom: 'var(--safe-bottom)' }}>
              {session.revealed ? (
                <ConfidenceLadder intervals={intervals} onRate={onRate} />
              ) : (
                <div className="h-[74px]" aria-hidden />
              )}
            </div>
          </>
        ) : null}
      </div>
    </div>
  );
}

function Centered({ children }: { children: React.ReactNode }) {
  return <div className="flex flex-1 items-center justify-center px-4">{children}</div>;
}
