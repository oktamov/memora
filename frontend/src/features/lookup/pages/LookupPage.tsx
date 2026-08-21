import { useEffect, useMemo, useState } from 'react';
import { useSearchParams } from 'react-router-dom';

import { useDecks } from '@/features/decks/hooks';
import { MeaningChip } from '@/features/lookup/components/MeaningChip';
import { LookupInput } from '@/features/lookup/components/LookupInput';
import { useLookup, useSaveCard } from '@/features/lookup/hooks';
import { useMe } from '@/features/auth/hooks';
import { useMainButton } from '@/shared/hooks/useMainButton';
import { readLastDeckId, writeLastDeckId } from '@/shared/telegram/cloudStorage';
import { hapticSelect } from '@/shared/telegram/haptics';
import type { CardExample, CardMeaning } from '@/shared/api/types';
import { Button } from '@/shared/ui/Button';
import { EmptyState } from '@/shared/ui/EmptyState';
import { messageFor } from '@/shared/lib/errorMessages';
import { ErrorState } from '@/shared/ui/ErrorState';
import { Spinner } from '@/shared/ui/Spinner';
import { TextArea } from '@/shared/ui/TextField';
import { useToast } from '@/shared/ui/toastContext';

/**
 * Lookup (SPEC §10).
 *
 * Type a word → result appears → each meaning is a selectable chip → keep the ones
 * worth having → optionally paste the sentence from the book → save.
 */
export function LookupPage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const initialTerm = searchParams.get('q') ?? '';

  const me = useMe();
  const decks = useDecks();
  const lookup = useLookup();
  const saveCard = useSaveCard();
  const toast = useToast();

  const [selected, setSelected] = useState<Set<number>>(new Set());
  const [sentence, setSentence] = useState('');
  const [deckId, setDeckId] = useState<string | null>(null);

  const targetLang = me.data?.native_lang ?? 'uz';
  const result = lookup.data;

  // Run the term handed over from the Decks screen, once.
  useEffect(() => {
    if (initialTerm && !lookup.data && !lookup.isPending) {
      lookup.mutate({ term: initialTerm, source_lang: 'en', target_lang: targetLang });
    }
    // Deliberately keyed on the term alone: re-running on every render would fire a
    // paid API call per keystroke, which SPEC §13 calls out by name.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [initialTerm, targetLang]);

  // CloudStorage holds the last deck used — a preference, never card data (SPEC §10).
  useEffect(() => {
    void readLastDeckId().then((stored) => {
      if (stored) setDeckId(stored);
    });
  }, []);

  const runLookup = (term: string) => {
    setSelected(new Set());
    setSentence('');
    setSearchParams({ q: term }, { replace: true });
    lookup.mutate({ term, source_lang: 'en', target_lang: targetLang });
  };

  const toggle = (index: number) => {
    hapticSelect();
    setSelected((previous) => {
      const next = new Set(previous);
      if (next.has(index)) {
        next.delete(index);
      } else {
        next.add(index);
      }
      return next;
    });
  };

  const meanings: CardMeaning[] = useMemo(() => {
    if (!result) return [];
    return [...selected]
      .sort((a, b) => a - b)
      .map((index) => result.meanings[index])
      .filter((meaning): meaning is NonNullable<typeof meaning> => Boolean(meaning))
      .map((meaning) => ({
        pos: meaning.pos,
        definition: meaning.definition,
        gloss_en: meaning.gloss_en,
      }));
  }, [result, selected]);

  const save = () => {
    if (!result || meanings.length === 0) return;

    const examples: CardExample[] = [];
    if (sentence.trim()) {
      // `user` — captured from the book the reader is holding (SPEC §5).
      examples.push({ text: sentence.trim(), translation: null, source: 'user' });
    }
    for (const meaning of result.meanings) {
      for (const example of meaning.examples.slice(0, 1)) {
        examples.push({ text: example, translation: null, source: 'provider' });
      }
    }

    saveCard.mutate(
      {
        deck_id: deckId,
        term: result.term,
        ipa: result.ipa,
        pos: meanings[0]?.pos ?? null,
        meanings,
        examples: examples.slice(0, 10),
      },
      {
        onSuccess: (card) => {
          // The button says "Saqlash", the toast says "Saqlandi" (SPEC §10).
          toast('Saqlandi');
          void writeLastDeckId(card.deck_id);
          setSelected(new Set());
          setSentence('');
        },
        onError: (error) => toast(messageFor(error), 'error'),
      },
    );
  };

  // SPEC §10: MainButton carries the single primary action of this screen.
  useMainButton({
    text: 'Saqlash',
    visible: Boolean(result) && meanings.length > 0,
    loading: saveCard.isPending,
    onClick: save,
  });

  return (
    <div className="space-y-5">
      <LookupInput
        onSubmit={runLookup}
        autoFocus={!initialTerm}
        busy={lookup.isPending}
        defaultValue={initialTerm}
      />

      {lookup.isPending ? (
        <div className="flex justify-center py-10">
          <Spinner />
        </div>
      ) : null}

      {lookup.isError ? (
        <ErrorState error={lookup.error} onRetry={() => runLookup(initialTerm)} />
      ) : null}

      {!result && !lookup.isPending && !lookup.isError ? (
        <EmptyState
          title="So‘zni yozing"
          hint="Kitobda uchragan notanish so‘zni kiriting — barcha ma’nolari, talaffuzi va misollari chiqadi."
        />
      ) : null}

      {result ? (
        <div className="animate-fade-up space-y-5">
          <header>
            <h1 className="font-display text-term font-bold text-body">{result.term}</h1>
            {result.ipa ? (
              <p className="mt-1 font-mono text-sm text-muted">{result.ipa}</p>
            ) : null}
            <p className="mt-2 font-mono text-[0.7rem] uppercase tracking-widest text-faint">
              {result.quota_used}/{result.quota_limit} · {result.cache === 'miss' ? 'yangi' : 'kesh'}
            </p>
          </header>

          <section className="space-y-2">
            <p className="text-sm font-medium text-muted">Saqlanadigan ma’nolarni tanlang</p>
            <ul className="space-y-2">
              {result.meanings.map((meaning, index) => (
                <li key={`${meaning.definition}-${index}`}>
                  <MeaningChip
                    meaning={meaning}
                    selected={selected.has(index)}
                    onToggle={() => toggle(index)}
                  />
                </li>
              ))}
            </ul>
          </section>

          <TextArea
            label="Kitobdagi jumla (ixtiyoriy)"
            value={sentence}
            maxLength={1000}
            placeholder="So‘z uchragan jumlani ko‘chiring — eslab qolish osonlashadi."
            onChange={(event) => setSentence(event.target.value)}
          />

          <DeckPicker
            decks={decks.data ?? []}
            value={deckId}
            onChange={setDeckId}
          />

          {/* A visible fallback for browsers without Telegram's MainButton. */}
          <Button
            className="w-full"
            disabled={meanings.length === 0 || saveCard.isPending}
            onClick={save}
          >
            {saveCard.isPending ? 'Saqlanmoqda…' : 'Saqlash'}
          </Button>
        </div>
      ) : null}
    </div>
  );
}

function DeckPicker({
  decks,
  value,
  onChange,
}: {
  decks: { id: string; name: string; kind: string }[];
  value: string | null;
  onChange: (value: string | null) => void;
}) {
  return (
    <label className="block">
      <span className="mb-1.5 block text-sm font-medium text-muted">To‘plam</span>
      <select
        value={value ?? ''}
        onChange={(event) => onChange(event.target.value || null)}
        className="focus-ring h-11 w-full rounded-xl border border-line bg-ground px-3 text-body"
      >
        <option value="">Bugungi to‘plam</option>
        {decks
          .filter((deck) => deck.kind !== 'daily')
          .map((deck) => (
            <option key={deck.id} value={deck.id}>
              {deck.name}
            </option>
          ))}
      </select>
    </label>
  );
}
