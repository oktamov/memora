/**
 * The activity heatmap — a notebook margin, not a SaaS dashboard (SPEC §10).
 *
 * Saffron is the signature colour and carries the intensity; empty days are the paper
 * itself rather than a grey block, so the grid reads as marks on a page.
 */
import { cn } from '@/shared/lib/cn';
import type { DailyActivity } from '@/shared/api/types';

const UZ_MONTHS_SHORT = ['yan', 'fev', 'mar', 'apr', 'may', 'iyn', 'iyl', 'avg', 'sen', 'okt', 'noy', 'dek'];

function intensity(reviews: number, busiest: number): string {
  if (reviews === 0) return 'bg-raised';
  const share = reviews / Math.max(busiest, 1);
  if (share > 0.66) return 'bg-saffron';
  if (share > 0.33) return 'bg-saffron/70';
  return 'bg-saffron/40';
}

export function Heatmap({ days }: { days: DailyActivity[] }) {
  const busiest = days.reduce((max, day) => Math.max(max, day.reviews), 0);

  // Pad the first week so every column is a real Monday-to-Sunday week.
  const firstDay = days[0] ? new Date(days[0].date) : new Date();
  const leadingBlanks = (firstDay.getDay() + 6) % 7;

  // One label per month, on the column where that month first appears. Labelling
  // every early-in-the-month column repeats the same name across adjacent weeks.
  const monthLabels = new Map<number, string>();
  const labelled = new Set<number>();
  days.forEach((day, index) => {
    const month = new Date(day.date).getMonth();
    if (labelled.has(month)) return;
    labelled.add(month);
    const column = Math.floor((index + leadingBlanks) / 7);
    if (!monthLabels.has(column)) {
      monthLabels.set(column, UZ_MONTHS_SHORT[month] ?? '');
    }
  });

  const columnCount = Math.ceil((days.length + leadingBlanks) / 7);

  return (
    <div className="overflow-x-auto">
      <div className="inline-block min-w-full">
        <div
          className="grid grid-flow-col gap-[3px]"
          style={{ gridTemplateRows: 'repeat(7, minmax(0, 1fr))' }}
          role="img"
          aria-label={`So‘nggi ${days.length} kunlik faollik`}
        >
          {Array.from({ length: leadingBlanks }, (_, index) => (
            <div key={`blank-${index}`} className="h-[11px] w-[11px]" />
          ))}
          {days.map((day) => (
            <div
              key={day.date}
              title={`${day.date}: ${day.reviews}`}
              className={cn('h-[11px] w-[11px] rounded-[3px]', intensity(day.reviews, busiest))}
            />
          ))}
        </div>

        <div
          className="mt-1.5 grid grid-flow-col gap-[3px]"
          style={{ gridTemplateColumns: `repeat(${columnCount}, minmax(0, 1fr))` }}
        >
          {Array.from({ length: columnCount }, (_, column) => (
            <span key={column} className="font-mono text-[0.6rem] text-faint">
              {monthLabels.get(column) ?? ''}
            </span>
          ))}
        </div>
      </div>
    </div>
  );
}
