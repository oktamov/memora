import { useCallback } from 'react';

import { useMe } from '@/features/auth/hooks';
import { useUpdateLanguages } from '@/features/lookup/hooks';

/**
 * The user's language pair, read from the server and written straight back.
 *
 * Shared by every screen that offers the input, so the picker never disagrees with
 * itself and the bot always sees the same pair.
 */
export function useLanguagePair() {
  const me = useMe();
  const update = useUpdateLanguages();

  const source = me.data?.source_lang ?? 'en';
  const target = me.data?.native_lang ?? 'uz';

  const change = useCallback(
    (nextSource: string, nextTarget: string) => {
      update.mutate({ source_lang: nextSource, native_lang: nextTarget });
    },
    [update],
  );

  return { source, target, change, loading: me.isPending };
}
