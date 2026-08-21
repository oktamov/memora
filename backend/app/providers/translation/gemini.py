"""Gemini as a translation fallback (SPEC §6).

Used when Azure is unconfigured or failing. One call per lookup: the whole batch goes
in as a JSON array and comes back as one, so ordering is preserved by position.
"""

from __future__ import annotations

import json
from typing import Any

import httpx

from app.core.config import settings
from app.providers.base import ProviderError

_RESPONSE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {"translations": {"type": "array", "items": {"type": "string"}}},
    "required": ["translations"],
}

_PROMPT = """Translate each string in the JSON array below from {source_lang} to \
{target_lang}.

Return exactly {count} translations, in the same order as the input. Translate the
meaning, not word for word. Keep each translation about as short as its source. Do not
add notes, transliterations or explanations.

Input:
{payload}"""


class GeminiTranslationProvider:
    name = "gemini_translate"

    def __init__(self, client: httpx.AsyncClient, *, api_key: str, model: str) -> None:
        self._client = client
        self._api_key = api_key
        self._model = model

    async def translate(self, texts: list[str], source_lang: str, target_lang: str) -> list[str]:
        if not texts:
            return []
        if source_lang == target_lang:
            return list(texts)

        url = f"{settings.GEMINI_ENDPOINT}/models/{self._model}:generateContent"
        body = {
            "contents": [
                {
                    "role": "user",
                    "parts": [
                        {
                            "text": _PROMPT.format(
                                source_lang=source_lang,
                                target_lang=target_lang,
                                count=len(texts),
                                payload=json.dumps(texts, ensure_ascii=False),
                            )
                        }
                    ],
                }
            ],
            "generationConfig": {
                "responseMimeType": "application/json",
                "responseSchema": _RESPONSE_SCHEMA,
                "temperature": 0.1,
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
            translations = parsed["translations"]
        except (ValueError, KeyError, IndexError, TypeError) as exc:
            raise ProviderError(self.name, "unexpected response shape") from exc

        if not isinstance(translations, list) or len(translations) != len(texts):
            # A misaligned batch would silently attach the wrong meaning to a word.
            raise ProviderError(self.name, "translation count did not match the input")

        return [str(item) for item in translations]
