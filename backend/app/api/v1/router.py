"""Aggregates every v1 router under `/api/v1`."""

from fastapi import APIRouter

from app.api.v1 import auth, cards, decks, lookup, review

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(auth.router)
api_router.include_router(decks.router)
api_router.include_router(lookup.router)
api_router.include_router(cards.router)
api_router.include_router(review.router)
