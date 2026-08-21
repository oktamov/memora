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

## Deploy to a server

One command. It is idempotent — run it again to redeploy.

```bash
curl -fsSL https://raw.githubusercontent.com/oktamov/memora/main/deploy/deploy.sh | sudo bash
```

With credentials, so the bot and the real providers come up too:

```bash
curl -fsSL https://raw.githubusercontent.com/oktamov/memora/main/deploy/deploy.sh \
  | sudo TELEGRAM_BOT_TOKEN=... GEMINI_API_KEY=... bash
```

**It publishes no host ports.** The target server already runs another project whose
Caddy owns 80/443 and whose API owns 8000, so Memora is reachable only through that
Caddy over a shared `memora_edge` network. The script connects the two, appends a
marked site block to the existing Caddyfile, validates it, and reloads without a
restart. If validation fails it restores the backup, so a mistake here cannot take the
other project down.

Secrets are generated on the first run and preserved afterwards — rotating
`JWT_SECRET` would sign every user out.

| Variable | Default | Meaning |
|---|---|---|
| `MEMORA_DOMAIN` | `memora.uz` | the domain to serve |
| `CADDY_CONTAINER` | `dublyaj-caddy` | the existing reverse proxy to extend |
| `MEMORA_DIR` | `/opt/memora` | where the code lives |
| `MEMORA_BRANCH` | `main` | branch to deploy |

If the repository is private, or you want to deploy uncommitted work, skip GitHub
entirely and push the working tree over SSH instead:

```bash
./deploy/ship.sh root@your-server
```

## CI / CD

`.github/workflows/deploy.yml` runs on every push to `main`: lint, types, 203 tests and
a migration-drift check on the backend; lint, types and a production build on the
frontend. Only if all of that passes does it SSH to the server and run `deploy.sh`,
then poll `https://memora.uz/health` until the site answers — a deploy that leaves the
site down fails the run rather than going green.

Pull requests run the same checks without deploying. Documentation-only pushes are
skipped entirely.

### One-time setup

Generate a key pair for the runner:

```bash
ssh-keygen -t ed25519 -C "github-actions-memora" -f ~/.ssh/memora_deploy -N ""
ssh-copy-id -i ~/.ssh/memora_deploy.pub root@168.119.187.64
ssh-keyscan -H 168.119.187.64            # for SSH_KNOWN_HOSTS
```

Then in **Settings → Secrets and variables → Actions**:

| Kind | Name | Value |
|---|---|---|
| Secret | `SSH_PRIVATE_KEY` | contents of `~/.ssh/memora_deploy` |
| Secret | `SSH_HOST` | `168.119.187.64` |
| Secret | `SSH_USER` | `root` |
| Secret | `SSH_KNOWN_HOSTS` | output of the `ssh-keyscan` above |
| Variable | `APP_DIR` | `/var/www/memora` (optional, this is the default) |
| Variable | `MEMORA_DOMAIN` | `memora.uz` (optional, this is the default) |

`SSH_KNOWN_HOSTS` is optional but worth setting: without it the runner trusts whatever
answers on first contact, and the workflow prints a warning saying so.

### Only what changed gets rebuilt

`deploy.sh` runs `docker compose build`, and Docker's layer cache means a frontend-only
push does not rebuild the Python dependency layer, and vice versa. Containers whose
image did not change are left running untouched.

### Hardening worth considering

The deploy key is a root key held by GitHub, so anyone who can push to `main` can run
anything on the server. To narrow that, restrict the key in the server's
`~/.ssh/authorized_keys` so it can only run the deploy:

```
command="cd /var/www/memora && MEMORA_DIR=$PWD bash deploy/deploy.sh",no-port-forwarding,no-pty ssh-ed25519 AAAA...
```

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
