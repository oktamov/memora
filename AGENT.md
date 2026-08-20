# Memora — Autonomous Build Prompt

Paste this as your first message to the agent, with `SPEC.md` present in the repo root.

---

You are building Memora, a Telegram Mini App for vocabulary learning. `SPEC.md` in the
repository root is the complete specification and the source of truth. Read it in full
before writing a single line of code.

Your mandate is to take this repository from empty to a working M0–M7 implementation
without stopping to ask permission between steps. Work continuously. Do not end your
turn to report progress, ask whether to proceed, or request confirmation of a decision
you are capable of making yourself. End your turn only under the two conditions in
§6 below.

---

## 1. The working loop

For each milestone M0 through M7, in order, run this exact loop:

1. **Read.** Re-read the milestone's section in `SPEC.md` plus every section it
   references. Do not work from memory of an earlier read.
2. **Plan.** Write the milestone's task list into `PROGRESS.md` as unchecked boxes
   before implementing anything. Be specific: "implement initData HMAC validation with
   6-step algorithm", not "do auth".
3. **Implement.** Work through the tasks. Check each box the moment it genuinely passes,
   never in advance.
4. **Verify.** Run the milestone's verification gate (§2). It must actually execute and
   actually pass. A gate you did not run is a gate that failed.
5. **Fix.** If the gate fails, fix it and re-run. Repeat until green. Do not proceed
   with a red gate, and do not weaken a test to make it pass.
6. **Commit.** One commit per milestone: `feat(M3): cards CRUD and card_states`.
7. **Record.** Append a short entry to `PROGRESS.md`: what shipped, what you decided,
   what you deferred.
8. **Continue immediately** to the next milestone. Do not pause. Do not summarize for
   the user mid-run.

## 2. Verification gates

Each milestone has an acceptance criterion in `SPEC.md`. These are the mechanical gates
you must run in addition, every time, before a milestone counts as done:

```bash
# backend
cd backend
uv run ruff check . && uv run ruff format --check .
uv run mypy app/services app/providers app/srs app/telegram
uv run pytest -q

# frontend
cd frontend
npm run lint
npx tsc --noEmit
npm run build
```

From M1 onward, additionally:

```bash
docker compose up -d --build
curl -fsS http://localhost:8000/health
docker compose logs api --tail=50   # must contain no ERROR lines
```

All green, or the milestone is not done.

## 3. When you cannot proceed

You will hit things that genuinely require credentials or a physical device. These do
**not** stop the run. Handle them like this:

- **Missing API key or external credential** (Azure, Gemini, bot token): implement the
  real provider fully and correctly, then add a `Fake*` sibling that returns fixture
  data, selected when the env var is absent. Tests run against the fake. Note it in
  `BLOCKERS.md` and keep going. Never leave a `NotImplementedError` in the real path.
- **initData you cannot obtain**: write a fixture generator in `tests/` that signs a
  payload with a dummy bot token using the same algorithm, and test the validator
  against both a valid and a tampered payload. This fully covers §7 without Telegram.
- **Anything requiring a real phone**: build it per spec, write the manual test steps
  into `MANUAL_TESTS.md` as a numbered checklist, and continue.
- **An ambiguity in `SPEC.md`**: choose the simplest option consistent with the rest of
  the spec, implement it, and record the choice and your reasoning in `DECISIONS.md`.
  Do not ask. Do not stall.

## 4. Rules you do not break

- **Do not weaken tests to make them pass.** If a test is wrong, fix the test and say
  so in the commit message. If the code is wrong, fix the code.
- **Do not skip a milestone** or work on two at once, even if a later one seems easier.
- **Do not add scope.** `SPEC.md` §2 lists non-goals. If you find yourself building
  something not in the spec, stop and delete it.
- **Do not claim something works without running it.** No "this should now work". Run
  it, paste the real output into `PROGRESS.md`.
- **Do not silence errors.** No bare `except:`, no `# type: ignore` without a reason on
  the same line, no `eslint-disable` without a comment.
- **Do not commit secrets.** `.env` stays gitignored; `.env.example` ships with empty
  values.
- **Re-read `SPEC.md` §13** ("Things that will go wrong if ignored") before starting
  M2, M5, and M6. Those six items are the failures most likely to happen on this build.

## 5. Files you maintain

- `PROGRESS.md` — living task list and milestone log. Update continuously, not at the
  end. This is how the user follows the run.
- `DECISIONS.md` — every choice the spec left open, with one line of reasoning.
- `BLOCKERS.md` — anything needing the user: credentials, BotFather setup, domains.
  Each entry states exactly what you need and what you did in the meantime.
- `MANUAL_TESTS.md` — steps only a human on a real device can run.

## 6. When to end your turn

Exactly two conditions:

1. **All eight milestones are complete**, every gate in §2 is green, and
   `PROGRESS.md` shows every box checked. Then write a final summary: what was built,
   what is in `BLOCKERS.md`, and the exact commands to run the project.
2. **You are hard-blocked**: the same gate has failed three times with three different
   fix attempts, and you cannot make progress on any other milestone either. Then stop
   and report precisely what fails, what you tried, and what you need.

Running low on context is not one of the conditions. If context gets tight, write your
current state to `PROGRESS.md` in enough detail that you can resume from it cold, then
continue.

"I've finished M2, shall I continue?" is not an acceptable way to end a turn. Continue.

---

Start now. Read `SPEC.md`, then begin M0.
