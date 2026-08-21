"""Card endpoints (SPEC §7)."""

from uuid import UUID

from fastapi import APIRouter, Query, Response, status

from app.core.deps import CurrentUser, DbSession
from app.models.card import Card, CardState
from app.schemas.card import (
    CardCreateRequest,
    CardResponse,
    CardStateResponse,
    CardUpdateRequest,
    SuspendRequest,
)
from app.schemas.common import Page
from app.services import card_service

router = APIRouter(tags=["cards"])


@router.post("/cards", response_model=CardResponse, status_code=status.HTTP_201_CREATED)
async def create_card(
    payload: CardCreateRequest, user: CurrentUser, session: DbSession
) -> CardResponse:
    """Save a lookup result. Without `deck_id`, today's daily deck is the target."""
    card = await card_service.create_card(
        session,
        user,
        deck_id=payload.deck_id,
        term=payload.term,
        ipa=payload.ipa,
        pos=payload.pos,
        meanings=[meaning.model_dump() for meaning in payload.meanings],
        examples=[example.model_dump(mode="json") for example in payload.examples],
        note=payload.note,
    )
    state = await card_service.get_card_state(session, card)
    return _to_response(card, state)


@router.get("/decks/{deck_id}/cards", response_model=Page[CardResponse])
async def list_cards(
    deck_id: UUID,
    user: CurrentUser,
    session: DbSession,
    limit: int = Query(default=card_service.DEFAULT_PAGE_SIZE, ge=1, le=card_service.MAX_PAGE_SIZE),
    cursor: str | None = Query(default=None),
    search: str | None = Query(default=None, max_length=64),
) -> Page[CardResponse]:
    page = await card_service.list_cards(
        session, user, deck_id, limit=limit, cursor=cursor, search=search
    )
    states = await card_service.states_for(session, [card.id for card in page.items])
    return Page[CardResponse](
        items=[_to_response(card, states.get(card.id)) for card in page.items],
        next_cursor=page.next_cursor,
    )


@router.patch("/cards/{card_id}", response_model=CardResponse)
async def update_card(
    card_id: UUID, payload: CardUpdateRequest, user: CurrentUser, session: DbSession
) -> CardResponse:
    changed = payload.model_fields_set
    card = await card_service.update_card(
        session,
        user,
        card_id,
        deck_id=payload.deck_id,
        meanings=(
            [meaning.model_dump() for meaning in payload.meanings]
            if payload.meanings is not None
            else None
        ),
        examples=(
            [example.model_dump(mode="json") for example in payload.examples]
            if payload.examples is not None
            else None
        ),
        note=payload.note,
        # Distinguish "clear the note" from "leave it alone".
        note_set="note" in changed,
    )
    state = await card_service.get_card_state(session, card)
    return _to_response(card, state)


@router.delete("/cards/{card_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_card(card_id: UUID, user: CurrentUser, session: DbSession) -> Response:
    await card_service.delete_card(session, user, card_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/cards/{card_id}/suspend", response_model=CardStateResponse)
async def suspend_card(
    card_id: UUID, payload: SuspendRequest, user: CurrentUser, session: DbSession
) -> CardStateResponse:
    state = await card_service.set_suspended(session, user, card_id, suspended=payload.suspended)
    return CardStateResponse.model_validate(state)


def _to_response(card: Card, state: CardState | None) -> CardResponse:
    response = CardResponse.model_validate(card)
    if state is not None:
        response.state = CardStateResponse.model_validate(state)
    return response
