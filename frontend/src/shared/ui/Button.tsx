import type { ButtonHTMLAttributes, ReactNode } from 'react';

import { cn } from '@/shared/lib/cn';

type Variant = 'primary' | 'ghost' | 'quiet' | 'danger';
type Size = 'sm' | 'md';

const VARIANTS: Record<Variant, string> = {
  primary: 'bg-indigo text-white hover:bg-indigo/90 active:bg-indigo/80',
  ghost: 'border border-line bg-surface text-body hover:bg-raised',
  quiet: 'text-muted hover:bg-raised hover:text-body',
  danger: 'border border-madder/30 bg-madder/10 text-madder hover:bg-madder/15',
};

const SIZES: Record<Size, string> = {
  sm: 'h-9 px-3 text-sm',
  md: 'h-11 px-4 text-[0.95rem]',
};

type Props = ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: Variant;
  size?: Size;
  children: ReactNode;
};

export function Button({
  variant = 'primary',
  size = 'md',
  className,
  children,
  ...rest
}: Props) {
  return (
    <button
      type="button"
      className={cn(
        'focus-ring inline-flex items-center justify-center gap-2 rounded-xl font-medium',
        'transition-colors disabled:cursor-not-allowed disabled:opacity-45',
        VARIANTS[variant],
        SIZES[size],
        className,
      )}
      {...rest}
    >
      {children}
    </button>
  );
}
