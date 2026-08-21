import { Plus } from 'lucide-react';
import { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';

import { useDecks } from '@/features/decks/hooks';
import { CreateDeckSheet } from '@/features/decks/components/CreateDeckSheet';
import { DeckCard } from '@/features/decks/components/DeckCard';
import { LanguagePair } from '@/features/lookup/components/LanguagePair';
import { LookupInput } from '@/features/lookup/components/LookupInput';
import { useLanguagePair } from '@/features/lookup/useLanguagePair';
import { Button } from '@/shared/ui/Button';
import { EmptyState } from '@/shared/ui/EmptyState';
import { ErrorState } from '@/shared/ui/ErrorState';
import { ScreenSpinner } from '@/shared/ui/Spinner';

/**
 * The first screen a user ever sees — already authenticated, no onboarding wall
 * (SPEC §10). Today's daily deck is pinned at the top by the backend's ordering.
 */
export function DecksPage() {
  const navigate = useNavigate();
  const decks = useDecks();
  const pair = useLanguagePair();
  const [creating, setCreating] = useState(false);

  return (
    <div className="space-y-5">
      {/* The pair sits with the input, on every screen that offers one — a picker the
          user has to go looking for is a picker they will not find. */}
      <div className="space-y-3">
        <LanguagePair
          source={pair.source}
          target={pair.target}
          disabled={pair.loading}
          onChange={pair.change}
        />
        <LookupInput onSubmit={(term) => navigate(`/lookup?q=${encodeURIComponent(term)}`)} />
      </div>

      {decks.isPending ? <ScreenSpinner /> : null}
      {decks.isError ? <ErrorState error={decks.error} onRetry={() => void decks.refetch()} /> : null}

      {decks.data ? (
        decks.data.length === 0 ? (
          <EmptyState
            title="Hali to‘plam yo‘q"
            hint="Tepadagi maydonga so‘z yozing — tarjimasi chiqadi va u bugungi lug‘atingizga o‘zi tushadi."
            action={
              <Button variant="ghost" size="sm" onClick={() => setCreating(true)}>
                <Plus className="h-4 w-4" />
                To‘plam yaratish
              </Button>
            }
          />
        ) : (
          <>
            <ul className="space-y-3">
              {decks.data.map((deck) => (
                <li key={deck.id} className="animate-fade-up">
                  <Link to={`/decks/${deck.id}`} className="block focus-ring rounded-card">
                    <DeckCard deck={deck} />
                  </Link>
                </li>
              ))}
            </ul>

            <Button variant="quiet" size="sm" className="w-full" onClick={() => setCreating(true)}>
              <Plus className="h-4 w-4" />
              To‘plam yaratish
            </Button>
          </>
        )
      ) : null}

      <CreateDeckSheet open={creating} onClose={() => setCreating(false)} />
    </div>
  );
}
