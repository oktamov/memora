
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
