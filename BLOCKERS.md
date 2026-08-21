# Blockers

Everything that needs a human with credentials or a physical device. Each entry states
exactly what is needed and what was built in the meantime.

---

## B1 — Telegram bot token (`TELEGRAM_BOT_TOKEN`)

**Needed:** create a bot with [@BotFather](https://t.me/BotFather), copy the token into
`.env` as `TELEGRAM_BOT_TOKEN`. Then `/setmenubutton` (or `/newapp`) pointing at
`MINI_APP_URL` so the Mini App can be opened from the chat.

**Meanwhile:** the bot is fully implemented. `Settings.bot_enabled` is false while the
token is empty, so the webhook route is not mounted and the app boots cleanly without
it. `initData` validation is tested against a fixture signed with a dummy token
(`tests/factories.py`), covering SPEC §7 end to end without a live bot.

## B2 — Public HTTPS origin (`MINI_APP_URL`, webhook)

**Needed:** Telegram will only open a Mini App and only deliver webhooks over HTTPS on a
public host. Point a domain (or an ngrok/Cloudflare tunnel) at the `nginx` service, set
`MINI_APP_URL`, then register the webhook at
`https://<host>/telegram/webhook/<TELEGRAM_WEBHOOK_PATH_SECRET>` with
`secret_token=<TELEGRAM_WEBHOOK_SECRET>`.

**Meanwhile:** the webhook handler, its path secret and its
`X-Telegram-Bot-Api-Secret-Token` header check are implemented and unit-tested against
the ASGI app directly.

## B3 — Azure Translator key (`AZURE_TRANSLATOR_KEY`, `AZURE_TRANSLATOR_REGION`)

**Needed:** an Azure Translator resource; copy key and region into `.env`. Optional —
Gemini alone covers every language pair. Azure's Dictionary Lookup is faster and cheaper
for the pairs it supports (all involving English), so it runs ahead of Gemini when
configured.

**Meanwhile:** `providers/translation/azure.py` is complete and correct against the
Azure Translator v3.0 `/translate` contract. When the key is absent,
`providers/registry.py` selects `FakeTranslationProvider`, which returns deterministic
fixture text. Tests run against the fake and against recorded Azure fixtures — never
against the live API.

## B4 — Gemini API key (`GEMINI_API_KEY`)

**Needed:** a Google AI Studio key in `.env`.

**Meanwhile:** `providers/dictionary/gemini.py` is complete, using structured output
with a hard JSON response schema (never free-text parsing), and is covered by tests
against recorded envelopes. Absent the key, `FakeDictionaryProvider` serves fixtures.
The `UZ_PREFER_LLM` comparison SPEC §6 asks for cannot be run until a key exists; the
gap and the exact procedure to close it are written up in `DECISIONS.md` D7.

## B5 — A physical phone running Telegram

**Needed:** for M5 and M6 acceptance. `disableVerticalSwipe()`, keyboard behaviour and
haptics cannot be verified in a desktop browser.

**Meanwhile:** every item is implemented per SPEC §10 and written up as a numbered
checklist in `MANUAL_TESTS.md`.
