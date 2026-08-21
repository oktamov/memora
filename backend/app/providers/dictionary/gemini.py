"""Gemini as a structured dictionary (SPEC §6).

The only path that produces multi-meaning output for arbitrary source languages. It
uses `responseSchema` structured output — the model is constrained to emit conforming
JSON, so nothing here ever parses free text.
"""

from __future__ import annotations

import json
from typing import Any

import httpx

from app.core.config import settings
from app.providers.base import LookupResult, Meaning, ProviderError

# A hard schema. Anything the model returns that does not fit is a provider error,
# never a salvage attempt.
_RESPONSE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "ipa": {"type": "string"},
        "meanings": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "pos": {"type": "string"},
                    "definition": {"type": "string"},
                    "gloss_en": {"type": "string"},
                    "examples": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["definition"],
            },
        },
    },
    "required": ["meanings"],
}

_PROMPT = """You are a bilingual dictionary.

Word or short phrase: {term}
Language of the word: {source_lang}
Language to give the meanings in: {target_lang}

Give every distinct meaning the word genuinely has, most common first, at most 6.
For each meaning:
- `pos`: part of speech in English (noun, verb, adjective, adverb, ...).
- `definition`: the meaning written in {target_lang}. Short — a gloss, not an essay.
- `gloss_en`: the same meaning in English.
- `examples`: at most one natural sentence in {source_lang} using the word in that sense.

Also give `ipa`: the IPA transcription of the word, or omit it if you are not sure.

If the word does not exist in {source_lang}, return an empty `meanings` array.
Never invent a meaning to fill space."""


class GeminiDictionaryProvider:
    name = "gemini"

    def __init__(self, client: httpx.AsyncClient, *, api_key: str, model: str) -> None:
        self._client = client
        self._api_key = api_key
        self._model = model

    def supports(self, source_lang: str) -> bool:
        """Any language. This is what makes it the non-English fallback."""
        del source_lang
        return True

    async def lookup(
        self, term: str, source_lang: str, target_lang: str | None = None
    ) -> LookupResult | None:
        """`target_lang` defaults to English so the signature still satisfies the
        `DictionaryProvider` Protocol; `lookup_service` always passes it explicitly."""
        target = target_lang or "en"
        payload = await self._generate(term, source_lang, target)
        meanings = self._parse_meanings(payload)
        if not meanings:
            return None

        ipa = payload.get("ipa")
        return LookupResult(
            term=term,
            source_lang=source_lang,
            target_lang=target,
            ipa=str(ipa).strip() or None if ipa else None,
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

    def _parse_meanings(self, payload: dict[str, Any]) -> list[Meaning]:
        raw = payload.get("meanings")
        if not isinstance(raw, list):
            raise ProviderError(self.name, "structured output had no meanings array")

        meanings: list[Meaning] = []
        for item in raw[:6]:
            if not isinstance(item, dict):
                continue
            definition = str(item.get("definition", "")).strip()
            if not definition:
                continue
            gloss = str(item.get("gloss_en", "")).strip()
            examples = [
                str(example).strip()
                for example in (item.get("examples") or [])
                if str(example).strip()
            ]
            meanings.append(
                Meaning(
                    pos=str(item.get("pos", "")).strip() or None,
                    definition=definition,
                    gloss_en=gloss or None,
                    examples=examples[:2],
                )
            )
        return meanings
