/** Deck server state. All of it through TanStack Query (SPEC §10). */
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import { api } from '@/shared/api/endpoints';
import { queryKeys } from '@/shared/api/queryKeys';

export function useDecks() {
  return useQuery({ queryKey: queryKeys.decks, queryFn: api.decks });
}

export function useDeck(deckId: string) {
  return useQuery({
    queryKey: queryKeys.deck(deckId),
    queryFn: () => api.deck(deckId),
    enabled: Boolean(deckId),
  });
}

/** Creates today's daily deck on first call — this is what makes it lazy. */
export function useDailyDeck() {
  return useQuery({ queryKey: queryKeys.dailyDeck, queryFn: api.dailyDeck });
}

export function useCreateDeck() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: api.createDeck,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: queryKeys.decks }),
  });
}

export function useUpdateDeck(deckId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (body: { name?: string; archived?: boolean }) => api.updateDeck(deckId, body),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: queryKeys.decks });
      void queryClient.invalidateQueries({ queryKey: queryKeys.deck(deckId) });
    },
  });
}

export function useDeleteDeck() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: api.deleteDeck,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: queryKeys.decks }),
  });
}
