# Memora

A multilingual vocabulary app delivered as a **Telegram Mini App**. Look up unknown
words while reading, save the meanings worth keeping into decks, review them with FSRS
scheduling.

`SPEC.md` is the source of truth. `DECISIONS.md` records every choice the spec left
open, `BLOCKERS.md` what still needs credentials, `MANUAL_TESTS.md` what only a human
on a phone can check, and `PROGRESS.md` the milestone-by-milestone build log.

---

## Run it

```bash
cp .env.example .env      # fill in what you have; the app boots without any of it
docker compose up -d --build
curl http://localhost:8000/health
```

- Mini App (through nginx) — http://localhost:8080
- API — http://localhost:8000, docs at `/docs`
- Postgres — `localhost:5433`, Redis — `localhost:6380`
  (non-standard ports so a local Postgres/Redis does not shadow them; see DECISIONS D6)

Without a `TELEGRAM_BOT_TOKEN` the bot stays unmounted and the app serves normally.
Without provider keys the fixture-backed `Fake*` providers answer lookups, so the whole
pipeline still runs end to end.

## Develop

```bash
# backend
cd backend
uv sync --all-groups
uv run uvicorn app.main:app --reload
uv run alembic upgrade head

# frontend
cd frontend
npm install
npm run dev            # proxies /api to localhost:8000
```

## Verify

```bash
cd backend
uv run ruff check . && uv run ruff format --check .
uv run mypy app/services app/providers app/srs app/telegram
uv run pytest -q                  # needs `docker compose up -d db redis`

cd frontend
npm run lint && npx tsc --noEmit && npm run build
```

Tests run against a dedicated `memora_test` database and Redis DB 15, both created
automatically. Providers are exercised against recorded fixtures, never live APIs.

## Shape

```
backend/app/
  api/v1/       endpoints            services/   business logic, no FastAPI imports
  core/         config, auth, errors providers/  dictionary + translation chain
  models/       SQLAlchemy 2.0       srs/        FSRS wrapper, pure
  telegram/     initData, bot, reminders
frontend/src/
  app/          router, providers, layout
  features/     auth · decks · lookup · review · stats
  shared/       api client, ui kit, Telegram SDK integration
```

`api/` may import `services/` and `schemas/`. `services/` may import `models/`,
`providers/`, `srs/`. `providers/` and `srs/` import nothing from `app/` beyond
`core/config`. `fastapi` is never imported inside `services/`.
