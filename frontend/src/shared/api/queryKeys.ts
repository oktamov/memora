/** Query keys, centralised so invalidation stays consistent. */
export const queryKeys = {
  me: ['me'] as const,
  decks: ['decks'] as const,
  deck: (deckId: string) => ['deck', deckId] as const,
  dailyDeck: ['deck', 'daily'] as const,
  cards: (deckId: string, search: string) => ['cards', deckId, search] as const,
  reviewQueue: (deckId: string | null) => ['review', 'queue', deckId] as const,
  reviewCounts: ['review', 'counts'] as const,
  stats: ['stats'] as const,
};
