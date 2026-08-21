import { Archive, Play, Trash2 } from 'lucide-react';
import { useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';

import { CardRow } from '@/features/decks/components/CardRow';
import { EditCardSheet } from '@/features/decks/components/EditCardSheet';
import { useCards } from '@/features/decks/cardHooks';
import { useDeck, useDeleteDeck, useUpdateDeck } from '@/features/decks/hooks';
import { useMainButton } from '@/shared/hooks/useMainButton';
import { languagePair } from '@/shared/lib/format';
import type { Card } from '@/shared/api/types';
import { Button } from '@/shared/ui/Button';
import { EmptyState } from '@/shared/ui/EmptyState';
import { messageFor } from '@/shared/lib/errorMessages';
import { ErrorState } from '@/shared/ui/ErrorState';
import { ScreenSpinner, Spinner } from '@/shared/ui/Spinner';
import { useToast } from '@/shared/ui/toastContext';

export function DeckDetailPage() {
  const { deckId = '' } = useParams();
  const navigate = useNavigate();
  const toast = useToast();

  const [search, setSearch] = useState('');
  const [editing, setEditing] = useState<Card | null>(null);

  const deck = useDeck(deckId);
  const cards = useCards(deckId, search);
  const updateDeck = useUpdateDeck(deckId);
  const deleteDeck = useDeleteDeck();

  const items = cards.data?.pages.flatMap((page) => page.items) ?? [];
  const dueCount = deck.data?.due_count ?? 0;

  // SPEC §10: MainButton is the one primary action — starting a session.
  useMainButton({
    text: 'Takrorlashni boshlash',
    visible: dueCount > 0,
    onClick: () => navigate(`/review?deck_id=${deckId}`),
  });

  if (deck.isPending) return <ScreenSpinner />;
  if (deck.isError) return <ErrorState error={deck.error} onRetry={() => void deck.refetch()} />;
  if (!deck.data) return null;

  const isDaily = deck.data.kind === 'daily';

  return (
    <div className="space-y-5">
      <header>
        <h1 className="font-display text-2xl font-bold text-body">{deck.data.name}</h1>
        <p className="mt-1 font-mono text-xs tracking-wide text-faint">
          {languagePair(deck.data.source_lang, deck.data.target_lang)} · {deck.data.card_count} karta
          {dueCount > 0 ? ` · ${dueCount} navbatda` : ''}
        </p>
      </header>

      {dueCount > 0 ? (
        <Button className="w-full" onClick={() => navigate(`/review?deck_id=${deckId}`)}>
          <Play className="h-4 w-4" />
          Takrorlashni boshlash
        </Button>
      ) : null}

      <input
        value={search}
        onChange={(event) => setSearch(event.target.value)}
        placeholder="To‘plam ichidan qidirish"
        aria-label="To‘plam ichidan qidirish"
        className="focus-ring h-11 w-full rounded-xl border border-line bg-surface px-3.5 text-body placeholder:text-faint"
      />

      {cards.isPending ? <ScreenSpinner /> : null}
      {cards.isError ? (
        <ErrorState error={cards.error} onRetry={() => void cards.refetch()} />
      ) : null}

      {cards.data && items.length === 0 ? (
        <EmptyState
          title={search ? 'Topilmadi' : 'To‘plam hali bo‘sh'}
          hint={
            search
              ? 'Boshqa so‘z bilan qidirib ko‘ring.'
              : 'Kitobda uchragan so‘zni qidiruvdan qo‘shing — u shu yerda paydo bo‘ladi.'
          }
          action={
            search ? null : (
              <Button variant="ghost" size="sm" onClick={() => navigate('/lookup')}>
                So‘z qidirish
              </Button>
            )
          }
        />
      ) : null}

      {items.length > 0 ? (
        <ul className="space-y-2">
          {items.map((card) => (
            <li key={card.id}>
              <CardRow card={card} onEdit={() => setEditing(card)} />
            </li>
          ))}
        </ul>
      ) : null}

      {cards.hasNextPage ? (
        <Button
          variant="quiet"
          size="sm"
          className="w-full"
          disabled={cards.isFetchingNextPage}
          onClick={() => void cards.fetchNextPage()}
        >
          {cards.isFetchingNextPage ? <Spinner className="h-4 w-4" /> : 'Yana yuklash'}
        </Button>
      ) : null}

      {!isDaily ? (
        <div className="flex gap-2 border-t border-line pt-5">
          <Button
            variant="quiet"
            size="sm"
            className="flex-1"
            onClick={() =>
              updateDeck.mutate(
                { archived: deck.data.archived_at === null },
                {
                  onSuccess: () =>
                    toast(deck.data.archived_at === null ? 'Arxivlandi' : 'Arxivdan chiqarildi'),
                  onError: (error) => toast(messageFor(error), 'error'),
                },
              )
            }
          >
            <Archive className="h-4 w-4" />
            {deck.data.archived_at === null ? 'Arxivlash' : 'Arxivdan chiqarish'}
          </Button>
          <Button
            variant="danger"
            size="sm"
            className="flex-1"
            onClick={() =>
              deleteDeck.mutate(deckId, {
                onSuccess: () => {
                  toast('O‘chirildi');
                  navigate('/');
                },
                onError: (error) => toast(messageFor(error), 'error'),
              })
            }
          >
            <Trash2 className="h-4 w-4" />
            O‘chirish
          </Button>
        </div>
      ) : null}

      <EditCardSheet card={editing} deckId={deckId} onClose={() => setEditing(null)} />
    </div>
  );
}
