import { Heatmap } from '@/features/stats/components/Heatmap';
import { StatTile } from '@/features/stats/components/StatTile';
import { useStats } from '@/features/stats/hooks';
import { plural } from '@/shared/lib/format';
import { EmptyState } from '@/shared/ui/EmptyState';
import { ErrorState } from '@/shared/ui/ErrorState';
import { ScreenSpinner } from '@/shared/ui/Spinner';

export function StatsPage() {
  const stats = useStats();

  if (stats.isPending) return <ScreenSpinner />;
  if (stats.isError) return <ErrorState error={stats.error} onRetry={() => void stats.refetch()} />;
  if (!stats.data) return null;

  const data = stats.data;
  const hasHistory = data.reviews_per_day.some((day) => day.reviews > 0);

  if (data.total_cards === 0) {
    return (
      <EmptyState
        title="Hali statistika yo‘q"
        hint="Birinchi so‘zingizni saqlang va takrorlang — seriya, faollik va eslab qolish darajasi shu yerda to‘planadi."
      />
    );
  }

  return (
    <div className="space-y-5">
      <div className="grid grid-cols-2 gap-3">
        <StatTile
          label="Seriya"
          value={plural(data.streak_days, 'kun')}
          hint={
            data.longest_streak_days > data.streak_days
              ? `Eng uzuni: ${plural(data.longest_streak_days, 'kun')}`
              : 'Eng uzun seriyangiz'
          }
          accent={data.streak_days > 0}
        />
        <StatTile
          label="Bugun"
          value={String(data.reviews_today)}
          hint={
            data.cards_due_today > 0
              ? `Yana ${plural(data.cards_due_today, 'karta')} navbatda`
              : 'Bugungi navbat tugadi'
          }
        />
        <StatTile label="Jami kartalar" value={String(data.total_cards)} />
        <StatTile
          label="Eslab qolish"
          value={
            data.retention_rate === null ? '—' : `${Math.round(data.retention_rate * 100)}%`
          }
          hint={
            data.retention_rate === null
              ? 'Takrorlashni boshlaganingizda hisoblanadi'
              : 'Takroriy kartalarda'
          }
        />
      </div>

      <section className="rounded-card border border-line bg-surface px-4 py-4">
        <h2 className="font-mono text-[0.62rem] uppercase tracking-[0.18em] text-faint">
          So‘nggi 90 kun
        </h2>
        <div className="mt-3">
          {hasHistory ? (
            <Heatmap days={data.reviews_per_day} />
          ) : (
            <p className="py-4 text-center text-sm text-muted">
              Birinchi takroringizdan keyin bu yerda izlar paydo bo‘ladi.
            </p>
          )}
        </div>
      </section>
    </div>
  );
}
