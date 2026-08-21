"""M3 acceptance (SPEC §11): saving the same word twice into one deck is rejected with
a clear error."""

from typing import Any

from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.card import STATE_NEW, Card, CardState

RUN_LOOKUP = {"term": "run", "source_lang": "en", "target_lang": "uz"}


def card_payload(**overrides: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "term": "run",
        "ipa": "/ɹʌn/",
        "meanings": [
            {"pos": "verb", "definition": "yugurmoq", "gloss_en": "to move quickly on foot"},
            {"pos": "noun", "definition": "yugurish", "gloss_en": "an act of running"},
        ],
        "examples": [
            {
                "text": "He ran to the station.",
                "translation": "U vokzalgacha yugurdi.",
                "source": "user",
            }
        ],
    }
    payload.update(overrides)
    return payload


async def test_saving_a_lookup_result_creates_a_card_and_its_state(
    client: AsyncClient, auth_headers: dict[str, str], db_session: AsyncSession
) -> None:
    lookup = await client.post("/api/v1/lookup", headers=auth_headers, json=RUN_LOOKUP)
    meanings = lookup.json()["meanings"][:2]

    response = await client.post(
        "/api/v1/cards",
        headers=auth_headers,
        json=card_payload(
            meanings=[
                {"pos": m["pos"], "definition": m["definition"], "gloss_en": m["gloss_en"]}
                for m in meanings
            ],
            ipa=lookup.json()["ipa"],
        ),
    )

    assert response.status_code == 201, response.text
    body = response.json()
    assert body["term"] == "run"
    assert len(body["meanings"]) == 2
    # SPEC §5: one card_states row, created together with the card.
    assert body["state"]["state"] == STATE_NEW
    assert body["state"]["reps"] == 0
    assert body["state"]["suspended"] is False

    states = (await db_session.scalars(select(CardState))).all()
    assert len(states) == 1


async def test_saving_the_same_word_twice_into_one_deck_is_rejected(
    client: AsyncClient, auth_headers: dict[str, str]
) -> None:
    """M3 acceptance."""
    first = await client.post("/api/v1/cards", headers=auth_headers, json=card_payload())
    assert first.status_code == 201

    second = await client.post("/api/v1/cards", headers=auth_headers, json=card_payload())

    assert second.status_code == 409
    error = second.json()["error"]
    assert error["code"] == "card_duplicate"
    assert "run" in error["message"]


async def test_case_variants_count_as_the_same_word(
    client: AsyncClient, auth_headers: dict[str, str]
) -> None:
    await client.post("/api/v1/cards", headers=auth_headers, json=card_payload(term="Run"))

    duplicate = await client.post(
        "/api/v1/cards", headers=auth_headers, json=card_payload(term="  RUN  ")
    )

    assert duplicate.status_code == 409


async def test_the_users_own_spelling_survives_as_display_term(
    client: AsyncClient, auth_headers: dict[str, str]
) -> None:
    response = await client.post(
        "/api/v1/cards", headers=auth_headers, json=card_payload(term="  Serendipity ")
    )

    body = response.json()
    assert body["term"] == "serendipity"
    assert body["display_term"] == "Serendipity"


async def test_the_same_word_may_live_in_two_different_decks(
    client: AsyncClient, auth_headers: dict[str, str]
) -> None:
    """The unique index is `(deck_id, term)`, not `(user_id, term)`."""
    other = await client.post(
        "/api/v1/decks",
        headers=auth_headers,
        json={"name": "Dune", "source_lang": "en", "target_lang": "uz"},
    )

    first = await client.post("/api/v1/cards", headers=auth_headers, json=card_payload())
    second = await client.post(
        "/api/v1/cards",
        headers=auth_headers,
        json=card_payload(deck_id=other.json()["id"]),
    )

    assert first.status_code == 201
    assert second.status_code == 201


async def test_omitting_deck_id_targets_todays_daily_deck(
    client: AsyncClient, auth_headers: dict[str, str]
) -> None:
    created = await client.post("/api/v1/cards", headers=auth_headers, json=card_payload())

    daily = await client.get("/api/v1/decks/daily", headers=auth_headers)

    assert created.json()["deck_id"] == daily.json()["id"]
    assert daily.json()["kind"] == "daily"


async def test_language_pair_is_copied_from_the_deck(
    client: AsyncClient, auth_headers: dict[str, str]
) -> None:
    deck = await client.post(
        "/api/v1/decks",
        headers=auth_headers,
        json={"name": "Russkiy", "source_lang": "ru", "target_lang": "uz"},
    )

    card = await client.post(
        "/api/v1/cards", headers=auth_headers, json=card_payload(deck_id=deck.json()["id"])
    )

    assert card.json()["source_lang"] == "ru"
    assert card.json()["target_lang"] == "uz"


async def test_the_readers_own_sentence_is_listed_first(
    client: AsyncClient, auth_headers: dict[str, str]
) -> None:
    """SPEC §5: context from real reading is the whole point."""
    response = await client.post(
        "/api/v1/cards",
        headers=auth_headers,
        json=card_payload(
            examples=[
                {"text": "A provider sentence.", "source": "provider"},
                {"text": "The sentence from my book.", "source": "user"},
            ]
        ),
    )

    examples = response.json()["examples"]
    assert examples[0]["source"] == "user"
    assert examples[0]["text"] == "The sentence from my book."


async def test_a_card_needs_at_least_one_meaning(
    client: AsyncClient, auth_headers: dict[str, str]
) -> None:
    response = await client.post(
        "/api/v1/cards", headers=auth_headers, json=card_payload(meanings=[])
    )

    assert response.status_code == 422


async def test_deck_counts_reflect_saved_cards(
    client: AsyncClient, auth_headers: dict[str, str]
) -> None:
    await client.post("/api/v1/cards", headers=auth_headers, json=card_payload())
    await client.post("/api/v1/cards", headers=auth_headers, json=card_payload(term="book"))

    decks = await client.get("/api/v1/decks", headers=auth_headers)

    daily = decks.json()[0]
    assert daily["card_count"] == 2
    assert daily["new_count"] == 2
    assert daily["due_count"] == 2  # a new card is due immediately


async def test_cards_are_listed_newest_first_with_a_cursor(
    client: AsyncClient, auth_headers: dict[str, str]
) -> None:
    for index in range(5):
        await client.post(
            "/api/v1/cards", headers=auth_headers, json=card_payload(term=f"word{index}")
        )
    deck_id = (await client.get("/api/v1/decks/daily", headers=auth_headers)).json()["id"]

    first = await client.get(
        f"/api/v1/decks/{deck_id}/cards", headers=auth_headers, params={"limit": 2}
    )

    assert first.status_code == 200
    body = first.json()
    assert len(body["items"]) == 2
    assert body["items"][0]["term"] == "word4"  # newest first
    assert body["next_cursor"]

    second = await client.get(
        f"/api/v1/decks/{deck_id}/cards",
        headers=auth_headers,
        params={"limit": 2, "cursor": body["next_cursor"]},
    )
    assert [item["term"] for item in second.json()["items"]] == ["word2", "word1"]

    last = await client.get(
        f"/api/v1/decks/{deck_id}/cards",
        headers=auth_headers,
        params={"limit": 2, "cursor": second.json()["next_cursor"]},
    )
    assert [item["term"] for item in last.json()["items"]] == ["word0"]
    assert last.json()["next_cursor"] is None


async def test_cards_can_be_searched_within_a_deck(
    client: AsyncClient, auth_headers: dict[str, str]
) -> None:
    for term in ("serendipity", "run", "serene"):
        await client.post("/api/v1/cards", headers=auth_headers, json=card_payload(term=term))
    deck_id = (await client.get("/api/v1/decks/daily", headers=auth_headers)).json()["id"]

    found = await client.get(
        f"/api/v1/decks/{deck_id}/cards", headers=auth_headers, params={"search": "SERE"}
    )

    assert {item["term"] for item in found.json()["items"]} == {"serendipity", "serene"}


async def test_a_bad_cursor_is_a_clear_error(
    client: AsyncClient, auth_headers: dict[str, str]
) -> None:
    deck_id = (await client.get("/api/v1/decks/daily", headers=auth_headers)).json()["id"]

    response = await client.get(
        f"/api/v1/decks/{deck_id}/cards", headers=auth_headers, params={"cursor": "!!!"}
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "cursor_invalid"


async def test_edit_meanings_and_note(client: AsyncClient, auth_headers: dict[str, str]) -> None:
    created = await client.post("/api/v1/cards", headers=auth_headers, json=card_payload())

    updated = await client.patch(
        f"/api/v1/cards/{created.json()['id']}",
        headers=auth_headers,
        json={
            "meanings": [{"pos": "verb", "definition": "chopmoq", "gloss_en": "to run"}],
            "note": "Dune, 3-bob",
        },
    )

    assert updated.status_code == 200
    assert updated.json()["meanings"] == [
        {"pos": "verb", "definition": "chopmoq", "gloss_en": "to run"}
    ]
    assert updated.json()["note"] == "Dune, 3-bob"
    assert updated.json()["pos"] == "verb"


async def test_a_note_can_be_cleared(client: AsyncClient, auth_headers: dict[str, str]) -> None:
    created = await client.post(
        "/api/v1/cards", headers=auth_headers, json=card_payload(note="eslatma")
    )

    cleared = await client.patch(
        f"/api/v1/cards/{created.json()['id']}", headers=auth_headers, json={"note": None}
    )

    assert cleared.json()["note"] is None


async def test_a_card_can_be_moved_to_another_deck(
    client: AsyncClient, auth_headers: dict[str, str]
) -> None:
    created = await client.post("/api/v1/cards", headers=auth_headers, json=card_payload())
    target = await client.post(
        "/api/v1/decks",
        headers=auth_headers,
        json={"name": "Dune", "source_lang": "en", "target_lang": "uz"},
    )

    moved = await client.patch(
        f"/api/v1/cards/{created.json()['id']}",
        headers=auth_headers,
        json={"deck_id": target.json()["id"]},
    )

    assert moved.json()["deck_id"] == target.json()["id"]


async def test_moving_onto_a_duplicate_is_rejected(
    client: AsyncClient, auth_headers: dict[str, str]
) -> None:
    target = await client.post(
        "/api/v1/decks",
        headers=auth_headers,
        json={"name": "Dune", "source_lang": "en", "target_lang": "uz"},
    )
    await client.post(
        "/api/v1/cards", headers=auth_headers, json=card_payload(deck_id=target.json()["id"])
    )
    daily_card = await client.post("/api/v1/cards", headers=auth_headers, json=card_payload())

    moved = await client.patch(
        f"/api/v1/cards/{daily_card.json()['id']}",
        headers=auth_headers,
        json={"deck_id": target.json()["id"]},
    )

    assert moved.status_code == 409
    assert moved.json()["error"]["code"] == "card_duplicate"


async def test_suspend_toggles_and_can_be_set_explicitly(
    client: AsyncClient, auth_headers: dict[str, str]
) -> None:
    created = await client.post("/api/v1/cards", headers=auth_headers, json=card_payload())
    card_id = created.json()["id"]

    toggled = await client.post(f"/api/v1/cards/{card_id}/suspend", headers=auth_headers, json={})
    assert toggled.json()["suspended"] is True

    toggled_back = await client.post(
        f"/api/v1/cards/{card_id}/suspend", headers=auth_headers, json={}
    )
    assert toggled_back.json()["suspended"] is False

    forced = await client.post(
        f"/api/v1/cards/{card_id}/suspend", headers=auth_headers, json={"suspended": True}
    )
    assert forced.json()["suspended"] is True


async def test_a_suspended_card_leaves_the_due_count(
    client: AsyncClient, auth_headers: dict[str, str]
) -> None:
    created = await client.post("/api/v1/cards", headers=auth_headers, json=card_payload())
    await client.post(
        f"/api/v1/cards/{created.json()['id']}/suspend",
        headers=auth_headers,
        json={"suspended": True},
    )

    decks = await client.get("/api/v1/decks", headers=auth_headers)

    assert decks.json()[0]["card_count"] == 1
    assert decks.json()[0]["due_count"] == 0


async def test_deleting_a_card_removes_its_state(
    client: AsyncClient, auth_headers: dict[str, str], db_session: AsyncSession
) -> None:
    created = await client.post("/api/v1/cards", headers=auth_headers, json=card_payload())

    deleted = await client.delete(f"/api/v1/cards/{created.json()['id']}", headers=auth_headers)

    assert deleted.status_code == 204
    assert (await db_session.scalars(select(Card))).all() == []
    assert (await db_session.scalars(select(CardState))).all() == []


async def test_deleting_a_deck_cascades_to_its_cards(
    client: AsyncClient, auth_headers: dict[str, str], db_session: AsyncSession
) -> None:
    deck = await client.post(
        "/api/v1/decks",
        headers=auth_headers,
        json={"name": "Dune", "source_lang": "en", "target_lang": "uz"},
    )
    await client.post(
        "/api/v1/cards", headers=auth_headers, json=card_payload(deck_id=deck.json()["id"])
    )

    await client.delete(f"/api/v1/decks/{deck.json()['id']}", headers=auth_headers)

    assert (await db_session.scalars(select(Card))).all() == []
    assert (await db_session.scalars(select(CardState))).all() == []


async def test_another_users_card_is_invisible(
    client: AsyncClient, auth_headers: dict[str, str], other_auth_headers: dict[str, str]
) -> None:
    created = await client.post("/api/v1/cards", headers=auth_headers, json=card_payload())
    card_id = created.json()["id"]

    assert (
        await client.patch(
            f"/api/v1/cards/{card_id}", headers=other_auth_headers, json={"note": "mine now"}
        )
    ).status_code == 404
    assert (
        await client.delete(f"/api/v1/cards/{card_id}", headers=other_auth_headers)
    ).status_code == 404
    assert (
        await client.post(f"/api/v1/cards/{card_id}/suspend", headers=other_auth_headers, json={})
    ).status_code == 404


async def test_a_card_cannot_be_added_to_an_archived_deck(
    client: AsyncClient, auth_headers: dict[str, str]
) -> None:
    deck = await client.post(
        "/api/v1/decks",
        headers=auth_headers,
        json={"name": "Old", "source_lang": "en", "target_lang": "uz"},
    )
    await client.patch(
        f"/api/v1/decks/{deck.json()['id']}", headers=auth_headers, json={"archived": True}
    )

    response = await client.post(
        "/api/v1/cards", headers=auth_headers, json=card_payload(deck_id=deck.json()["id"])
    )

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "deck_archived"


async def test_card_endpoints_require_authentication(client: AsyncClient) -> None:
    assert (await client.post("/api/v1/cards", json=card_payload())).status_code == 401
