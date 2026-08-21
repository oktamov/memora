import type { InputHTMLAttributes, TextareaHTMLAttributes } from 'react';

import { cn } from '@/shared/lib/cn';

const FIELD =
  'focus-ring w-full rounded-xl border border-line bg-ground px-3.5 py-2.5 text-body placeholder:text-faint';

export function TextField({
  label,
  className,
  ...rest
}: InputHTMLAttributes<HTMLInputElement> & { label: string }) {
  return (
    <label className="block">
      <span className="mb-1.5 block text-sm font-medium text-muted">{label}</span>
      <input className={cn(FIELD, 'h-11', className)} {...rest} />
    </label>
  );
}

export function TextArea({
  label,
  className,
  ...rest
}: TextareaHTMLAttributes<HTMLTextAreaElement> & { label: string }) {
  return (
    <label className="block">
      <span className="mb-1.5 block text-sm font-medium text-muted">{label}</span>
      <textarea className={cn(FIELD, 'min-h-[84px] resize-y', className)} {...rest} />
    </label>
  );
}
