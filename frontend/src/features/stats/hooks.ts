import { useQuery } from '@tanstack/react-query';

import { api } from '@/shared/api/endpoints';
import { queryKeys } from '@/shared/api/queryKeys';

export function useStats() {
  return useQuery({ queryKey: queryKeys.stats, queryFn: api.stats });
}
