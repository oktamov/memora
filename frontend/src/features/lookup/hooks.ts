import { useMutation, useQueryClient } from '@tanstack/react-query';

import { api } from '@/shared/api/endpoints';
import { queryKeys } from '@/shared/api/queryKeys';

/**
 * Translate and keep, in one call.
 *
 * A mutation rather than a query on purpose: SPEC §10 and §13 forbid
 * search-as-you-type, so this only ever runs on explicit submit. Every keystroke sent
 * to a paid API is money burned.
 */
export function useTranslate() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: api.translate,
    onSuccess: (result) => {
      // The word is already filed, so the deck list and review counts are stale.
      void queryClient.invalidateQueries({ queryKey: queryKeys.decks });
      void queryClient.invalidateQueries({ queryKey: ['cards', result.deck_id] });
      void queryClient.invalidateQueries({ queryKey: queryKeys.reviewCounts });
      void queryClient.invalidateQueries({ queryKey: queryKeys.stats });
    },
  });
}

export function useUpdateLanguages() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (pair: { source_lang: string; native_lang: string }) => api.updateMe(pair),
    onSuccess: (user) => queryClient.setQueryData(queryKeys.me, user),
  });
}
