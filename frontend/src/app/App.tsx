import { useEffect, useState } from 'react';

type Health = {
  status: string;
  db: string;
  redis: string;
  version: string;
};

/**
 * M0 shell. The five real screens land in M5; this proves the Vite dev server
 * proxies `/api` and that the API is reachable from the browser.
 */
export function App() {
  const [health, setHealth] = useState<Health | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetch('/api/health')
      .then((response) => (response.ok ? response.json() : Promise.reject(response.statusText)))
      .then((data: Health) => setHealth(data))
      .catch((cause: unknown) => setError(String(cause)));
  }, []);

  return (
    <main className="mx-auto flex min-h-full max-w-md flex-col justify-center gap-6 px-6 py-16">
      <div>
        <h1 className="font-display text-term font-bold tracking-tight">Memora</h1>
        <p className="mt-2 text-lg text-muted">
          Kitob o&apos;qiyotganda uchragan so&apos;zlarni saqlang va yodlang.
        </p>
      </div>

      <div className="rounded-card border border-line bg-surface p-5 shadow-card">
        <p className="font-mono text-xs uppercase tracking-widest text-faint">Backend</p>
        {health ? (
          <dl className="mt-3 space-y-1.5 font-mono text-sm">
            <Row label="status" value={health.status} />
            <Row label="db" value={health.db} />
            <Row label="redis" value={health.redis} />
            <Row label="version" value={health.version} />
          </dl>
        ) : (
          <p className="mt-3 font-mono text-sm text-madder">{error ?? 'Ulanmoqda…'}</p>
        )}
      </div>
    </main>
  );
}

function Row({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-baseline justify-between gap-4">
      <dt className="text-faint">{label}</dt>
      <dd className={value === 'down' ? 'text-madder' : 'text-sage'}>{value}</dd>
    </div>
  );
}
