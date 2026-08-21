/**
 * The in-flight review session, and nothing else (SPEC §10).
 *
 * Zustand holds only queue, index and pending answers. Everything durable lives on the
 * server and comes through TanStack Query.
 *
 * Flush policy (SPEC §10): every 5 answers, on session end, and on `visibilitychange`.
 * The UI never waits for a flush — rating advances to the next card immediately.
 */
import { create } from 'zustand';

import { api } from '@/shared/api/endpoints';
import type { QueueItem, Rating } from '@/shared/api/types';

export const FLUSH_EVERY = 5;

export type PendingAnswer = {
  card_id: string;
  rating: Rating;
  reviewed_at: string;
};

type SessionState = {
  deckId: string | null;
  queue: QueueItem[];
  index: number;
  revealed: boolean;
  pending: PendingAnswer[];
  answeredCount: number;
  ratings: Record<Rating, number>;
  flushing: boolean;
  finished: boolean;

  start: (queue: QueueItem[], deckId: string | null) => void;
  reveal: () => void;
  rate: (rating: Rating) => void;
  requeue: (item: QueueItem) => void;
  flush: () => Promise<void>;
  end: () => Promise<void>;
  reset: () => void;
};

const emptyRatings: Record<Rating, number> = { 1: 0, 2: 0, 3: 0, 4: 0 };

export const useReviewSession = create<SessionState>((set, get) => ({
  deckId: null,
  queue: [],
  index: 0,
  revealed: false,
  pending: [],
  answeredCount: 0,
  ratings: { ...emptyRatings },
  flushing: false,
  finished: false,

  start: (queue, deckId) =>
    set({
      queue,
      deckId,
      index: 0,
      revealed: false,
      pending: [],
      answeredCount: 0,
      ratings: { ...emptyRatings },
      finished: queue.length === 0,
    }),

  reveal: () => set({ revealed: true }),

  rate: (rating) => {
    const { queue, index, pending, answeredCount, ratings } = get();
    const current = queue[index];
    if (!current) return;

    const answer: PendingAnswer = {
      card_id: current.card.id,
      rating,
      reviewed_at: new Date().toISOString(),
    };

    // A card rated `again` comes back at the end of this session (SPEC §11 M4).
    const nextQueue = rating === 1 ? [...queue, current] : queue;
    const nextIndex = index + 1;

    set({
      queue: nextQueue,
      pending: [...pending, answer],
      answeredCount: answeredCount + 1,
      ratings: { ...ratings, [rating]: ratings[rating] + 1 },
      // Optimistic: advance immediately, never block on the network.
      index: nextIndex,
      revealed: false,
      finished: nextIndex >= nextQueue.length,
    });

    if ((answeredCount + 1) % FLUSH_EVERY === 0) {
      void get().flush();
    }
  },

  requeue: (item) => set((state) => ({ queue: [...state.queue, item] })),

  flush: async () => {
    const { pending, flushing } = get();
    if (flushing || pending.length === 0) {
      return;
    }

    set({ flushing: true, pending: [] });
    try {
      await api.answerReviews(pending);
    } catch {
      // Put them back so the next flush (or session end) retries. Losing answers
      // would corrupt both the schedule and the review log.
      set((state) => ({ pending: [...pending, ...state.pending] }));
    } finally {
      set({ flushing: false });
    }
  },

  end: async () => {
    await get().flush();
    set({ finished: true });
  },

  reset: () =>
    set({
      deckId: null,
      queue: [],
      index: 0,
      revealed: false,
      pending: [],
      answeredCount: 0,
      ratings: { ...emptyRatings },
      finished: false,
    }),
}));
