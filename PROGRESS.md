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

---

## M2 — Lookup

- [x] `providers/base.py` — `Meaning`, `LookupResult` dataclasses + `DictionaryProvider` / `TranslationProvider` Protocols, verbatim from SPEC §6
- [x] `providers/dictionary/free_dictionary.py` — dictionaryapi.dev, keyless, POS/IPA/definitions/examples
- [x] `providers/translation/azure.py` — Azure Translator v3.0, **one** batched call per lookup
- [x] `providers/dictionary/gemini.py` — structured output with a hard JSON schema, never free-text parsing
- [x] `providers/translation/gemini.py` — Gemini as translation fallback
- [x] `providers/fakes.py` — `Fake*` siblings returning fixture data, selected when the key is absent (AGENT.md §3)
- [x] `providers/registry.py` — language-aware chain: `en` → FreeDictionary + translate; non-`en` → Gemini; `UZ_PREFER_LLM` prefers Gemini when `target_lang == "uz"`
- [x] Every provider takes the shared `httpx.AsyncClient` by constructor injection (SPEC §13)
- [x] 4s timeout per provider, fall through on raise/timeout, whole-chain failure → 503 retryable, never a partial result
- [x] `models/lookup.py` — `LookupCache`, **global not per-user**, unique `(term, source_lang, target_lang)`
- [x] Alembic migration `0003_lookup_cache`
- [x] `services/lookup_service.py` — normalize → Redis (24h) → `lookup_cache` (warm Redis, bump `hit_count`) → chain → persist both
- [x] Quota: Redis counter expiring at the user's local midnight; cache hits do **not** count
- [x] Quota: accounts younger than 24h capped at 30/day (SPEC §8.5)
- [x] Rate limit: 20 lookups/min per user, 429 + `Retry-After`
- [x] Input validation: reject >64 chars or >4 whitespace tokens
- [x] Global daily provider budget; on exceed serve cache only, return `provider_budget_exceeded`, log loudly
- [x] Structured log per provider call: name, latency, cache status, quota-counted — never the payload
- [x] `api/v1/lookup.py` — `POST /lookup`, never writes a card
- [x] Tests: cache hit path, cross-user cache sharing, quota, rate limit, input rejection, budget, chain fallthrough, provider fixtures
- [x] Gates: ruff, mypy, pytest, frontend lint/tsc/build, compose health, no ERROR logs

### M2 log

**Shipped.** The full provider layer — `Meaning`/`LookupResult` and both Protocols
verbatim from SPEC §6, FreeDictionary, Azure Translator (one batched call), Gemini as
both structured dictionary and translation fallback, and fixture-backed `Fake*` siblings
selected purely by whether a key is set. The three-stage pipeline (Redis 24h → global
`lookup_cache` → chain), the global-not-per-user cache table, per-user daily quota keyed
to local midnight, the reduced new-account quota, the 20/min per-user rate limit, the
±64-char/4-token input gate, and the hard global provider budget.

**Decided.** An unknown word is 404 `term_not_found`, not the 503 the spec reserves for
a failed chain — telling a user to retry a typo forever is wrong (D8). `normalize_term`
casefolds unconditionally so the cache key is stable, with the user's own spelling kept
for the card's `display_term` (D9). `UZ_PREFER_LLM` ships on, and D7 records honestly
that the comparison SPEC §6 asks for is unmeasured because no key exists, along with the
exact procedure to run it.

**Deferred.** Nothing from M2. The Azure and Gemini paths are complete but exercised
against recorded fixtures only (BLOCKERS.md B3, B4).

**Gate output.**
```
ruff check . → All checks passed!   ruff format --check . → 59 files already formatted
mypy app/services app/providers app/srs app/telegram → Success: no issues found in 19 source files
pytest -q → 86 passed
  · POST /lookup run (en→uz) → 4 meanings, ipa present, cache=miss
  · same word, different user → cache hit, identical meanings (global cache proven)
  · cache hit leaves quota_used unchanged at 1
  · Redis flushed → next request served cache=db, hit_count incremented
  · 65 chars / 5 tokens / blank → 422 term_too_long, term_too_many_tokens, term_empty
  · 21st lookup in a minute → 429 rate_limited + Retry-After
  · quota exhausted → 429 quota_exceeded, but the cached word still returns 200
  · budget exceeded → 429 provider_budget_exceeded, cache still serves
  · whole chain raising → 503 provider_unavailable, details.retryable = true
  · first provider raising → second answers, translated, gloss_en preserved
  · every provider answering "no such word" → 404 term_not_found
  · Azure: 6 strings → exactly 1 HTTP call, order preserved; length mismatch → error
eslint → No issues found   tsc --noEmit → No errors found   vite build → built in 511ms
compose: /health ok · tables: users, decks, lookup_cache, alembic_version
         startup log: {"bot_enabled": false, "provider_fakes": true}
         logs api | grep '"level": "ERROR"' → (none)
         alembic check → No new upgrade operations detected
```

---

## M3 — Cards

- [x] `models/card.py` — `Card` + `CardState`, 1:1, unique `(deck_id, term)`, index `(user_id, due) WHERE suspended = false`
- [x] Keep scheduling state off `cards` entirely (SPEC §13)
- [x] Alembic migration `0004_cards`
- [x] `schemas/card.py` — `meanings` and `examples` in exactly the SPEC §5 shapes, `source` ∈ {user, provider}
- [x] `services/card_service.py` — create card + `card_states` row in one transaction
- [x] Omitting `deck_id` targets today's daily deck
- [x] Duplicate `(deck_id, term)` rejected with a clear error, not a 500
- [x] `display_term` keeps the user's spelling; `term` is normalized
- [x] `source_lang`/`target_lang` copied from the deck at creation
- [x] User's own examples ordered before provider ones (SPEC §5)
- [x] `POST /cards`, `GET /decks/{id}/cards` (cursor-paginated), `PATCH /cards/{id}` (meanings, note, move deck), `DELETE /cards/{id}`, `POST /cards/{id}/suspend`
- [x] `deck_service.deck_counts` now returns real card/due/new counts in one query
- [x] Tests: save from a lookup result, duplicate rejection, daily-deck default, cursor pagination, move between decks, suspend toggle, cross-user isolation, cascade delete
- [x] Gates: ruff, mypy, pytest, frontend lint/tsc/build, compose health, no ERROR logs

### M3 log

**Shipped.** `cards` and `card_states` as two tables — content and scheduling stay
apart, exactly as SPEC §13 insists — created together in one transaction so no card
ever exists without a state. Full CRUD, keyset pagination, in-deck search, deck moves,
suspend toggle, and real card/due/new counts on the decks list in a single grouped
query.

**Decided.** Three things the implementation forced, all written up in DECISIONS.md:
the ORM relationship is `card_state` because `state` collided with the response field
(D11); error messages snapshot `deck.id` and `display_term` before the flush, because a
failed flush expires the objects and reading them in the `except` raises
`MissingGreenlet` instead of the intended 409 (D12); pagination is keyset on the
UUIDv7 id, since offsets drift as cards are saved mid-scroll (D13).

**Deferred.** Nothing. `deck_counts` moved from its M1 placeholder to a real query.

**Gate output.**
```
ruff check . → All checks passed!   ruff format --check . → 64 files already formatted
mypy app/services app/providers app/srs app/telegram → Success: no issues found in 20 source files
pytest -q → 110 passed
  · save from a lookup result → 201, one card_states row, state=0, reps=0
  · same word twice in one deck → 409 card_duplicate, message names the word  ← M3 acceptance
  · "Run" then "  RUN  " → 409 (same normalized term)
  · "  Serendipity " → term=serendipity, display_term=Serendipity
  · same word in two decks → both 201 (the index is (deck_id, term))
  · no deck_id → lands in today's daily deck
  · reader's own example sorted ahead of the provider's
  · pagination: 5 cards at limit=2 → word4/word3, word2/word1, word0, next_cursor null
  · move onto a duplicate → 409; archived deck → 409 deck_archived
  · suspend toggles, and a suspended card drops out of due_count
  · delete card → state gone; delete deck → cards and states gone
  · another user gets 404 on patch, delete and suspend
eslint → No issues found   tsc --noEmit → No errors found   vite build → built in 501ms
compose: /health ok · tables now include cards and card_states
         logs api | grep '"level": "ERROR"' → (none)
         alembic check → No new upgrade operations detected
```

---

## M4 — Review

- [x] `srs/types.py` — `Rating` enum (1 again … 4 easy), `CardStateSnapshot`, `SchedulingResult`, `ReviewLogRecord`
- [x] `srs/scheduler.py` — `schedule(state, rating, now) -> SchedulingResult`, pure: no database, no HTTP
- [x] Map the spec's `state` 0-3 onto py-fsrs 4.x, which has no `New` (DECISIONS.md D1)
- [x] Derive `reps`, `lapses`, `elapsed_days`, `scheduled_days` ourselves (D2)
- [x] Per-user `fsrs_params` read from `users.fsrs_params`; null → library defaults
- [x] `models/review.py` — `ReviewLog`, append-only, every column SPEC §5 lists
- [x] Alembic migration `0005_review_logs`
- [x] `services/review_service.py` — queue building and batch answering
- [x] Queue order: learning/relearning first, then due reviews oldest-first, then new up to `daily_new_limit`
- [x] `daily_review_limit` caps the session
- [x] Batch answer in **one transaction**: update `card_states`, insert `review_logs`
- [x] Clamp client `reviewed_at` to `[now - 10min, now]`
- [x] `api/v1/review.py` — `GET /review/queue`, `POST /review/answer`, `GET /review/counts`
- [x] Tests: `again` reappears in the same session, `easy` schedules days out, one review_log row per answer, ordering, limits, clamping, cross-user isolation
- [x] Gates: ruff, mypy, pytest, frontend lint/tsc/build, compose health, no ERROR logs

### M4 log

**Shipped.** A pure FSRS wrapper with no database or HTTP in it, the append-only
`review_logs` table carrying every column SPEC §5 lists, queue building in the spec's
order, batch answering in one transaction, and `reviewed_at` clamping.

**Decided.** Learning and relearning cards get a 20-minute learn-ahead window (D14) —
without it the M4 acceptance criterion is unsatisfiable, because FSRS puts the first
learning step a minute out and a strict `due <= now` queue could never show an `again`
card again. Review cards are deliberately excluded from that window. A batch applies
answers in the order sent, so a card rated `again` then `good` in one flush schedules
from the right intermediate state (D15). The spec's 0-3 `state` column is mapped onto
py-fsrs 4.x, which has no `New`, and `reps`/`lapses`/`elapsed_days`/`scheduled_days` are
derived here because the library dropped them (D1, D2).

**Deferred.** The FSRS optimizer, per SPEC §9. `users.fsrs_params` exists and is read
(null → library defaults); nothing writes it in v1.

**Gate output.**
```
ruff check . → All checks passed!   ruff format --check . → 72 files already formatted
mypy app/services app/providers app/srs app/telegram → Success: no issues found in 23 source files
pytest -q → 153 passed
  · rated again → due < 30 min out AND back in the queue          ← M4 acceptance
  · rated easy → scheduled_days >= 1, due > 1 day out, queue empty ← M4 acceptance
  · 3 answers → exactly 3 review_logs rows, ratings 1/3/4         ← M4 acceptance
  · same card twice in one batch → 2 log rows, second scheduled from the first's state
  · queue order: learning card, then the 30-day-overdue review, then the new one
  · due reviews oldest-first; not-yet-due and suspended cards excluded
  · daily_new_limit=2 with 4 new cards → 2 items, new_remaining=2
  · unknown card in a batch → 404 and *nothing* written (one transaction)
  · reviewed_at +400 days → clamped to now; -30 days → clamped to now-10min
  · learn-ahead does not pull a review card due in 5 minutes into the queue
  · 12 consecutive scheduler runs, no fuzz-induced flakiness
eslint → No issues found   tsc --noEmit → No errors found   vite build → built in 548ms
compose: /health ok · review_logs present · logs grep ERROR → (none)
         alembic check → No new upgrade operations detected
```
