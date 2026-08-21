/**
 * The language pair, always visible above the input.
 *
 * Chosen once, remembered, and switchable in one tap — this app is for people who will
 * not go hunting through a settings screen.
 */
import { ArrowLeftRight } from 'lucide-react';

import { cn } from '@/shared/lib/cn';
import { LANGUAGES } from '@/shared/lib/languages';

export function LanguagePair({
  source,
  target,
  onChange,
  disabled = false,
}: {
  source: string;
  target: string;
  onChange: (source: string, target: string) => void;
  disabled?: boolean;
}) {
  return (
    <div className="flex items-center gap-1.5">
      <Picker
        label="Qaysi tildan"
        value={source}
        disabled={disabled}
        onChange={(code) => onChange(code, code === target ? source : target)}
      />

      <button
        type="button"
        disabled={disabled}
        aria-label="Tillarni almashtirish"
        onClick={() => onChange(target, source)}
        className={cn(
          'focus-ring shrink-0 rounded-lg p-2 text-faint transition-colors',
          'hover:bg-raised hover:text-body disabled:opacity-40',
        )}
      >
        <ArrowLeftRight className="h-4 w-4" />
      </button>

      <Picker
        label="Qaysi tilga"
        value={target}
        disabled={disabled}
        onChange={(code) => onChange(code === source ? target : source, code)}
      />
    </div>
  );
}

function Picker({
  label,
  value,
  disabled,
  onChange,
}: {
  label: string;
  value: string;
  disabled: boolean;
  onChange: (code: string) => void;
}) {
  return (
    <select
      aria-label={label}
      value={value}
      disabled={disabled}
      onChange={(event) => onChange(event.target.value)}
      className={cn(
        'focus-ring h-9 min-w-0 flex-1 rounded-lg border border-line bg-surface px-2.5',
        'font-mono text-xs uppercase tracking-wide text-body disabled:opacity-50',
      )}
    >
      {LANGUAGES.map((language) => (
        <option key={language.code} value={language.code}>
          {language.code.toUpperCase()} · {language.label}
        </option>
      ))}
    </select>
  );
}
