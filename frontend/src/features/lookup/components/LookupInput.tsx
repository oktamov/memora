import { Search } from 'lucide-react';
import { useEffect, useRef, useState } from 'react';

import { cn } from '@/shared/lib/cn';

/**
 * The persistent lookup input (SPEC §10).
 *
 * Fires **only** on explicit submit. There is no search-as-you-type: every keystroke
 * sent to a paid API is money burned (SPEC §13). The 300ms debounce below throttles
 * repeated *submits* — a double-tapped keyboard "go" — not typing.
 */
export function LookupInput({
  onSubmit,
  autoFocus = false,
  busy = false,
  placeholder = 'So‘zni yozing',
  defaultValue = '',
}: {
  onSubmit: (term: string) => void;
  autoFocus?: boolean;
  busy?: boolean;
  placeholder?: string;
  defaultValue?: string;
}) {
  const [term, setTerm] = useState(defaultValue);
  const inputRef = useRef<HTMLInputElement>(null);
  const lastSubmit = useRef(0);

  // SPEC §10: focusable from anywhere via `/`.
  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key !== '/' || event.metaKey || event.ctrlKey) return;
      const target = event.target as HTMLElement | null;
      if (target && ['INPUT', 'TEXTAREA'].includes(target.tagName)) return;
      event.preventDefault();
      inputRef.current?.focus();
    };
    window.addEventListener('keydown', onKeyDown);
    return () => window.removeEventListener('keydown', onKeyDown);
  }, []);

  const submit = () => {
    const value = term.trim();
    if (!value || busy) return;

    const now = Date.now();
    if (now - lastSubmit.current < 300) return;
    lastSubmit.current = now;

    onSubmit(value);
  };

  return (
    <form
      className="relative"
      onSubmit={(event) => {
        event.preventDefault();
        submit();
      }}
    >
      <Search
        aria-hidden
        className="pointer-events-none absolute left-4 top-1/2 h-[18px] w-[18px] -translate-y-1/2 text-faint"
      />
      <input
        ref={inputRef}
        value={term}
        autoFocus={autoFocus}
        onChange={(event) => setTerm(event.target.value)}
        placeholder={placeholder}
        enterKeyHint="search"
        autoCapitalize="none"
        autoCorrect="off"
        spellCheck={false}
        aria-label="Qidiriladigan so‘z"
        className={cn(
          'focus-ring h-12 w-full rounded-2xl border border-line bg-surface pl-11 pr-4',
          'text-body placeholder:text-faint shadow-sm transition-colors',
        )}
      />
    </form>
  );
}
