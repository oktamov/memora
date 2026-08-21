"""Deck endpoints (SPEC §7)."""

from uuid import UUID

from fastapi import APIRouter, Query, Response, status

from app.core.deps import CurrentUser, DbSession
from app.schemas.deck import DeckCreateRequest, DeckResponse, DeckUpdateRequest
from app.services import card_service, deck_service

router = APIRouter(prefix="/decks", tags=["decks"])


@router.get("", response_model=list[DeckResponse])
async def list_decks(
    user: CurrentUser,
    session: DbSession,
    include_archived: bool = Query(default=False),
) -> list[DeckResponse]:
    """Decks with their card and due counts, today's daily deck pinned first."""
    decks = await deck_service.list_decks(session, user, include_archived=include_archived)
    counts = await card_service.deck_counts(session, user)
    return [_with_counts(deck, counts) for deck in decks]


@router.post("", response_model=DeckResponse, status_code=status.HTTP_201_CREATED)
async def create_deck(
    payload: DeckCreateRequest, user: CurrentUser, session: DbSession
) -> DeckResponse:
    deck = await deck_service.create_deck(
        session,
        user,
        name=payload.name,
        source_lang=payload.source_lang,
        target_lang=payload.target_lang,
    )
    return DeckResponse.model_validate(deck)


@router.get("/daily", response_model=DeckResponse)
async def read_daily_deck(user: CurrentUser, session: DbSession) -> DeckResponse:
    """Today's daily deck in the user's timezone, created if this is the first call."""
    deck = await deck_service.get_or_create_daily_deck(session, user)
    counts = await card_service.deck_counts(session, user)
    return _with_counts(deck, counts)


@router.get("/{deck_id}", response_model=DeckResponse)
async def read_deck(deck_id: UUID, user: CurrentUser, session: DbSession) -> DeckResponse:
    deck = await deck_service.get_deck(session, user, deck_id)
    counts = await card_service.deck_counts(session, user)
    return _with_counts(deck, counts)


@router.patch("/{deck_id}", response_model=DeckResponse)
async def update_deck(
    deck_id: UUID, payload: DeckUpdateRequest, user: CurrentUser, session: DbSession
) -> DeckResponse:
    deck = await deck_service.update_deck(
        session, user, deck_id, name=payload.name, archived=payload.archived
    )
    return DeckResponse.model_validate(deck)


@router.delete("/{deck_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_deck(deck_id: UUID, user: CurrentUser, session: DbSession) -> Response:
    await deck_service.delete_deck(session, user, deck_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


def _with_counts(deck: object, counts: dict[UUID, deck_service.DeckCounts]) -> DeckResponse:
    response = DeckResponse.model_validate(deck)
    tallies = counts.get(response.id)
    if tallies is not None:
        response.card_count = tallies.total
        response.due_count = tallies.due
        response.new_count = tallies.new
    return response
