/** Every backend call, in one place. */
import { request } from './client';
import type {
  AnswerResult,
  Card,
  CardExample,
  CardMeaning,
  Deck,
  LookupResult,
  TranslateResult,
  Page,
  Rating,
  ReviewCountsOverview,
  ReviewQueue,
  StatsOverview,
  User,
} from './types';

export const api = {
  me: () => request<User>('/auth/me'),

  updateMe: (patch: Partial<Pick<User, 'source_lang' | 'native_lang' | 'daily_new_limit'
    | 'daily_review_limit' | 'timezone' | 'reminder_hour' | 'reminder_enabled'>>) =>
    request<User>('/auth/me', { method: 'PATCH', body: patch }),

  decks: () => request<Deck[]>('/decks'),

  deck: (deckId: string) => request<Deck>(`/decks/${deckId}`),

  dailyDeck: () => request<Deck>('/decks/daily'),

  createDeck: (body: { name: string; source_lang: string; target_lang: string }) =>
    request<Deck>('/decks', { method: 'POST', body }),

  updateDeck: (deckId: string, body: { name?: string; archived?: boolean }) =>
    request<Deck>(`/decks/${deckId}`, { method: 'PATCH', body }),

  deleteDeck: (deckId: string) => request<void>(`/decks/${deckId}`, { method: 'DELETE' }),

  /** Translate and file the word in one call — the app's main action. */
  translate: (body: { term: string; source_lang?: string; target_lang?: string }) =>
    request<TranslateResult>('/translate', { method: 'POST', body }),

  /** Translate without saving. The shape a public developer API takes. */
  lookup: (body: { term: string; source_lang?: string; target_lang?: string }) =>
    request<LookupResult>('/lookup', { method: 'POST', body }),

  createCard: (body: {
    deck_id?: string | null;
    term: string;
    ipa?: string | null;
    pos?: string | null;
    meanings: CardMeaning[];
    examples: CardExample[];
    note?: string | null;
  }) => request<Card>('/cards', { method: 'POST', body }),

  cards: (deckId: string, params: { cursor?: string | null; search?: string; limit?: number }) =>
    request<Page<Card>>(`/decks/${deckId}/cards`, {
      query: {
        cursor: params.cursor ?? undefined,
        search: params.search || undefined,
        limit: params.limit,
      },
    }),

  updateCard: (
    cardId: string,
    body: {
      deck_id?: string;
      meanings?: CardMeaning[];
      examples?: CardExample[];
      note?: string | null;
    },
  ) => request<Card>(`/cards/${cardId}`, { method: 'PATCH', body }),

  deleteCard: (cardId: string) => request<void>(`/cards/${cardId}`, { method: 'DELETE' }),

  suspendCard: (cardId: string, suspended?: boolean) =>
    request<{ suspended: boolean }>(`/cards/${cardId}/suspend`, {
      method: 'POST',
      body: { suspended },
    }),

  reviewQueue: (params: { deckId?: string | null; limit?: number }) =>
    request<ReviewQueue>('/review/queue', {
      query: { deck_id: params.deckId ?? undefined, limit: params.limit },
    }),

  answerReviews: (answers: { card_id: string; rating: Rating; reviewed_at: string }[]) =>
    request<{ results: AnswerResult[] }>('/review/answer', {
      method: 'POST',
      body: { answers },
    }),

  reviewCounts: () => request<ReviewCountsOverview>('/review/counts'),

  stats: () => request<StatsOverview>('/stats/overview'),
};
