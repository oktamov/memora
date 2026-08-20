"""Model package. Importing it registers every table on `Base.metadata`."""

from app.models.deck import Deck, DeckKind
from app.models.user import User

__all__ = ["Deck", "DeckKind", "User"]
