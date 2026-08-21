"""Gemini as a multi-sense translator.

The product is a translator, not a monolingual dictionary: a user types a word in one
language and wants every translation of it in another, as one comma-separated line.
One structured call answers that for any language pair, which is why this is the
primary provider rather than a fallback.

Structured output with a hard `responseSchema` — the model is constrained to conforming
JSON, so nothing here ever parses free text.
"""

from __future__ import annotations

import json
from typing import Any

import httpx

from app.core.config import settings
from app.providers.base import LookupResult, Meaning, ProviderError

_RESPONSE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "ipa": {"type": "string"},
        "translations": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "text": {"type": "string"},
                    "pos": {"type": "string"},
                },
                "required": ["text"],
            },
        },
    },
    "required": ["translations"],
}

_PROMPT = """Translate a single word or short phrase.

Word: {term}
From: {source_lang}
To: {target_lang}

Return every distinct translation the word genuinely has in {target_lang}, most common
first, at most 6. Each entry is one translation only — a single word or short phrase,
never a sentence, never an explanation, never a definition.

`pos` is the part of speech in English (noun, verb, adjective, ...), omitted when it
does not apply.

Also give `ipa`: the IPA transcription of the word in {source_lang}, omitted if you are
not confident.

If the word does not exist in {source_lang}, return an empty `translations` array.
Never invent a translation to fill space."""

_MAX_TRANSLATIONS = 6


class GeminiDictionaryProvider:
    name = "gemini"

    def __init__(self, client: httpx.AsyncClient, *, api_key: str, model: str) -> None:
        self._client = client
        self._api_key = api_key
        self._model = model

    def supports(self, source_lang: str) -> bool:
        """Any language. This is what makes it the primary path for arbitrary pairs."""
        del source_lang
        return True

    async def lookup(
        self, term: str, source_lang: str, target_lang: str | None = None
    ) -> LookupResult | None:
        """`target_lang` defaults to English so the signature still satisfies the
        `DictionaryProvider` Protocol; `lookup_service` always passes it explicitly."""
        target = target_lang or "en"
        payload = await self._generate(term, source_lang, target)
        meanings = self._parse(payload)
        if not meanings:
            return None

        ipa = str(payload.get("ipa") or "").strip()
        return LookupResult(
            term=term,
            source_lang=source_lang,
            target_lang=target,
            ipa=ipa or None,
            meanings=meanings,
            provider=self.name,
        )

    async def _generate(self, term: str, source_lang: str, target_lang: str) -> dict[str, Any]:
        url = f"{settings.GEMINI_ENDPOINT}/models/{self._model}:generateContent"
        body = {
            "contents": [
                {
                    "role": "user",
                    "parts": [
                        {
                            "text": _PROMPT.format(
                                term=term, source_lang=source_lang, target_lang=target_lang
                            )
                        }
                    ],
                }
            ],
            "generationConfig": {
                "responseMimeType": "application/json",
                "responseSchema": _RESPONSE_SCHEMA,
                "temperature": 0.2,
            },
        }

        try:
            response = await self._client.post(
                url,
                headers={"x-goog-api-key": self._api_key, "Content-Type": "application/json"},
                json=body,
                timeout=settings.PROVIDER_TIMEOUT_SECONDS,
            )
        except httpx.HTTPError as exc:
            raise ProviderError(self.name, str(exc)) from exc

        if response.status_code >= 400:
            raise ProviderError(self.name, f"HTTP {response.status_code}")

        try:
            envelope = response.json()
            text = envelope["candidates"][0]["content"]["parts"][0]["text"]
            parsed = json.loads(text)
        except (ValueError, KeyError, IndexError, TypeError) as exc:
            raise ProviderError(self.name, "unexpected response shape") from exc

        if not isinstance(parsed, dict):
            raise ProviderError(self.name, "structured output was not an object")
        return parsed

    def _parse(self, payload: dict[str, Any]) -> list[Meaning]:
        raw = payload.get("translations")
        if not isinstance(raw, list):
            raise ProviderError(self.name, "structured output had no translations array")

        seen: set[str] = set()
        meanings: list[Meaning] = []
        for item in raw[:_MAX_TRANSLATIONS]:
            if not isinstance(item, dict):
                continue
            text = str(item.get("text", "")).strip()
            # A model asked for "every distinct translation" will still repeat itself
            # occasionally, and a duplicate in a comma-separated line looks like a bug.
            key = text.casefold()
            if not text or key in seen:
                continue
            seen.add(key)
            meanings.append(
                Meaning(
                    pos=str(item.get("pos", "")).strip() or None,
                    definition=text,
                    gloss_en=None,
                )
            )
        return meanings
