/** Uzbek formatting helpers. Sentence case, active voice (SPEC §10). */

const UZ_MONTHS = [
  'yanvar',
  'fevral',
  'mart',
  'aprel',
  'may',
  'iyun',
  'iyul',
  'avgust',
  'sentabr',
  'oktabr',
  'noyabr',
  'dekabr',
];

export function formatDate(iso: string): string {
  const date = new Date(iso);
  return `${date.getDate()}-${UZ_MONTHS[date.getMonth()]}`;
}

/** "3 kun", "2 oy", "10 daqiqa" — the interval printed under a ladder stop. */
export function formatInterval(from: Date, to: Date): string {
  const minutes = Math.round((to.getTime() - from.getTime()) / 60_000);

  if (minutes < 1) return '<1 daq';
  if (minutes < 60) return `${minutes} daq`;

  const hours = Math.round(minutes / 60);
  if (hours < 24) return `${hours} soat`;

  const days = Math.round(hours / 24);
  if (days < 30) return `${days} kun`;

  const months = Math.round(days / 30);
  if (months < 12) return `${months} oy`;

  return `${Math.round(months / 12)} yil`;
}

/** Uzbek has no plural inflection here, so the noun stays constant. */
export function plural(count: number, noun: string): string {
  return `${count} ${noun}`;
}

export function languagePair(source: string, target: string): string {
  return `${source.toUpperCase()} → ${target.toUpperCase()}`;
}
