"""Provider contracts (SPEC §6).

This module imports nothing from `app/` except `core/config`, per the layering rule in
SPEC §4. Providers are constructed with the one shared `httpx.AsyncClient` — never
their own (SPEC §6, §13).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable


@dataclass(slots=True)
class Meaning:
    pos: str | None
    definition: str  # in target_lang
    gloss_en: str | None  # original English definition, if available
    examples: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "pos": self.pos,
            "definition": self.definition,
            "gloss_en": self.gloss_en,
            "examples": list(self.examples),
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> Meaning:
        return cls(
            pos=payload.get("pos"),
            definition=payload.get("definition", ""),
            gloss_en=payload.get("gloss_en"),
            examples=list(payload.get("examples") or []),
        )


@dataclass(slots=True)
class LookupResult:
    term: str
    source_lang: str
    target_lang: str
    ipa: str | None
    meanings: list[Meaning]
    provider: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "term": self.term,
            "source_lang": self.source_lang,
            "target_lang": self.target_lang,
            "ipa": self.ipa,
            "meanings": [meaning.to_dict() for meaning in self.meanings],
            "provider": self.provider,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> LookupResult:
        return cls(
            term=payload["term"],
            source_lang=payload["source_lang"],
            target_lang=payload["target_lang"],
            ipa=payload.get("ipa"),
            meanings=[Meaning.from_dict(item) for item in payload.get("meanings", [])],
            provider=payload.get("provider", "unknown"),
        )


@runtime_checkable
class DictionaryProvider(Protocol):
    name: str

    def supports(self, source_lang: str) -> bool: ...

    async def lookup(self, term: str, source_lang: str) -> LookupResult | None: ...


@runtime_checkable
class TranslationProvider(Protocol):
    name: str

    async def translate(
        self, texts: list[str], source_lang: str, target_lang: str
    ) -> list[str]: ...


class ProviderError(Exception):
    """A provider failed. The chain catches this and falls through to the next."""

    def __init__(self, provider: str, message: str) -> None:
        super().__init__(f"{provider}: {message}")
        self.provider = provider
