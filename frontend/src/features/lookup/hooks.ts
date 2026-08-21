import { useMutation, useQueryClient } from '@tanstack/react-query';

import { api } from '@/shared/api/endpoints';
import { queryKeys } from '@/shared/api/queryKeys';
import type { CardExample, CardMeaning } from '@/shared/api/types';

/**
 * Lookup is a mutation, not a query, on purpose.
 *
 * SPEC §10, §13: no search-as-you-type. Every keystroke fired at a paid API is money
 * burned, so the call only ever happens on explicit submit.
 */
export function useLookup() {
  return useMutation({ mutationFn: api.lookup });
}

export function useSaveCard() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (body: {
      deck_id?: string | null;
      term: string;
      ipa?: string | null;
      pos?: string | null;
      meanings: CardMeaning[];
      examples: CardExample[];
      note?: string | null;
    }) => api.createCard(body),
    onSuccess: (card) => {
      void queryClient.invalidateQueries({ queryKey: queryKeys.decks });
      void queryClient.invalidateQueries({ queryKey: queryKeys.dailyDeck });
      void queryClient.invalidateQueries({ queryKey: ['cards', card.deck_id] });
      void queryClient.invalidateQueries({ queryKey: queryKeys.reviewCounts });
    },
  });
}
