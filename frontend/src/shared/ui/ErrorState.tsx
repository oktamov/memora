import { messageFor } from '@/shared/lib/errorMessages';
import { Button } from '@/shared/ui/Button';

export function ErrorState({ error, onRetry }: { error: unknown; onRetry?: () => void }) {
  return (
    <div className="animate-fade-up rounded-card border border-madder/25 bg-madder/[0.06] px-5 py-6 text-center">
      <p className="text-[0.95rem] leading-relaxed text-body">{messageFor(error)}</p>
      {onRetry ? (
        <Button variant="ghost" size="sm" className="mt-4" onClick={onRetry}>
          Qayta urinish
        </Button>
      ) : null}
    </div>
  );
}
