"""Builds the provider chain from settings (SPEC §6).

Chain selection is language-aware:
  - `source_lang == "en"` → FreeDictionary, then one batched translation call.
  - `source_lang != "en"` → Gemini, the only structured multi-meaning path for
    arbitrary source languages.
  - `target_lang == "uz"` with `UZ_PREFER_LLM` → Gemini first even for English, because
    general NMT handles Uzbek unevenly.

Every provider is handed the one shared `httpx.AsyncClient` (SPEC §6, §13).
"""

from __future__ import annotations

from dataclasses import dataclass

import httpx

from app.core.config import settings
from app.providers.base import DictionaryProvider, TranslationProvider
from app.providers.dictionary.free_dictionary import FreeDictionaryProvider
from app.providers.dictionary.gemini import GeminiDictionaryProvider
from app.providers.fakes import FakeDictionaryProvider, FakeTranslationProvider
from app.providers.translation.azure import AzureTranslationProvider
from app.providers.translation.gemini import GeminiTranslationProvider


@dataclass(frozen=True, slots=True)
class Chain:
    """The ordered providers to try for one lookup.

    A `bilingual` provider returns `target_lang` text directly and needs no translation
    step; a `monolingual` one returns English and is paired with `translator`.
    """

    dictionaries: tuple[tuple[DictionaryProvider, bool], ...]
    translator: TranslationProvider | None


class ProviderRegistry:
    """Constructed once per process, in the FastAPI lifespan."""

    def __init__(self, client: httpx.AsyncClient) -> None:
        self._client = client

        self.free_dictionary = FreeDictionaryProvider(client)

        self.gemini_dictionary: GeminiDictionaryProvider | FakeDictionaryProvider
        self.translator: TranslationProvider

        if settings.GEMINI_API_KEY:
            self.gemini_dictionary = GeminiDictionaryProvider(
                client, api_key=settings.GEMINI_API_KEY, model=settings.GEMINI_MODEL
            )
        else:
            # No key: fixtures, so the chain still runs end to end (BLOCKERS.md B4).
            self.gemini_dictionary = FakeDictionaryProvider()

        if settings.AZURE_TRANSLATOR_KEY and settings.AZURE_TRANSLATOR_REGION:
            self.translator = AzureTranslationProvider(
                client,
                key=settings.AZURE_TRANSLATOR_KEY,
                region=settings.AZURE_TRANSLATOR_REGION,
            )
        elif settings.GEMINI_API_KEY:
            self.translator = GeminiTranslationProvider(
                client, api_key=settings.GEMINI_API_KEY, model=settings.GEMINI_MODEL
            )
        else:
            self.translator = FakeTranslationProvider()  # BLOCKERS.md B3

    @property
    def uses_fakes(self) -> bool:
        """True when no provider credential is configured. Surfaced on `/health`."""
        return isinstance(self.gemini_dictionary, FakeDictionaryProvider) or isinstance(
            self.translator, FakeTranslationProvider
        )

    def chain_for(self, source_lang: str, target_lang: str) -> Chain:
        """The ordered chain for one language pair.

        The bool beside each provider says whether it already speaks `target_lang`.
        """
        english_source = source_lang == "en"
        prefer_llm = target_lang == "uz" and settings.UZ_PREFER_LLM

        if not english_source:
            return Chain(dictionaries=((self.gemini_dictionary, True),), translator=self.translator)

        if prefer_llm:
            # Gemini first for Uzbek, FreeDictionary + translation as the fallback.
            return Chain(
                dictionaries=((self.gemini_dictionary, True), (self.free_dictionary, False)),
                translator=self.translator,
            )

        return Chain(
            dictionaries=((self.free_dictionary, False), (self.gemini_dictionary, True)),
            translator=self.translator,
        )
