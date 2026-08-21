
## D6 — Compose publishes Postgres on host `5433` and Redis on `6380`
A local Postgres and Redis already own `5432`/`6379` on the development machine, and
they shadow the published container ports, so host-side tooling (Alembic autogenerate,
`pytest`) silently connects to the wrong server. **Choice:** publish `5433:5432` and
`6380:6379`. Inside the Compose network the services still talk on `db:5432` and
`redis:6379`, so nothing about the deployed configuration changes.

## D7 — `UZ_PREFER_LLM` ships **on**, and the comparison SPEC §6 asks for is unmeasured
SPEC §6 asks for both Uzbek paths to be measured and the outcome recorded here.
Neither `GEMINI_API_KEY` nor `AZURE_TRANSLATOR_KEY` is available in this environment
(BLOCKERS.md B3, B4), so no honest measurement exists yet — and inventing one would be
worse than admitting the gap. **Choice:** default `UZ_PREFER_LLM=true`, matching the
spec's own reasoning that general NMT handles Uzbek unevenly and that a structured
bilingual model call avoids a lossy English pivot. The flag is read per request, so
flipping it needs no redeploy. **To measure once keys exist:** run the same 50-word
list through `/lookup` with the flag on and off, compare Uzbek definition quality by
hand, and replace this paragraph with the result.

## D8 — An unknown word is `404 term_not_found`, not `503`
SPEC §6 requires a retryable 503 when the *chain fails*. A provider answering "this
word does not exist" is not a failure — the chain worked. **Choice:** track the two
outcomes separately. Every provider erroring → 503 `provider_unavailable` with
`retryable: true`. At least one provider answering honestly with nothing, and no errors
→ 404 `term_not_found`. Returning 503 for a typo would tell the user to retry forever.

## D9 — `normalize_term` casefolds unconditionally
SPEC §5 says card terms are "trimmed, casefolded unless proper noun", but the cache key
has to be stable — `Run`, `run` and `RUN` must be one entry or the cache's hit rate
drops for no benefit. **Choice:** the lookup and cache key are always casefolded, and
the user's own capitalisation survives on the card as `display_term` (SPEC §5), which
is where it actually matters.

## D10 — The `en → target` path keeps the English text in `gloss_en`
`FreeDictionaryProvider` fills both `definition` and `gloss_en` with the English text;
`lookup_service` then overwrites `definition` with the translated string and leaves
`gloss_en` alone. This keeps the provider a pure dictionary with no translation
knowledge, and satisfies SPEC §6's "keep the English gloss in `gloss_en`" with a single
batched translation call per lookup.

## D11 — The `Card → CardState` relationship is named `card_state`, not `state`
`CardResponse.state` carries the scheduling state in the API. With the ORM
relationship also called `state`, pydantic's `model_validate(card)` reached for the
`lazy="raise"` relationship while serialising and blew up on every card response.
**Choice:** name the relationship `card_state`; the API field stays `state`, so the
wire contract is untouched.

## D12 — Error messages snapshot their ingredients before the write
A failed flush expires every ORM object in the session, so reading `deck.id` or
`card.display_term` *inside* the `except IntegrityError` block attempts lazy IO outside
the async greenlet and raises `MissingGreenlet` instead of the intended 409.
**Choice:** copy what the error message needs into plain locals before `commit()`.
This is why `create_card` and `update_card` both hoist those reads.

## D13 — Card list pagination is keyset, not offset
SPEC §7 says cursor-based. The cursor is the card's UUIDv7, base64url-encoded — v7 ids
are time-ordered, so `id < cursor` with `ORDER BY id DESC` is a correct newest-first
keyset with no extra sort column. Offsets would drift every time a card is saved
mid-scroll, which on this screen is the normal case.

## D14 — Learning cards have a 20-minute learn-ahead window
SPEC §11 M4 requires a card rated `again` to reappear in the **same** session, but FSRS
puts the first learning step about a minute out, so a strict `due <= now` queue could
never show it again — the acceptance criterion and the query contradict each other.
**Choice:** learning and relearning cards count as due when
`due <= now + 20 minutes`. Anki solves the same problem the same way (its "learn ahead
limit"). The window deliberately does **not** apply to review cards: those are days
apart and pulling them forward would defeat the scheduling. `review_service.counts()`
uses the identical predicate so the badge and the queue never disagree.

## D15 — A batch of answers is applied in the order the client sent it
SPEC §7 makes `/review/answer` a batch endpoint, which means one card can legitimately
appear twice in a batch — rated `again`, shown again, then rated `good`. **Choice:**
iterate the answers in order, each scheduling from the state the previous one produced,
inside the single transaction. Deduplicating or applying them in parallel would compute
the second answer from a stale state and write a `review_logs` row that never happened.

## D16 — The client reads raw `initData`; it never depends on parsing it
`retrieveLaunchParams()` validates the *parsed* initData against a strict schema — the
installed SDK requires a `signature` field, for one — and throws the entire result away
if any single field is missing or newly added by Telegram. That took `initDataRaw` with
it, so the app silently never authenticated. Caught by driving the real Mini App in a
browser against the real API.
**Choice:** try the SDK first, then fall back to reading `tgWebAppData` straight from
the launch hash or Telegram's cached launch parameters. The raw string is the only
thing we send onward, and its authenticity is established by the server's HMAC check
(SPEC §7) — never by a client-side shape check. A parser one Telegram release behind
would otherwise lock every user out of an app that has no other way in.

## D17 — `isTMA()` decides only whether SDK components mount
Same incident, second cause. The environment probe is deliberately conservative and
answers false in clients that did launch us with real parameters. Gating initData
retrieval behind it dropped authentication for those users. **Choice:** the probe now
decides only whether the SDK's components are mounted; launch parameters are read
unconditionally.

## D18 — `index.html` is served `no-cache`; hashed assets stay immutable
A browser-cached `index.html` kept pointing at a bundle from a previous build, so a
redeploy appeared to change nothing. **Choice:** `Cache-Control: no-cache,
must-revalidate` on `index.html` and every SPA fallback route; `immutable` stays on
`/assets/` since those filenames are content-hashed. Without this, a Mini App update
reaches users only when their webview happens to evict the entry.

## D19 — Ladder intervals are estimated client-side
SPEC §10 requires the next-due interval under each of the four stops. Answering exactly
would mean running FSRS four times per card on the server and shipping all four
outcomes with the queue. **Choice:** estimate from the card's current stability in the
client. The ladder exists so the user senses the consequence before choosing; the
authoritative interval comes back from `/review/answer` and is what actually gets
stored. Should the estimate ever need to be exact, the queue response is where the four
values would go.

## D20 — Pending bot lookups live in Redis under a short token
Telegram caps callback data at 64 bytes, and a chat message carries no state, so the
lookup result and the user's running selection cannot ride along in the buttons.
**Choice:** stage them in Redis under a URL-safe token with a one-hour TTL. The token
is what appears in the callback payload. Every callback re-checks that the token
belongs to the pressing user, so forwarding the message does not hand someone else's
buttons over. An abandoned lookup expires on its own.

## D21 — `/settings` covers the reminder; the rest lives in the Mini App
SPEC §9a asks `/settings` for "reminder hour on/off, language pair defaults". The
reminder controls are genuinely faster in chat — two taps while the phone is already
open on the conversation. Language pair defaults are a per-deck concern the Mini App
already exposes properly, and rebuilding a language picker out of inline buttons would
be a worse version of a screen that exists. **Choice:** the bot owns the reminder
toggle and hour; `/settings` says in one line that the rest is in the app.

## D22 — Reminder recipients come from a single query with the due count joined in
SPEC §13 lists "reminders to users with nothing due" as the fastest way to get blocked.
**Choice:** "has due cards" is a join condition, not a check performed after the send
has started, and the count carried in the message is the same `due <= now` predicate
the review queue uses — so the number the user reads is the number they will see. The
local-hour comparison stays in Python because it depends on each user's IANA zone;
the reminder-enabled population is small enough that this is cheaper than a per-row
`AT TIME ZONE`.

## D23 — Retention counts only review-state answers
SPEC §7 asks for a "retention rate" without defining the denominator. **Choice:**
the share of answers on cards already in the `review` state that were not rated
`again`. New and learning cards are excluded deliberately — failing a card you are
still learning is the algorithm working, not a memory lapse, and counting those would
push the number down hardest for the users studying most. `hard` counts as remembered,
since the card was recalled. Before any review-state answer exists the value is `null`,
not `0.0`: no data and perfect failure should not look the same.

## D24 — Today not being reviewed yet does not break the streak
A streak measured strictly to today would read zero every morning until the user opens
the app, which is both wrong and discouraging. **Choice:** if today has no reviews, the
run is measured from yesterday. Two consecutive empty days end it. This is what every
SRS app does and what a user expects to see at 9am.

## D25 — The activity series always returns all 90 days, zeros included
The heatmap needs the gaps as much as the marks; returning only active days would let
the client close the gaps up and render a longer streak than the user has. The service
fills the range in Python after grouping, so the API contract is a fixed-length series.

## D26 — `/start` offers an *inline* WebApp button, not the reply keyboard SPEC §9a asks for
SPEC §9a specifies "a persistent reply keyboard with a `WebAppInfo` button labeled
'Memorani ochish'". Implemented literally, the app opened from that button and then
showed "Ilovani Telegram orqali oching" **from inside Telegram** — because a Mini App
launched from a `KeyboardButton` receives no `initData`. Telegram reserves that launch
type for `sendData` flows; `@telegram-apps/types` states it outright: *"Current launch
init data. Can be missing in case, application was launched via KeyboardButton."*

No initData means no HMAC to validate, and SPEC §7 makes that HMAC the entire basis of
authentication — so the button could open the app but never sign the user in.

**Choice:** every offer to open the app uses an **inline** WebApp button, which does
carry initData. The persistent entry point becomes the BotFather menu button, which sits
beside the input field permanently and authenticates correctly. The reply keyboard stays
but carries only a plain "Takrorlash" shortcut, so no button in the bot can ever lead to
an unauthenticated app.

**How this was caught:** on a real phone, via the bot. It cannot be reproduced in a
browser, because outside Telegram every launch path lacks initData and the same error
screen is the *correct* output.

**Two follow-ons the first fix missed.** A reply keyboard is *persistent*: switching
`/start` to an inline button left every existing user still holding the broken one, so
`/start` now sends `ReplyKeyboardRemove()` first and the inline button second — one
`reply_markup` per message means this needs two messages. And the app now calls
`set_chat_menu_button` on startup, so the persistent entry point SPEC §9a wanted exists
without anyone having to remember a BotFather step.

## D27 — Only `hash` is removed from the data-check string; `signature` stays in
Newer Telegram clients send a `signature` field alongside `hash` — the Ed25519 value
used for *third-party* validation. The validator originally stripped it before
computing the HMAC, reasoning that it belonged to a different algorithm. It does not:
Telegram excludes **only** `hash`, and SPEC §7 step 1 already said so in as many words
— "pull out `hash`, keep every other key".

Stripping it produced a different data-check string, so the HMAC never matched and
every genuine launch was rejected as a forgery: "initData imzosi noto'g'ri", from
inside Telegram.

**Why the tests missed it:** `tests/factories.py` never generated a `signature` field,
so the extra `pop` was a no-op in every test — the fixtures were a cleaner world than
production. `make_init_data` now takes `signature=`, and three tests cover it,
including a cross-check against `aiogram.utils.web_app.check_webapp_signature`. Putting
the bug back turns two of them red, which was verified rather than assumed.

**The general lesson for this file:** a hand-written crypto validator needs to be
checked against a reference implementation on a payload shaped like a real one, not
only against fixtures written by the same person who wrote the validator.

## D28 — The product is a translator, and `/lookup` no longer refuses to save
The app was built as a monolingual dictionary: an English word returned English
definitions, and the user ticked which ones to keep. That is not the product. The user
picks a language pair, types a word, and wants every translation of it on one
comma-separated line — already saved, with nothing else to do. "Bu app ni juda dangasa
odamlar ishlatishadi."

Four consequences, all deliberate departures from the spec as written:

**SPEC §7 says "`/lookup` never writes a card".** That rule was written for a flow where
the user chose what to keep. Requiring a second tap is now the single piece of friction
the product exists to remove. **Choice:** `POST /translate` translates *and* files the
word; `POST /lookup` stays a pure read, unchanged, because that is the shape a public
developer API takes — which is where this is going next.

**SPEC §6's provider chain was dictionary-first.** FreeDictionary returns English
definitions, which is the wrong output entirely. **Choice:** the chain is now Azure
Dictionary Lookup (alternative translations with parts of speech, one fast call, but
only for pairs involving English) then Gemini (structured output, any pair). Both return
target-language text directly, so the separate translation step and its batch-alignment
problem are gone. `FreeDictionaryProvider` is kept and still tested — it is the right
tool if English definitions are ever wanted again — but nothing routes to it.

**A daily deck is now per language pair.** `(user_id, daily_date)` became
`(user_id, daily_date, source_lang, target_lang)`, so a user who switches from EN→UZ to
RU→UZ mid-day gets two decks and a review session never mixes languages.

**The meaning-selection UI is gone**, in the app and in the bot. No chips, no inline
toggle buttons, no "Saqlash". The bot replies once, with the word, the translations and
where they went.

## D29 — Translating the same word twice checks first rather than recovering after
The first version let the duplicate INSERT fail and caught `ConflictError`. That works
in a service-level test and returns **500** over HTTP: `create_card` rolls the session
back, and the very next `SELECT` on that session re-raises the original
`IntegrityError`. **Choice:** look the card up before inserting. A repeat translation is
an ordinary thing to do, not an exception. The `ConflictError` catch stays as a
backstop for two devices racing on the same word.

**Why the tests missed it:** every duplicate test called the service directly. The
regression test now goes through HTTP, where the session lifecycle is the real one.
