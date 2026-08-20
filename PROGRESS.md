# Memora — Build Progress

Living log. Updated continuously during the autonomous run.

---

## M0 — Skeleton

- [x] Repo scaffolding: `backend/`, `frontend/`, root `docker-compose.yml`, `.gitignore`
- [x] `backend/pyproject.toml` with pinned deps (FastAPI, SQLAlchemy 2.0 async, asyncpg, alembic, pydantic v2, fsrs, httpx, aiogram 3, uuid6, redis) managed by `uv`
- [x] `app/core/config.py` — `Settings` via pydantic-settings, all §12 env vars
- [x] `app/core/errors.py` — error envelope `{error:{code,message,details}}` + handlers
- [x] `app/db/base.py` (DeclarativeBase) and `app/db/session.py` (async engine + session factory)
- [x] `app/main.py` — app factory, lifespan creating the single shared `httpx.AsyncClient`, structured JSON logging
- [x] `GET /health` returning db + redis reachability
- [x] Alembic initialized against async engine, `alembic.ini`, `env.py` wired to `Settings`
- [x] `.env.example` with empty values; `.env` gitignored
- [x] Frontend: Vite + React 18 + TS strict, Tailwind, path aliases, `/api` dev proxy
- [x] Frontend: no PWA plugin, no service worker (§2 non-goal)
- [x] `docker-compose.yml` with `api`, `db`, `redis`, `web`, `nginx`
- [x] ruff lint+format clean, mypy clean on target packages, pytest green
- [x] frontend lint + `tsc --noEmit` + build green
- [x] `docker compose up -d --build`, `/health` green, no ERROR lines in api logs

### M0 log

**Shipped.** Compose stack (`api`, `db`, `redis`, `web`, `nginx`), FastAPI app factory
with the single shared `httpx.AsyncClient` on `app.state`, structured JSON logging,
the SPEC §7 error envelope on every path, async SQLAlchemy engine, Alembic wired to
`Settings`, Vite + React 18 + TS strict frontend with the SPEC §10 palette and type
roles in place.

**Decided.** `/health` answers 200 with per-dependency status rather than 503, so the
gate does not flap on container start ordering (DECISIONS.md D5). Alembic ships an
empty `0001_baseline` so `alembic_version` exists from M0; tables arrive with their own
milestone's migration.

**Deferred.** All five screens (M5) — the M0 frontend is a shell that proves the `/api`
proxy and renders the design tokens.

**Gate output.**
```
backend:  ruff check → All checks passed!   ruff format --check → 25 files already formatted
          mypy app/services app/providers app/srs app/telegram → Success: no issues found in 7 source files
          pytest -q → 2 passed
frontend: eslint → clean   tsc --noEmit → clean   vite build → built in 505ms
compose:  curl /health → {"status":"ok","db":"up","redis":"up","version":"0.1.0"}
          curl :8080/health (through nginx) → same
          docker compose logs api | grep '"level": "ERROR"' → (none)
          alembic_version → 0001_baseline
```
