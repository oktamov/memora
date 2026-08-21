
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
