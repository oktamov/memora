import { cn } from '@/shared/lib/cn';

export function Spinner({ className }: { className?: string }) {
  return (
    <span
      role="status"
      aria-label="Yuklanmoqda"
      className={cn(
        'inline-block h-5 w-5 animate-spin rounded-full border-2 border-line border-t-indigo',
        className,
      )}
    />
  );
}

export function ScreenSpinner() {
  return (
    <div className="flex min-h-[50vh] items-center justify-center">
      <Spinner className="h-6 w-6" />
    </div>
  );
}
