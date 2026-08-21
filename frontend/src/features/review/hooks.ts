import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import { api } from '@/shared/api/endpoints';
import { queryKeys } from '@/shared/api/queryKeys';

export function useReviewQueue(deckId: string | null, enabled = true) {
  return useQuery({
    queryKey: queryKeys.reviewQueue(deckId),
    queryFn: () => api.reviewQueue({ deckId }),
    enabled,
    // The session is taken once and driven from the store; refetching mid-session
    // would swap the cards out from under the user.
    staleTime: Infinity,
    refetchOnWindowFocus: false,
  });
}

export function useReviewCounts() {
  return useQuery({ queryKey: queryKeys.reviewCounts, queryFn: api.reviewCounts });
}

export function useInvalidateAfterSession() {
  const queryClient = useQueryClient();
  return () => {
    void queryClient.invalidateQueries({ queryKey: ['review'] });
    void queryClient.invalidateQueries({ queryKey: queryKeys.decks });
    void queryClient.invalidateQueries({ queryKey: queryKeys.stats });
  };
}

export const answerMutationKey = ['review', 'answer'] as const;

export function useAnswerReviews() {
  return useMutation({ mutationKey: answerMutationKey, mutationFn: api.answerReviews });
}
