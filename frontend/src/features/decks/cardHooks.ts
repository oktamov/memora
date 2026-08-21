import { useInfiniteQuery, useMutation, useQueryClient } from '@tanstack/react-query';

import { api } from '@/shared/api/endpoints';
import { queryKeys } from '@/shared/api/queryKeys';
import type { CardExample, CardMeaning } from '@/shared/api/types';

export function useCards(deckId: string, search: string) {
  return useInfiniteQuery({
    queryKey: queryKeys.cards(deckId, search),
    queryFn: ({ pageParam }) => api.cards(deckId, { cursor: pageParam, search }),
    initialPageParam: null as string | null,
    getNextPageParam: (lastPage) => lastPage.next_cursor,
    enabled: Boolean(deckId),
  });
}

function useCardInvalidation(deckId: string) {
  const queryClient = useQueryClient();
  return () => {
    void queryClient.invalidateQueries({ queryKey: ['cards', deckId] });
    void queryClient.invalidateQueries({ queryKey: queryKeys.decks });
    void queryClient.invalidateQueries({ queryKey: queryKeys.reviewCounts });
  };
}

export function useUpdateCard(deckId: string) {
  const invalidate = useCardInvalidation(deckId);
  return useMutation({
    mutationFn: ({
      cardId,
      ...body
    }: {
      cardId: string;
      deck_id?: string;
      meanings?: CardMeaning[];
      examples?: CardExample[];
      note?: string | null;
    }) => api.updateCard(cardId, body),
    onSuccess: invalidate,
  });
}

export function useDeleteCard(deckId: string) {
  const invalidate = useCardInvalidation(deckId);
  return useMutation({ mutationFn: api.deleteCard, onSuccess: invalidate });
}

export function useSuspendCard(deckId: string) {
  const invalidate = useCardInvalidation(deckId);
  return useMutation({
    mutationFn: ({ cardId, suspended }: { cardId: string; suspended?: boolean }) =>
      api.suspendCard(cardId, suspended),
    onSuccess: invalidate,
  });
}
