
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
