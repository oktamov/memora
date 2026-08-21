import { useQuery } from '@tanstack/react-query';

import { api } from '@/shared/api/endpoints';
import { queryKeys } from '@/shared/api/queryKeys';

/** The current user. There is no login screen — this resolves on boot (SPEC §10). */
export function useMe() {
  return useQuery({ queryKey: queryKeys.me, queryFn: api.me, staleTime: 5 * 60_000 });
}
