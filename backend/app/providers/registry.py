"""Builds the provider chain from settings.

The product translates a word into every sense it has in the target language, so the
chain is ordered by which provider answers that best for a given pair:

  1. Azure Dictionary Lookup — returns alternative translations with parts of speech in
     one fast call, but only for its own list of pairs (all involving English).
  2. Gemini — structured output, any language pair, the universal fallback.

Every provider is handed the one shared `httpx.AsyncClient` (SPEC §6, §13).
"""

from __future__ import annotations

from dataclasses import dataclass

import httpx

from app.core.config import settings
from app.providers.base import DictionaryProvider
from app.providers.dictionary.azure_dictionary import AzureDictionaryProvider
from app.providers.dictionary.gemini import GeminiDictionaryProvider
from app.providers.fakes import FakeDictionaryProvider


@dataclass(frozen=True, slots=True)
class Chain:
    """The ordered providers to try for one lookup. Every one returns `target_lang`
    text directly, so there is no separate translation step to align."""

    providers: tuple[DictionaryProvider, ...]


class ProviderRegistry:
    """Constructed once per process, in the FastAPI lifespan."""

    def __init__(self, client: httpx.AsyncClient) -> None:
        self._client = client

        self.azure: AzureDictionaryProvider | None = None
        if settings.AZURE_TRANSLATOR_KEY and settings.AZURE_TRANSLATOR_REGION:
            self.azure = AzureDictionaryProvider(
                client,
                key=settings.AZURE_TRANSLATOR_KEY,
                region=settings.AZURE_TRANSLATOR_REGION,
            )

        self.gemini: GeminiDictionaryProvider | FakeDictionaryProvider
        if settings.GEMINI_API_KEY:
            self.gemini = GeminiDictionaryProvider(
                client, api_key=settings.GEMINI_API_KEY, model=settings.GEMINI_MODEL
            )
        else:
            # No key: fixtures, so the chain still runs end to end (BLOCKERS.md B4).
            self.gemini = FakeDictionaryProvider()

    @property
    def uses_fakes(self) -> bool:
        """True when no provider credential is configured. Surfaced on `/health`."""
        return isinstance(self.gemini, FakeDictionaryProvider)

    def chain_for(self, source_lang: str, target_lang: str) -> Chain:
        providers: list[DictionaryProvider] = []

        # Azure first when it covers the pair: one call, no model latency, no LLM bill.
        # `UZ_PREFER_LLM` overrides that for Uzbek, where SPEC §6 notes general NMT is
        # uneven and a model reads better.
        prefer_llm = target_lang == "uz" and settings.UZ_PREFER_LLM
        if (
            self.azure is not None
            and not prefer_llm
            and self.azure.supports_pair(source_lang, target_lang)
        ):
            providers.append(self.azure)

        providers.append(self.gemini)
        return Chain(providers=tuple(providers))
