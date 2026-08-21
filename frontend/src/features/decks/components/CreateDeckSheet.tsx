import { useState } from 'react';

import { useCreateDeck } from '@/features/decks/hooks';
import { messageFor } from '@/shared/lib/errorMessages';
import { Button } from '@/shared/ui/Button';
import { Sheet } from '@/shared/ui/Sheet';
import { TextField } from '@/shared/ui/TextField';
import { useToast } from '@/shared/ui/toastContext';

const LANGS = ['en', 'ru', 'uz', 'tr', 'de', 'fr'];

export function CreateDeckSheet({ open, onClose }: { open: boolean; onClose: () => void }) {
  const [name, setName] = useState('');
  const [sourceLang, setSourceLang] = useState('en');
  const [targetLang, setTargetLang] = useState('uz');
  const createDeck = useCreateDeck();
  const toast = useToast();

  const submit = () => {
    if (!name.trim()) return;
    createDeck.mutate(
      { name: name.trim(), source_lang: sourceLang, target_lang: targetLang },
      {
        onSuccess: () => {
          toast('To‘plam yaratildi');
          setName('');
          onClose();
        },
        onError: (error) => toast(messageFor(error), 'error'),
      },
    );
  };

  return (
    <Sheet open={open} title="Yangi to‘plam" onClose={onClose}>
      <div className="space-y-4">
        <TextField
          label="Nomi"
          value={name}
          maxLength={120}
          placeholder="Masalan: Dune"
          onChange={(event) => setName(event.target.value)}
        />

        <div className="grid grid-cols-2 gap-3">
          <LangSelect label="O‘rganilayotgan til" value={sourceLang} onChange={setSourceLang} />
          <LangSelect label="Ma’no tili" value={targetLang} onChange={setTargetLang} />
        </div>

        <Button className="w-full" disabled={!name.trim() || createDeck.isPending} onClick={submit}>
          {createDeck.isPending ? 'Yaratilmoqda…' : 'Yaratish'}
        </Button>
      </div>
    </Sheet>
  );
}

function LangSelect({
  label,
  value,
  onChange,
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
}) {
  return (
    <label className="block">
      <span className="mb-1.5 block text-sm font-medium text-muted">{label}</span>
      <select
        value={value}
        onChange={(event) => onChange(event.target.value)}
        className="focus-ring h-11 w-full rounded-xl border border-line bg-ground px-3 font-mono text-sm uppercase text-body"
      >
        {LANGS.map((lang) => (
          <option key={lang} value={lang}>
            {lang.toUpperCase()}
          </option>
        ))}
      </select>
    </label>
  );
}
