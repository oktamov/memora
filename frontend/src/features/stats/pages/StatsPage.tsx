/** Stats. The real screen — heatmap, streak, retention — lands in M7. */
import { EmptyState } from '@/shared/ui/EmptyState';

export function StatsPage() {
  return (
    <EmptyState
      title="Statistika tayyorlanmoqda"
      hint="Seriya, faollik kalendari va eslab qolish darajasi shu yerda ko‘rinadi."
    />
  );
}
