"""dictionaryapi.dev — keyless, no quota, ~150ms (SPEC §6).

English source only. It returns English definitions, POS, IPA and examples; the
translation step that turns those into `target_lang` lives in `lookup_service`, so
this provider stays a pure dictionary.
"""

from __future__ import annotations

from typing import Any

import httpx

from app.core.config import settings
from app.providers.base import LookupResult, Meaning, ProviderError, http_error

_MAX_MEANINGS = 8
_MAX_EXAMPLES_PER_MEANING = 2


class FreeDictionaryProvider:
    name = "free_dictionary"

    def __init__(self, client: httpx.AsyncClient) -> None:
        # Injected, never constructed here: one client per process (SPEC §6, §13).
        self._client = client

    def supports(self, source_lang: str) -> bool:
        return source_lang == "en"

    async def lookup(self, term: str, source_lang: str) -> LookupResult | None:
        if not self.supports(source_lang):
            return None

        url = f"{settings.FREE_DICTIONARY_ENDPOINT}/{source_lang}/{term}"
        try:
            response = await self._client.get(url, timeout=settings.PROVIDER_TIMEOUT_SECONDS)
        except httpx.HTTPError as exc:
            raise ProviderError(self.name, str(exc)) from exc

        if response.status_code == 404:
            # An honest "no such word", not a failure. The chain stops here.
            return None
        if response.status_code >= 400:
            raise http_error(self.name, response)

        try:
            entries = response.json()
        except ValueError as exc:
            raise ProviderError(self.name, "response was not JSON") from exc

        if not isinstance(entries, list) or not entries:
            return None

        return self._parse(term, source_lang, entries)

    def _parse(
        self, term: str, source_lang: str, entries: list[dict[str, Any]]
    ) -> LookupResult | None:
        meanings: list[Meaning] = []
        ipa: str | None = None

        for entry in entries:
            ipa = ipa or _first_ipa(entry)
            for block in entry.get("meanings", []) or []:
                pos = block.get("partOfSpeech")
                for definition in block.get("definitions", []) or []:
                    text = (definition.get("definition") or "").strip()
                    if not text:
                        continue
                    example = (definition.get("example") or "").strip()
                    meanings.append(
                        Meaning(
                            pos=pos,
                            # Untranslated for now; lookup_service fills `definition`
                            # with target_lang text and keeps this as `gloss_en`.
                            definition=text,
                            gloss_en=text,
                            examples=[example] if example else [],
                        )
                    )
                    if len(meanings) >= _MAX_MEANINGS:
                        break
                if len(meanings) >= _MAX_MEANINGS:
                    break
            if len(meanings) >= _MAX_MEANINGS:
                break

        if not meanings:
            return None

        for meaning in meanings:
            del meaning.examples[_MAX_EXAMPLES_PER_MEANING:]

        return LookupResult(
            term=term,
            source_lang=source_lang,
            target_lang="en",  # lookup_service rewrites this after translation
            ipa=ipa,
            meanings=meanings,
            provider=self.name,
        )


def _first_ipa(entry: dict[str, Any]) -> str | None:
    """Prefer a phonetic with audio — those are the transcriptions worth trusting."""
    direct = (entry.get("phonetic") or "").strip()
    candidates = entry.get("phonetics") or []

    with_audio = [
        str(item.get("text", "")).strip()
        for item in candidates
        if item.get("audio") and str(item.get("text") or "").strip()
    ]
    if with_audio:
        return with_audio[0]
    if direct:
        return direct
    for item in candidates:
        text = (item.get("text") or "").strip()
        if text:
            return text
    return None
