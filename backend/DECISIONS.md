# Decisions

Every choice `SPEC.md` left open, with the reasoning behind it.

---

## D1 — `py-fsrs` 4.x has no `State.New`; we keep the spec's 0-based column anyway
`SPEC.md` §5 defines `card_states.state` as `0 new, 1 learning, 2 review, 3 relearning`.
Installed `fsrs==4.1.2` exposes only `Learning=1, Review=2, Relearning=3`; a brand-new
card is `Card(state=Learning, step=None, stability=None, difficulty=None)`.
**Choice:** the database keeps the spec's four-value enum, and `srs/scheduler.py` maps
`state == 0` to a fresh `fsrs.Card` with `step=None` and null stability/difficulty on the
way in, and back out via "was this card ever reviewed". The spec's storage contract is
the one clients and the future optimizer see, so it wins over the library's internal shape.

## D2 — `reps`, `lapses`, `elapsed_days`, `scheduled_days` are computed by us
`fsrs` 4.x dropped these from `Card`. `SPEC.md` §5 requires them on `card_states` and
`review_logs`, and §5 is explicit that `review_logs` must be reconstructable-proof.
**Choice:** `srs/scheduler.py` derives all four itself — `elapsed_days` from
`last_review → now`, `scheduled_days` from `now → next due`, `reps` incremented per
review, `lapses` incremented when a `review`-state card is rated `Again`.

## D3 — Fake providers are selected by absent env var, per `AGENT.md` §3
`FakeTranslationProvider` and `FakeDictionaryProvider` return deterministic fixture data
and are wired by `providers/registry.py` when `AZURE_TRANSLATOR_KEY` / `GEMINI_API_KEY`
are unset. The real providers are fully implemented on the same code path; no
`NotImplementedError` exists in the real path.

## D4 — `users.fsrs_params` is `jsonb`, nullable, written by nobody in v1
`SPEC.md` §9 asks for the column to exist so review logs stay useful, and explicitly
defers the optimizer. The column ships in the first migration and is read by
`srs/scheduler.py` (null → library defaults). Nothing writes it.

## D5 — Health check reports dependency status rather than failing hard
`GET /health` returns `200` with `{"status": "ok"|"degraded", "db":…, "redis":…}` so the
Compose healthcheck and `curl -fsS` in `AGENT.md` §2 both succeed while still surfacing a
down dependency. A hard 503 would make the M0 gate flap during container startup ordering.
