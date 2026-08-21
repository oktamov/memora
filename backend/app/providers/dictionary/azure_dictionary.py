"""Azure Translator's Dictionary Lookup.

`/dictionary/lookup` returns the *alternative translations* of a word with parts of
speech — which is exactly the product's output — in one call, far faster and cheaper
than asking a model. It covers a fixed list of language pairs, so it runs ahead of
Gemini when it supports the pair and steps aside when it does not.
"""

from __future__ import annotations

from typing import Any

import httpx

from app.core.config import settings
from app.providers.base import LookupResult, Meaning, ProviderError, http_error

_MAX_TRANSLATIONS = 6

# Azure's dictionary covers a fixed set of languages, all paired with English. Anything
# else falls through to Gemini rather than burning a request that cannot succeed.
_DICTIONARY_LANGS = {
    "af",
    "ar",
    "bg",
    "bn",
    "bs",
    "ca",
    "cs",
    "cy",
    "da",
    "de",
    "el",
    "en",
    "es",
    "et",
    "fa",
    "fi",
    "fr",
    "he",
    "hi",
    "hu",
    "id",
    "is",
    "it",
    "ja",
    "ko",
    "lt",
    "lv",
    "ms",
    "mt",
    "nb",
    "nl",
    "pl",
    "pt",
    "ro",
    "ru",
    "sk",
    "sl",
    "sr",
    "sv",
    "sw",
    "ta",
    "th",
    "tr",
    "uk",
    "ur",
    "vi",
    "zh-Hans",
}


class AzureDictionaryProvider:
    name = "azure_dictionary"

    def __init__(self, client: httpx.AsyncClient, *, key: str, region: str) -> None:
        self._client = client
        self._key = key
        self._region = region

    def supports_pair(self, source_lang: str, target_lang: str) -> bool:
        """Azure's dictionary only goes to or from English."""
        if source_lang == target_lang:
            return False
        if "en" not in (source_lang, target_lang):
            return False
        return source_lang in _DICTIONARY_LANGS and target_lang in _DICTIONARY_LANGS

    def supports(self, source_lang: str) -> bool:
        return source_lang in _DICTIONARY_LANGS

    async def lookup(
        self, term: str, source_lang: str, target_lang: str | None = None
    ) -> LookupResult | None:
        target = target_lang or "en"
        if not self.supports_pair(source_lang, target):
            return None

        try:
            response = await self._client.post(
                f"{settings.AZURE_TRANSLATOR_ENDPOINT}/dictionary/lookup",
                params={"api-version": "3.0", "from": source_lang, "to": target},
                headers={
                    "Ocp-Apim-Subscription-Key": self._key,
                    "Ocp-Apim-Subscription-Region": self._region,
                    "Content-Type": "application/json",
                },
                json=[{"Text": term}],
                timeout=settings.PROVIDER_TIMEOUT_SECONDS,
            )
        except httpx.HTTPError as exc:
            raise ProviderError(self.name, str(exc)) from exc

        if response.status_code >= 400:
            raise http_error(self.name, response)

        try:
            payload = response.json()
        except ValueError as exc:
            raise ProviderError(self.name, "response was not JSON") from exc

        meanings = self._parse(payload)
        if not meanings:
            return None

        return LookupResult(
            term=term,
            source_lang=source_lang,
            target_lang=target,
            ipa=None,  # the dictionary endpoint carries no phonetics
            meanings=meanings,
            provider=self.name,
        )

    def _parse(self, payload: Any) -> list[Meaning]:
        if not isinstance(payload, list) or not payload:
            raise ProviderError(self.name, "unexpected response shape")

        entry = payload[0]
        if not isinstance(entry, dict):
            raise ProviderError(self.name, "unexpected response shape")

        seen: set[str] = set()
        meanings: list[Meaning] = []
        for item in entry.get("translations", []):
            text = str(item.get("displayTarget", "")).strip()
            key = text.casefold()
            if not text or key in seen:
                continue
            seen.add(key)
            meanings.append(
                Meaning(
                    pos=str(item.get("posTag", "")).strip().lower() or None,
                    definition=text,
                    gloss_en=None,
                )
            )
            if len(meanings) >= _MAX_TRANSLATIONS:
                break
        return meanings
