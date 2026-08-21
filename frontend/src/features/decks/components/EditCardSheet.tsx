import { useEffect, useState } from 'react';

import { useDeleteCard, useSuspendCard, useUpdateCard } from '@/features/decks/cardHooks';
import { useDecks } from '@/features/decks/hooks';
import type { Card } from '@/shared/api/types';
import { Button } from '@/shared/ui/Button';
import { messageFor } from '@/shared/lib/errorMessages';
import { Sheet } from '@/shared/ui/Sheet';
import { TextArea } from '@/shared/ui/TextField';
import { useToast } from '@/shared/ui/toastContext';

/** Edit meanings and note, move the card, suspend it, or delete it (SPEC §7). */
export function EditCardSheet({
  card,
  deckId,
  onClose,
}: {
  card: Card | null;
  deckId: string;
  onClose: () => void;
}) {
  const toast = useToast();
  const decks = useDecks();
  const updateCard = useUpdateCard(deckId);
  const deleteCard = useDeleteCard(deckId);
  const suspendCard = useSuspendCard(deckId);

  const [note, setNote] = useState('');
  const [targetDeck, setTargetDeck] = useState('');

  useEffect(() => {
    setNote(card?.note ?? '');
    setTargetDeck(card?.deck_id ?? '');
  }, [card]);

  if (!card) return null;

  const save = () => {
    const body: { note: string | null; deck_id?: string } = { note: note.trim() || null };
    if (targetDeck && targetDeck !== card.deck_id) {
      body.deck_id = targetDeck;
    }

    updateCard.mutate(
      { cardId: card.id, ...body },
      {
        onSuccess: () => {
          toast('Saqlandi');
          onClose();
        },
        onError: (error) => toast(messageFor(error), 'error'),
      },
    );
  };

  const suspended = card.state?.suspended ?? false;

  return (
    <Sheet open title={card.display_term} onClose={onClose}>
      <div className="space-y-4">
        <p className="text-[1.05rem] leading-snug text-body">
          {card.meanings.map((meaning) => meaning.definition).join(', ')}
        </p>

        <TextArea
          label="Eslatma"
          value={note}
          maxLength={2000}
          placeholder="Masalan: Dune, 3-bob"
          onChange={(event) => setNote(event.target.value)}
        />

        <label className="block">
          <span className="mb-1.5 block text-sm font-medium text-muted">To‘plam</span>
          <select
            value={targetDeck}
            onChange={(event) => setTargetDeck(event.target.value)}
            className="focus-ring h-11 w-full rounded-xl border border-line bg-ground px-3 text-body"
          >
            {(decks.data ?? []).map((deck) => (
              <option key={deck.id} value={deck.id}>
                {deck.name}
              </option>
            ))}
          </select>
        </label>

        <Button className="w-full" disabled={updateCard.isPending} onClick={save}>
          {updateCard.isPending ? 'Saqlanmoqda…' : 'Saqlash'}
        </Button>

        <div className="flex gap-2">
          <Button
            variant="quiet"
            size="sm"
            className="flex-1"
            onClick={() =>
              suspendCard.mutate(
                { cardId: card.id },
                {
                  onSuccess: (state) => {
                    toast(state.suspended ? 'To‘xtatildi' : 'Qayta yoqildi');
                    onClose();
                  },
                  onError: (error) => toast(messageFor(error), 'error'),
                },
              )
            }
          >
            {suspended ? 'Qayta yoqish' : 'To‘xtatish'}
          </Button>
          <Button
            variant="danger"
            size="sm"
            className="flex-1"
            onClick={() =>
              deleteCard.mutate(card.id, {
                onSuccess: () => {
                  toast('O‘chirildi');
                  onClose();
                },
                onError: (error) => toast(messageFor(error), 'error'),
              })
            }
          >
            O‘chirish
          </Button>
        </div>
      </div>
    </Sheet>
  );
}
