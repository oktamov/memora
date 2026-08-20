# Memora — Build Specification

A multilingual vocabulary app delivered as a **Telegram Mini App**. Users look up
unknown words while reading, save them into decks, and memorize them with spaced
repetition (Anki-style).

The product is three pieces: a Telegram bot (entry point, notifications, quick capture),
a Mini App web client opened from the bot, and one FastAPI backend serving both.

This document is the source of truth. Follow it exactly. Where it is silent, choose
the simplest thing that works and write down the decision in `DECISIONS.md`.

---

## 1. Product summary

**The loop:** user reads a paper book → hits an unknown word → types it into the app →
gets all meanings, pronunciation, part of speech, example sentences → saves the ones
worth keeping into a deck → reviews daily with FSRS scheduling.

**Two kinds of decks:**
- **Normal deck** — user-created, named, permanent ("Dune", "Business English").
- **Daily deck** — auto-created per user per calendar day. Created lazily on first
  save of the day. Named by date. This is the default target when the user does not
  pick a deck.

**Two entry points, one backend:**
- **Mini App** — full experience: decks, lookup, review, stats.
- **Bot chat** — quick capture. The user sends a bare word to the bot and gets meanings
  back with inline buttons to save into today's daily deck. While holding a physical
  book, typing one word into a chat is faster than opening an app. The bot also sends
  the daily review reminder.

Both paths go through the same `lookup_service` and the same quota accounting.

**Core promise:** looking up a word must feel instant. Everything else is secondary.

### Naming

Product name: **Memora**. Written with a capital M, never all-caps, never "MemorA".
Package/module names, the database, and the Docker services use lowercase `memora`.

The name is common in this category — several unrelated apps ship under it. Do not
generate marketing copy that claims uniqueness of the name, and do not register
`memoraapp.*` style domains without checking availability first. Inside the codebase
this has no effect; it matters only for anything user-facing outside Telegram.

---

## 2. Non-goals

Do not build these. They are explicitly out of scope for v1.

- Offline support, service-worker caching, local database, sync engine.
  The app is **online-only**. Telegram Mini Apps have no meaningful offline story;
  do not attempt one.
- PWA manifest, service worker, install prompts. Telegram is the shell. Remove
  `vite-plugin-pwa` if scaffolded.
- Email/password authentication, password reset, email verification. Identity comes
  from Telegram only. There is no login screen.
- Native mobile apps. Standalone web access outside Telegram.
- Deck sharing, public deck library, social features, leaderboards.
- Document/PDF/YouTube import, bulk card generation.
- Image occlusion, cloze cards, audio recording.
- Payment/subscription.
- Full-text translation. The app translates **words and short phrases only**
  (see §8 abuse controls). It is not a Google Translate replacement.

---

## 3. Tech stack

Pin these. Do not substitute.

**Backend**
- Python 3.12
- FastAPI
- SQLAlchemy 2.0 (async, `AsyncSession`) + asyncpg
- Alembic for migrations
- Pydantic v2 (`pydantic-settings` for config)
- PostgreSQL 16
- Redis 7 — rate limiting and hot lookup cache only
- `fsrs` (py-fsrs) for scheduling
- `httpx` for outbound HTTP
- `aiogram` 3.x for the bot (webhook mode, mounted on the same FastAPI app)
- `uv` for dependency management
- `pytest` + `pytest-asyncio` + `httpx.ASGITransport` for tests

**Frontend**
- Vite + React 18 + TypeScript (strict)
- TanStack Query for all server state
- Zustand for review-session state only
- React Router
- Tailwind CSS + shadcn/ui
- `@telegram-apps/sdk-react` for Mini App integration

**Infra**
- Docker Compose: `api`, `db`, `redis`, `web`, `nginx`
- No Celery. Use FastAPI `BackgroundTasks`. If a real queue becomes necessary later,
  use ARQ, not Celery.

---

## 4. Repository structure

```
memora/
├── backend/
│   ├── app/
│   │   ├── main.py                 # app factory, lifespan, middleware
│   │   ├── core/
│   │   │   ├── config.py           # Settings (pydantic-settings)
│   │   │   ├── security.py         # session JWT encode/decode
│   │   │   ├── deps.py             # get_db, get_current_user, quota checks
│   │   │   └── errors.py           # exception handlers, error envelope
│   │   ├── db/
│   │   │   ├── base.py             # DeclarativeBase
│   │   │   └── session.py          # engine, async_session_factory
│   │   ├── models/                 # one file per aggregate
│   │   │   ├── user.py
│   │   │   ├── deck.py
│   │   │   ├── card.py             # Card + CardState
│   │   │   ├── review.py           # ReviewLog
│   │   │   └── lookup.py           # LookupCache
│   │   ├── schemas/                # Pydantic request/response models
│   │   ├── api/
│   │   │   └── v1/
│   │   │       ├── router.py       # aggregates all routers
│   │   │       ├── auth.py
│   │   │       ├── decks.py
│   │   │       ├── cards.py
│   │   │       ├── lookup.py
│   │   │       ├── review.py
│   │   │       └── stats.py
│   │   ├── services/               # business logic, no FastAPI imports here
│   │   │   ├── auth_service.py
│   │   │   ├── deck_service.py
│   │   │   ├── card_service.py
│   │   │   ├── lookup_service.py   # orchestrates the provider chain
│   │   │   └── review_service.py
│   │   ├── telegram/
│   │   │   ├── init_data.py        # initData HMAC validation, parsing
│   │   │   ├── bot.py              # aiogram Dispatcher + Bot construction
│   │   │   ├── handlers/           # /start, /review, bare-word capture
│   │   │   ├── keyboards.py        # WebApp buttons, inline save buttons
│   │   │   └── notify.py           # daily reminder sender
│   │   ├── providers/
│   │   │   ├── base.py             # Protocols + result dataclasses
│   │   │   ├── dictionary/
│   │   │   │   ├── free_dictionary.py
│   │   │   │   └── gemini.py
│   │   │   ├── translation/
│   │   │   │   ├── azure.py
│   │   │   │   └── gemini.py
│   │   │   └── registry.py         # builds the chain from settings
│   │   └── srs/
│   │       ├── scheduler.py        # thin FSRS wrapper, pure, no I/O
│   │       └── types.py            # Rating enum, SchedulingResult
│   ├── alembic/
│   ├── tests/
│   └── pyproject.toml
├── frontend/
│   ├── src/
│   │   ├── app/
│   │   │   ├── router.tsx
│   │   │   ├── providers.tsx       # QueryClient, auth context, theme
│   │   │   └── layout/
│   │   ├── features/
│   │   │   ├── auth/               # api.ts, hooks.ts, components/, pages/
│   │   │   ├── decks/
│   │   │   ├── lookup/
│   │   │   ├── review/
│   │   │   └── stats/
│   │   └── shared/
│   │       ├── api/                # axios/fetch client, interceptors, types
│   │       ├── ui/                 # shadcn components
│   │       ├── hooks/
│   │       └── lib/
│   ├── vite.config.ts
│   └── package.json
├── docker-compose.yml
├── DECISIONS.md
└── SPEC.md
```

**Layering rule, enforced:** `api/` may import `services/` and `schemas/`.
`services/` may import `models/`, `providers/`, `srs/`. `providers/` and `srs/` import
nothing from `app/` except `core/config`. Never import `fastapi` inside `services/`.

---

## 5. Data model

All primary keys are UUIDv7 (use the `uuid6` package, `uuid7()`). All timestamps are
`TIMESTAMPTZ`, stored UTC.

### `users`
| column | type | notes |
|---|---|---|
| id | uuid | pk |
| telegram_id | bigint | unique, not null |
| username | text | nullable, changes over time — never use as identity |
| first_name | text | nullable |
| native_lang | varchar(8) | BCP-47, default from `language_code`, fallback `uz` |
| ui_lang | varchar(8) | default `uz` |
| daily_new_limit | int | default 20 |
| daily_review_limit | int | default 200 |
| lookup_quota_per_day | int | default 100 |
| timezone | varchar(48) | IANA, default `Asia/Tashkent` |
| reminder_hour | smallint | local hour, default 20, null disables |
| reminder_enabled | bool | default true |
| is_active | bool | default true |
| created_at | timestamptz | |

### `decks`
| column | type | notes |
|---|---|---|
| id | uuid | pk |
| user_id | uuid | fk → users, on delete cascade |
| name | text | not null |
| source_lang | varchar(8) | the language being learned |
| target_lang | varchar(8) | the language meanings are shown in |
| kind | enum | `normal` \| `daily` |
| daily_date | date | null unless `kind='daily'` |
| archived_at | timestamptz | null |
| created_at | timestamptz | |

Unique partial index: `(user_id, daily_date) WHERE kind = 'daily'`.
Index: `(user_id, archived_at)`.

### `cards`
| column | type | notes |
|---|---|---|
| id | uuid | pk |
| deck_id | uuid | fk → decks, on delete cascade |
| user_id | uuid | denormalized, for cheap user-scoped queries |
| term | text | the word as saved, normalized (trimmed, casefolded unless proper noun) |
| display_term | text | as the user typed it |
| ipa | text | nullable |
| pos | varchar(32) | part of speech, nullable |
| meanings | jsonb | see shape below, not null |
| examples | jsonb | see shape below, default `[]` |
| note | text | user's own note, nullable |
| source_lang | varchar(8) | copied from deck at creation |
| target_lang | varchar(8) | copied from deck at creation |
| created_at | timestamptz | |

Unique index: `(deck_id, term)` — no duplicates within a deck.

`meanings` shape — an array, order preserved, this is what the user selected at save time:
```json
[
  { "pos": "verb", "definition": "yugurmoq", "gloss_en": "to move at a speed faster than walking" },
  { "pos": "noun", "definition": "yugurish", "gloss_en": "an act of running" }
]
```

`examples` shape:
```json
[
  { "text": "He ran to the station.", "translation": "U vokzalgacha yugurdi.", "source": "user" }
]
```
`source` is `user` when captured from the book the reader is holding, `provider` otherwise.
Prefer showing the user's own sentence first — context from real reading is the whole point.

### `card_states`
One row per card, 1:1. Created together with the card.

| column | type | notes |
|---|---|---|
| card_id | uuid | pk, fk → cards, on delete cascade |
| user_id | uuid | denormalized |
| due | timestamptz | not null, indexed |
| stability | double precision | |
| difficulty | double precision | |
| elapsed_days | int | |
| scheduled_days | int | |
| reps | int | default 0 |
| lapses | int | default 0 |
| state | smallint | FSRS state: 0 new, 1 learning, 2 review, 3 relearning |
| last_review | timestamptz | nullable |
| suspended | bool | default false |

Index: `(user_id, due) WHERE suspended = false`.

### `review_logs`
Append-only. Never update, never delete.

| column | type | notes |
|---|---|---|
| id | uuid | pk |
| card_id | uuid | fk → cards, on delete cascade |
| user_id | uuid | |
| rating | smallint | 1 again, 2 hard, 3 good, 4 easy |
| state | smallint | state **before** the review |
| due | timestamptz | due **before** the review |
| stability | double precision | before |
| difficulty | double precision | before |
| elapsed_days | int | |
| last_elapsed_days | int | |
| scheduled_days | int | |
| reviewed_at | timestamptz | |

This table exists so FSRS's optimizer can later fit per-user parameters. It cannot be
reconstructed after the fact. Write to it on **every** review from day one.

### `lookup_cache`
**Global, not per-user.** This is the single most important cost control in the system.

| column | type | notes |
|---|---|---|
| id | uuid | pk |
| term | text | normalized |
| source_lang | varchar(8) | |
| target_lang | varchar(8) | |
| provider | varchar(32) | which chain produced it |
| payload | jsonb | the full LookupResult |
| hit_count | int | default 0 |
| created_at | timestamptz | |

Unique index: `(term, source_lang, target_lang)`.

---

## 6. Provider layer

### Contracts (`providers/base.py`)

```python
from typing import Protocol
from dataclasses import dataclass, field

@dataclass
class Meaning:
    pos: str | None
    definition: str          # in target_lang
    gloss_en: str | None     # original English definition, if available
    examples: list[str] = field(default_factory=list)

@dataclass
class LookupResult:
    term: str
    source_lang: str
    target_lang: str
    ipa: str | None
    meanings: list[Meaning]
    provider: str

class DictionaryProvider(Protocol):
    name: str
    def supports(self, source_lang: str) -> bool: ...
    async def lookup(self, term: str, source_lang: str) -> LookupResult | None: ...

class TranslationProvider(Protocol):
    name: str
    async def translate(
        self, texts: list[str], source_lang: str, target_lang: str
    ) -> list[str]: ...
```

### The pipeline (`services/lookup_service.py`)

```
normalize(term)
  → Redis GET  (TTL 24h)           → hit? return
  → lookup_cache SELECT            → hit? warm Redis, increment hit_count, return
  → provider chain
  → persist to lookup_cache + Redis
  → return
```

**Chain selection is language-aware:**

- `source_lang == "en"` → `FreeDictionaryProvider` (dictionaryapi.dev, keyless, no
  quota, ~150ms). It returns English definitions, POS, IPA, examples. Then batch the
  definitions and examples into **one** `TranslationProvider.translate()` call to
  produce `target_lang` text. Keep the English gloss in `gloss_en`.
- `source_lang != "en"` → `GeminiDictionaryProvider`. This is the only path that
  produces structured multi-meaning output for arbitrary source languages. Use
  structured output with a hard JSON schema — never parse free text.
- Any provider raising or timing out (>4s) → fall through to the next. If the whole
  chain fails, return HTTP 503 with a retryable error code. Never return a partial
  or invented result.

**Uzbek quality note:** Uzbek is the primary target language and general NMT handles it
unevenly. When `target_lang == "uz"`, prefer the Gemini path even for English source
words if `settings.UZ_PREFER_LLM` is true. Make this a config flag, measure both, and
record the outcome in `DECISIONS.md`.

### HTTP client

Create **one** `httpx.AsyncClient` in the FastAPI lifespan with
`limits=httpx.Limits(max_keepalive_connections=20)` and store it on `app.state`.
Every provider receives it via constructor injection. Creating a client per request
adds 200–300ms of TLS handshake and defeats the entire latency goal. Do not do it.

---

## 7. API contract

Base path `/api/v1`. All responses JSON. Errors use one envelope:

```json
{ "error": { "code": "quota_exceeded", "message": "…", "details": {} } }
```

### Auth
| method | path | notes |
|---|---|---|
| POST | `/auth/telegram` | body `{init_data}` → `{access_token}`, upserts the user |
| GET | `/auth/me` | current user + settings |
| PATCH | `/auth/me` | update `native_lang`, limits, timezone, reminder settings |

**initData validation** (`telegram/init_data.py`) — implement exactly:

1. Parse the raw query string. Pull out `hash`, keep every other key.
2. Build the data-check string: remaining keys sorted alphabetically, joined as
   `key=value` with `\n`.
3. `secret_key = HMAC_SHA256(key=b"WebAppData", msg=bot_token)`.
4. Expected hash = `HMAC_SHA256(key=secret_key, msg=data_check_string).hexdigest()`.
5. Compare with `hmac.compare_digest`. Never `==`.
6. Reject if `auth_date` is older than 24 hours.

Only after all six steps may `user` be trusted. Never read `initDataUnsafe` on the
server, and never accept a `telegram_id` sent directly in a request body.

On success, upsert by `telegram_id` and issue a session JWT (24h, `Authorization:
Bearer`). Every other endpoint takes the JWT, not initData — initData goes stale and
re-validating it per request wastes the freshness check. The frontend re-calls
`/auth/telegram` on 401.

### Decks
| method | path | notes |
|---|---|---|
| GET | `/decks` | user's decks + card counts + due counts |
| POST | `/decks` | `{name, source_lang, target_lang}` |
| GET | `/decks/{id}` | |
| PATCH | `/decks/{id}` | rename, archive |
| DELETE | `/decks/{id}` | cascades |
| GET | `/decks/daily` | today's daily deck, created if absent |

### Lookup
| method | path | notes |
|---|---|---|
| POST | `/lookup` | `{term, source_lang, target_lang}` → `LookupResult` |

Never writes a card. Pure read + cache. Rate limited and quota'd.

### Cards
| method | path | notes |
|---|---|---|
| POST | `/cards` | `{deck_id?, term, meanings[], examples[], note?}` — omitting `deck_id` targets today's daily deck |
| GET | `/decks/{id}/cards` | paginated, cursor-based |
| PATCH | `/cards/{id}` | edit meanings, note, move deck |
| DELETE | `/cards/{id}` | |
| POST | `/cards/{id}/suspend` | toggles `card_states.suspended` |

### Review
| method | path | notes |
|---|---|---|
| GET | `/review/queue` | `?deck_id=&limit=` → ordered queue for this session |
| POST | `/review/answer` | **batch**: `[{card_id, rating, reviewed_at}]` |
| GET | `/review/counts` | new / learning / due counts, per deck and total |

`GET /review/queue` returns the full session up front — card content plus current
state. `POST /review/answer` accepts an array so the frontend can flush every few
answers instead of round-tripping per card. Answers carry client `reviewed_at`;
the server clamps it to `[now - 10min, now]` to prevent clock abuse.

### Stats
| method | path | notes |
|---|---|---|
| GET | `/stats/overview` | streak, reviews per day (90d), retention rate, total cards |

### Bot
| method | path | notes |
|---|---|---|
| POST | `/telegram/webhook/{secret}` | aiogram update handler, not under `/api/v1` |

`{secret}` is a random path segment from settings, and the request must also carry a
matching `X-Telegram-Bot-Api-Secret-Token` header. Reject anything else with 403
before parsing the body.

---

## 8. Cost and abuse controls

The app is public and lookups cost money. All of the following are mandatory.

1. **Global lookup cache** (§5). Cross-user. Expect 40–60% hit rate once a few hundred
   users are reading similar material.
2. **Per-user daily lookup quota** — `users.lookup_quota_per_day`, default 100, counted
   in Redis with a key expiring at the user's local midnight. Cache hits do **not**
   count against quota; only calls that reach a provider do.
3. **Rate limit** — 20 lookups/minute per user, 60 requests/minute per IP on auth
   endpoints. Return 429 with `Retry-After`.
4. **Input validation on `/lookup`** — reject terms longer than 64 characters or
   containing more than 4 whitespace-separated tokens. This app looks up words and
   short phrases. Rejecting paragraphs is what stops it from becoming a free
   translation proxy, which is the realistic abuse vector.
5. **No email verification exists here**, so the remaining controls carry more weight.
   Tighten them: new accounts (<24h old) get a reduced quota of 30 lookups/day.
   Telegram accounts younger than the bot's own launch are not distinguishable, so do
   not attempt account-age heuristics beyond your own `users.created_at`.
6. **Global daily provider budget** — a hard ceiling in settings. When exceeded, serve
   cache only and return `provider_budget_exceeded` for misses. Log loudly.

---

## 9. FSRS integration

`srs/scheduler.py` wraps py-fsrs and contains no database or HTTP code. It takes
current state + rating + timestamp and returns the next state and a log record.

```python
def schedule(state: CardStateSnapshot, rating: Rating, now: datetime) -> SchedulingResult
```

Rules:
- New cards enter the queue subject to `users.daily_new_limit`.
- Queue ordering: learning/relearning cards first (they are time-sensitive), then
  due review cards oldest-first, then new cards up to the daily limit.
- `POST /review/answer` runs in one transaction per batch: update `card_states`,
  insert `review_logs`.
- Store FSRS parameters per user in a `users.fsrs_params jsonb` column, nullable.
  Null means library defaults. Do not implement the optimizer in v1 — just make the
  column exist so review logs stay useful.

---

## 9a. Telegram bot

Run aiogram in **webhook** mode, mounted on the same FastAPI app and the same process.
Do not run a second service, and do not use polling in production.

**Handlers:**
- `/start` — upsert user, short Uzbek greeting, a persistent reply keyboard with a
  `WebAppInfo` button labeled "Memorani ochish".
- `/review` — reply with due counts and a WebApp button that deep-links straight into
  the review screen (`?startapp=review`).
- `/settings` — reminder hour on/off, language pair defaults.
- **Bare text message** — treat as a lookup. Apply the same §8 validation (≤64 chars,
  ≤4 tokens) and the same quota. Reply with meanings and inline buttons:
  one button per meaning to toggle selection, then "Saqlash". Save to today's daily
  deck. Edit the message in place on each toggle rather than sending new messages.

**Daily reminder** (`telegram/notify.py`): an APScheduler job inside the API process
running hourly. Each run selects users whose local time now matches `reminder_hour`,
who have `reminder_enabled`, and who have due cards. Send one message with the due
count and a WebApp button. Respect Telegram's limits — chunk sends at ~25/second and
handle `TelegramForbiddenError` by setting `is_active = false` (user blocked the bot).

Never send a reminder to a user with zero due cards. An empty reminder is the fastest
way to get blocked.

---

## 10. Frontend (Mini App)

### Screens

There is no login screen and no onboarding wall. The first screen a user ever sees is
Decks, already authenticated, with today's daily deck created and empty.

1. **Decks** — list of decks, each showing name, language pair, card count, due count.
   Today's daily deck pinned at top. Primary action: a persistent lookup input.
2. **Lookup** — the input is always reachable, keyboard-focusable from anywhere via `/`.
   Types a word → result appears → each meaning is a selectable chip → user picks
   which meanings to keep → optionally pastes the sentence from the book → saves to a
   deck (defaults to today's daily deck).
3. **Deck detail** — card list, search, edit, move, delete.
4. **Review** — the focus mode. One card, flip, four ratings.
5. **Stats** — streak, activity heatmap, retention.

### Mini App integration

Initialize the SDK before anything renders. On mount:

```
init()
ready()            // tells Telegram to hide the loading placeholder
expand()           // full height, otherwise the app opens half-screen
disableVerticalSwipe()
```

**`disableVerticalSwipe()` is not optional.** Without it, a downward drag anywhere —
including on a review card — closes the Mini App. On iOS this happens constantly and
users lose their session mid-review.

Other rules:
- **BackButton** — use Telegram's native back button, driven by the router. Do not
  draw your own back arrow anywhere.
- **MainButton** — use it for the single primary action of a screen: "Saqlash" on the
  lookup screen, "Takrorlashni boshlash" on a deck. Do not use it in review; the
  rating ladder is the action there.
- **HapticFeedback** — fire `impactOccurred('light')` on card flip and
  `notificationOccurred` on rating. This is the cheapest quality signal available in a
  Mini App and it costs three lines.
- **Theme** — read `colorScheme` (`light` | `dark`) and switch the palette below.
  Do **not** consume Telegram's individual `themeParams` colors; they vary per client
  and would dissolve the design into generic Telegram chrome. Match the mode, keep
  the identity.
- **Viewport** — never use `100vh`. Use `viewportStableHeight` from the SDK. `100vh`
  is wrong in the Telegram webview whenever the keyboard opens, which on the lookup
  screen is always.
- **Deep links** — read `startapp` on launch and route accordingly (`review` opens
  the review session directly). The bot's reminder button depends on this.
- **CloudStorage** — use for trivial client prefs only (last used deck). Never for
  card data; the backend is the source of truth.

### Design direction

The subject is words captured off a paper page while reading. Two modes, deliberately
different: browsing feels like a notebook, reviewing feels like a dark room with one
lamp on.

**Palette** — drawn from Uzbek suzani and ikat dyework, not from generic SaaS.
In light mode `--paper` is the ground; in dark mode `--ink` is. Review mode uses
`--ink` in both, deliberately — the focus screen is always the dark room.
- `--ink` `#161A2B` — near-black indigo, review-mode ground
- `--paper` `#FBF7F0` — warm off-white, browsing ground
- `--indigo` `#2E4374` — primary
- `--madder` `#B4432E` — "Again", errors, destructive
- `--saffron` `#E0A32E` — accent, streaks, the signature
- `--sage` `#6E8B6B` — "Easy", success

**Type** — three roles, chosen for full Latin-extended + Cyrillic + IPA coverage,
which matters here because the app must render Uzbek, Russian, and phonetic notation:
- Display: **Bricolage Grotesque** (variable) — headings, and the term on a review card
- Body: **Source Sans 3** — UI and definitions
- Utility: **JetBrains Mono** — IPA, language codes, counts

Set the review-card term at a large optical size with tight tracking; set definitions
noticeably smaller and lighter. The gap between them is what makes a card scannable in
under a second.

**Signature element** — the rating control is not four equal buttons. It is a
horizontal **confidence ladder**: a single continuous track from madder to sage, with
four stops, the next-due interval printed under each stop. The user sees the
consequence of the answer before choosing it. Everything else on the review screen is
silent — no chrome, no nav, no progress bar competing for attention. Spend the
boldness here and nowhere else.

**Motion** — one orchestrated moment: the card flip. Reduced-motion respected, in
which case it cross-fades. No scroll reveals, no ambient effects.

### Copy rules
Uzbek UI, sentence case, active voice. Action names stay constant through the flow:
the button says "Saqlash", the toast says "Saqlandi". Empty states are invitations —
an empty deck says what to do next, not "Ma'lumot yo'q".

### Frontend rules
- All server state through TanStack Query. No `useEffect` fetching.
- Zustand holds only the in-flight review session: queue, index, pending answers.
- Flush pending answers to `/review/answer` every 5 answers and on session end and on
  `visibilitychange`. Never block the UI on the flush.
- Optimistic UI on rating: advance to the next card immediately.
- The lookup input debounces at 300ms but only fires on explicit submit — no
  search-as-you-type. Every keystroke fired at a paid API is money burned.

---

## 11. Milestones

Build in this order. Do not start a milestone before the previous one's acceptance
criteria pass.

**M0 — Skeleton.** Compose file up, FastAPI serving `/health`, Postgres reachable,
Alembic initialized, Vite dev server proxying `/api`.
*Accept:* `docker compose up` gives a green health check and a rendered React page.

**M1 — Telegram auth + decks.** initData validation with unit tests over known-good and
tampered payloads, session JWT, user upsert, deck CRUD, daily deck creation.
*Accept:* a tampered initData hash is rejected; a valid one returns a token that opens
deck endpoints. Test the validator against a fixture, not a live bot.

**M2 — Lookup.** Provider contracts, FreeDictionary, Azure translation, Gemini
fallback, both cache layers, quota and rate limiting.
*Accept:* `POST /lookup` for `run` (en→uz) returns ≥3 meanings in <500ms cold and
<50ms warm. A second identical request from a *different* user hits cache.

**M3 — Cards.** Save from a lookup result, card CRUD, `card_states` created on save.
*Accept:* saving twice into one deck is rejected with a clear error.

**M4 — Review.** FSRS wrapper, queue endpoint, batch answers, review logs.
*Accept:* a card rated `again` reappears in the same session; a card rated `easy`
schedules days out; `review_logs` has one row per answer.

**M5 — Mini App.** All five screens against the real API, SDK integration per §10,
BackButton/MainButton/haptics wired, deep links handled.
*Accept:* full loop inside the real Telegram client on a phone — open from the bot,
look up a word, save it, review it. Dragging down on a review card does not close the
app. Opening the keyboard does not break the layout.

**M6 — Bot.** Webhook mount, `/start`, `/review`, bare-word capture with inline save,
daily reminder scheduler.
*Accept:* sending `serendipity` to the bot returns meanings and saves to today's daily
deck; the card is immediately visible in the Mini App.

**M7 — Stats + polish.** Overview endpoint, heatmap, streaks, empty states, error
states.

---

## 12. Conventions

- Type hints on every function. `mypy --strict` on `app/services`, `app/providers`,
  `app/srs`.
- `ruff` for lint and format. Line length 100.
- Every endpoint gets at least one test. Providers are tested against recorded
  fixtures, never live APIs.
- Migrations are generated by Alembic and reviewed by hand. Never `create_all()`.
- No secrets in code. All config through `Settings`. Ship `.env.example`.
- Structured JSON logging. Log every provider call with provider name, latency,
  cache status, and whether it counted against quota. Never log full lookup payloads.
- Commit per milestone with a message naming the milestone.

### Required environment variables

```
DATABASE_URL=
REDIS_URL=
JWT_SECRET=
TELEGRAM_BOT_TOKEN=
TELEGRAM_WEBHOOK_SECRET=
TELEGRAM_WEBHOOK_PATH_SECRET=
MINI_APP_URL=
AZURE_TRANSLATOR_KEY=
AZURE_TRANSLATOR_REGION=
GEMINI_API_KEY=
UZ_PREFER_LLM=true
DAILY_PROVIDER_BUDGET=5000
```

---

## 13. Things that will go wrong if ignored

- **Per-request `httpx.AsyncClient`.** Kills the latency target. §6.
- **Per-user lookup cache.** Multiplies cost by user count. The cache is global. §5.
- **Skipping `review_logs` early.** The data cannot be recovered later and the
  optimizer becomes impossible. §5.
- **FSRS fields on `cards`.** Merging content and scheduling state makes algorithm
  changes and full-deck resets painful. Keep `card_states` separate. §5.
- **Unbounded `/lookup` input.** Turns the app into a free translation proxy and the
  bill arrives at the end of the month. §8.
- **Search-as-you-type on lookup.** Same problem, self-inflicted. §10.
- **Trusting `initDataUnsafe` or a client-sent `telegram_id`.** Anyone can post any
  user id. Validate the HMAC server-side or you have no auth at all. §7.
- **Skipping `disableVerticalSwipe()`.** Users lose review sessions by scrolling. §10.
- **`100vh` anywhere.** Breaks the moment the keyboard opens. §10.
- **Using `username` as identity.** It is mutable and can be transferred between
  accounts. `telegram_id` is the key. §5.
- **Reminders to users with nothing due.** Fastest path to getting blocked. §9a.
