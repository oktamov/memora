# Manual tests

Steps only a human on a real device can run. Everything else is covered by
`uv run pytest -q` and the Compose smoke checks in `AGENT.md` §2.

Prerequisites: a bot created with @BotFather, `TELEGRAM_BOT_TOKEN` set, the API
reachable over HTTPS, and `MINI_APP_URL` pointing at that host. See `BLOCKERS.md`.

---

## MT-1 — Mini App opens from the bot (M5)

1. Open a chat with your bot and send `/start`.
2. Confirm the greeting is in Uzbek and a reply keyboard shows **Memorani ochish**.
3. Tap it. The Mini App must open **full height**, not half-screen.
4. Confirm no Telegram loading placeholder remains on screen after ~1s.
5. Confirm the first screen is **Decks** — no login screen, no onboarding wall.

## MT-2 — Vertical swipe does not close the app (M5, SPEC §13)

1. Open the Mini App and start a review session.
2. Drag downward on the review card, firmly, several times, on **iOS**.
3. The app must not close and the session must not be lost.

## MT-3 — Keyboard does not break the layout (M5, SPEC §13)

1. Open the lookup screen and tap the input.
2. With the keyboard open, confirm the input stays visible and nothing is clipped.
3. Rotate to landscape and back; confirm the layout still fits.
4. Dismiss the keyboard; confirm the layout returns without a dead gap at the bottom.

## MT-4 — Haptics (M5)

1. Flip a review card — expect a light impact.
2. Rate the card — expect a notification haptic.

## MT-5 — Native BackButton (M5)

1. Navigate Decks → deck detail → review.
2. Confirm Telegram's own back button appears in the header and steps back correctly.
3. Confirm the app never draws its own back arrow.

## MT-6 — Deep link into review (M5, M6)

1. Send `/review` to the bot.
2. Tap the WebApp button in the reply.
3. The Mini App must open **directly** on the review screen, not on Decks.

## MT-7 — Full loop end to end (M5 acceptance)

1. Open the app from the bot.
2. Look up a word you do not know.
3. Select two meanings, paste a sentence from the book you are holding, save.
4. Confirm a "Saqlandi" toast and that the card appears in today's daily deck.
5. Review it: flip, rate **Yaxshi**, confirm the session advances immediately.

## MT-8 — Bare-word capture in chat (M6 acceptance)

1. Send `serendipity` to the bot as a plain message.
2. Confirm meanings come back with one inline button per meaning plus **Saqlash**.
3. Tap two meaning buttons — the message must be **edited in place**, not resent.
4. Tap **Saqlash**.
5. Open the Mini App and confirm the card is in today's daily deck with exactly the
   two meanings you selected.

## MT-9 — Abuse controls in chat (M6, SPEC §8)

1. Send a full paragraph (>64 characters, >4 words) to the bot.
2. Confirm it is rejected with a short Uzbek explanation and that **no** provider call
   is made (check the API logs for the absence of a `provider_call` event).

## MT-10 — Daily reminder (M6)

1. Set `reminder_hour` to the next local hour via `/settings`.
2. Ensure you have at least one due card.
3. Wait for the hourly job. Confirm one message arrives with the due count and a
   WebApp button.
4. Clear all due cards and wait for the following hour. Confirm **no** message arrives.

## MT-11 — Blocked user is deactivated (M6)

1. Block the bot from Telegram.
2. Trigger a reminder run.
3. Confirm the API logs a `TelegramForbiddenError` and that `users.is_active` flips to
   `false` for that user.
