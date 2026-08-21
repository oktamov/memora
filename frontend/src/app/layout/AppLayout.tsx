import { NavLink, Outlet, useLocation } from 'react-router-dom';

import { cn } from '@/shared/lib/cn';
import { useNativeBackButton } from '@/shared/hooks/useBackButton';

const TABS = [
  { to: '/', label: 'To‘plamlar' },
  { to: '/review', label: 'Takrorlash' },
  { to: '/stats', label: 'Statistika' },
];

/**
 * The browsing shell — "a notebook" (SPEC §10).
 *
 * The review screen deliberately does not use this layout: it is a dark room with one
 * lamp on, with no nav competing for attention.
 */
export function AppLayout() {
  const location = useLocation();
  useNativeBackButton();

  return (
    <div className="mx-auto flex min-h-full w-full max-w-lg flex-col">
      <header className="px-5 pb-1 pt-5">
        <p className="font-display text-2xl font-bold tracking-tight text-body">Memora</p>
      </header>

      <nav className="sticky top-0 z-20 bg-ground/85 px-5 py-2 backdrop-blur">
        <div className="flex gap-1 rounded-xl bg-raised p-1">
          {TABS.map((tab) => {
            const active =
              tab.to === '/' ? location.pathname === '/' : location.pathname.startsWith(tab.to);
            return (
              <NavLink
                key={tab.to}
                to={tab.to}
                className={cn(
                  'focus-ring flex-1 rounded-lg px-3 py-2 text-center text-sm font-medium transition-colors',
                  active ? 'bg-surface text-body shadow-sm' : 'text-muted hover:text-body',
                )}
              >
                {tab.label}
              </NavLink>
            );
          })}
        </div>
      </nav>

      <main
        className="flex-1 px-5 pb-8 pt-4"
        style={{ paddingBottom: 'calc(2rem + var(--safe-bottom))' }}
      >
        <Outlet />
      </main>
    </div>
  );
}
