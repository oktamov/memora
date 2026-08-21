import { useEffect } from 'react';
import { useSearchParams } from 'react-router-dom';

import { LanguagePair } from '@/features/lookup/components/LanguagePair';
import { LookupInput } from '@/features/lookup/components/LookupInput';
import { TranslationCard } from '@/features/lookup/components/TranslationCard';
import { useTranslate } from '@/features/lookup/hooks';
import { useLanguagePair } from '@/features/lookup/useLanguagePair';
import { messageFor } from '@/shared/lib/errorMessages';
import { hapticRating } from '@/shared/telegram/haptics';
import { EmptyState } from '@/shared/ui/EmptyState';
import { ErrorState } from '@/shared/ui/ErrorState';
import { Spinner } from '@/shared/ui/Spinner';
import { useToast } from '@/shared/ui/toastContext';

/**
 * The app's main screen.
 *
 * Type a word, read every translation on one line, and it is already in today's deck.
 * There is deliberately nothing else to do: no meanings to tick, no deck to pick, no
 * save button. That friction is what this app exists to remove.
 */
export function LookupPage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const initialTerm = searchParams.get('q') ?? '';

  const translate = useTranslate();
  const { source, target, change, loading } = useLanguagePair();
  const toast = useToast();

  const run = (term: string) => {
    setSearchParams({ q: term }, { replace: true });
    translate.mutate(
      { term, source_lang: source, target_lang: target },
      {
        onSuccess: (result) => {
          hapticRating('success');
          toast(result.already_saved ? 'To‘plamda bor' : 'Saqlandi');
        },
        onError: (error) => toast(messageFor(error), 'error'),
      },
    );
  };

  // Run the term handed over from the Decks screen, once.
  useEffect(() => {
    if (initialTerm && !loading && !translate.data && !translate.isPending) {
      run(initialTerm);
    }
    // Keyed on the term and the pair alone: re-running on every render would fire a
    // paid API call per render, which SPEC §13 calls out by name.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [initialTerm, loading]);

  return (
    <div className="space-y-4">
      <LanguagePair
        source={source}
        target={target}
        disabled={loading}
        onChange={change}
      />

      <LookupInput
        onSubmit={run}
        autoFocus={!initialTerm}
        busy={translate.isPending}
        defaultValue={initialTerm}
      />

      {translate.isPending ? (
        <div className="flex justify-center py-10">
          <Spinner />
        </div>
      ) : null}

      {translate.isError ? (
        <ErrorState error={translate.error} onRetry={() => run(initialTerm)} />
      ) : null}

      {translate.data && !translate.isPending ? (
        <TranslationCard result={translate.data} />
      ) : null}

      {!translate.data && !translate.isPending && !translate.isError ? (
        <EmptyState
          title="So‘zni yozing"
          hint="Tarjimasini olasiz va so‘z bugungi lug‘atingizga o‘zi tushadi — boshqa hech narsa qilishingiz shart emas."
        />
      ) : null}
    </div>
  );
}
