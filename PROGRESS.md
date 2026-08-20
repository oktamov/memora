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

---

## M1 — Telegram auth + decks

- [x] `models/user.py` — `User` per SPEC §5 including `fsrs_params jsonb` (SPEC §9)
- [x] `models/deck.py` — `Deck`, `DeckKind` enum, partial unique index `(user_id, daily_date) WHERE kind='daily'`, index `(user_id, archived_at)`
- [x] Alembic migration `0002_users_decks`, reviewed by hand (no `create_all`)
- [x] `telegram/init_data.py` — the 6-step HMAC algorithm exactly as SPEC §7 states, `hmac.compare_digest`, 24h `auth_date` freshness
- [x] `tests/factories.py` — fixture generator signing initData with a dummy bot token
- [x] Test: valid initData passes
- [x] Test: tampered `hash` is rejected
- [x] Test: tampered *field* (with a stale hash) is rejected
- [x] Test: `auth_date` older than 24h is rejected
- [x] Test: missing `hash` is rejected
- [x] `core/security.py` — session JWT encode/decode, 24h TTL
- [x] `core/deps.py` — `get_db`, `get_current_user` from `Authorization: Bearer`
- [x] `services/auth_service.py` — upsert by `telegram_id`, never by `username`
- [x] `services/deck_service.py` — CRUD + lazy daily-deck creation, race-safe on the partial unique index
- [x] `api/v1/auth.py` — `POST /auth/telegram`, `GET /auth/me`, `PATCH /auth/me`
- [x] `api/v1/decks.py` — list (with card + due counts), create, get, patch, delete, `GET /decks/daily`
- [x] `api/v1/router.py` aggregating v1 under `/api/v1`
- [x] Rate limit: 60 req/min per IP on auth endpoints (SPEC §8.3)
- [x] At least one test per endpoint (SPEC §12)
- [x] Gates: ruff, mypy, pytest, frontend lint/tsc/build, compose health, no ERROR logs

### M1 log

**Shipped.** The six-step initData HMAC validator exactly as SPEC §7 states, with
`hmac.compare_digest` and the 24h freshness check; a fixture generator that signs
payloads with a dummy bot token; session JWTs; `telegram_id`-keyed user upsert; full
deck CRUD; lazy daily-deck creation in the *user's* timezone; per-IP rate limiting on
auth.

**Decided.** Column defaults moved from Python-side `default=` to `server_default=`.
Hand-reviewing the generated migration caught that the core `INSERT ... ON CONFLICT` in
`upsert_user` bypasses SQLAlchemy's Python defaults, so `daily_new_limit` and friends
would have hit a NOT NULL violation on every first login. `ON CONFLICT` also had to
name the partial index's predicate (`index_where`) or Postgres cannot match it — both
now come from one `DAILY_DECK_PREDICATE` constant. Tests run against a dedicated
`memora_test` database and Redis DB 15; the dev database belongs to Alembic
(DECISIONS.md D6 covers the host port move to 5433/6380).

**Deferred.** `deck_service.deck_counts` returns zeros until the `cards` and
`card_states` tables land in M3.

**Gate output.**
```
ruff check . → All checks passed!     ruff format --check . → 44 files already formatted
mypy app/services app/providers app/srs app/telegram → Success: no issues found in 10 source files
pytest -q → 45 passed
  · 13 initData cases: valid, flipped-hash, swapped user id with a real signature,
    wrong bot token, expired, missing hash/user/auth_date, blank-valued fields
  · concurrency: 5 simultaneous first-saves produce exactly 1 daily deck
  · timezone: 17:00 UTC and 20:00 UTC on 1 Mar are different Tashkent days
eslint → No issues found   tsc --noEmit → No errors found   vite build → built in 509ms
compose: /health → {"status":"ok","db":"up","redis":"up","version":"0.1.0"}
         POST /api/v1/auth/telegram → 503 bot_not_configured (expected, BLOCKERS.md B1)
         docker compose logs api | grep '"level": "ERROR"' → (none)
         alembic_version → 0002_users_decks   alembic check → No new upgrade operations detected
```
