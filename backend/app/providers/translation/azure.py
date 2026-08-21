"""Azure Translator v3.0 (SPEC §6).

One batched call per lookup. Azure accepts up to 100 texts and 50k characters per
request, which comfortably covers a word's definitions and examples — sending them one
at a time would multiply both latency and cost.
"""

from __future__ import annotations

from typing import Any

import httpx

from app.core.config import settings
from app.providers.base import ProviderError, http_error

_MAX_TEXTS_PER_REQUEST = 100


class AzureTranslationProvider:
    name = "azure"

    def __init__(self, client: httpx.AsyncClient, *, key: str, region: str) -> None:
        self._client = client
        self._key = key
        self._region = region

    async def translate(self, texts: list[str], source_lang: str, target_lang: str) -> list[str]:
        """Translate `texts` in order. The returned list is the same length as the input."""
        if not texts:
            return []
        if source_lang == target_lang:
            return list(texts)

        translated: list[str] = []
        for start in range(0, len(texts), _MAX_TEXTS_PER_REQUEST):
            chunk = texts[start : start + _MAX_TEXTS_PER_REQUEST]
            translated.extend(await self._translate_chunk(chunk, source_lang, target_lang))
        return translated

    async def _translate_chunk(
        self, texts: list[str], source_lang: str, target_lang: str
    ) -> list[str]:
        try:
            response = await self._client.post(
                f"{settings.AZURE_TRANSLATOR_ENDPOINT}/translate",
                params={"api-version": "3.0", "from": source_lang, "to": target_lang},
                headers={
                    "Ocp-Apim-Subscription-Key": self._key,
                    "Ocp-Apim-Subscription-Region": self._region,
                    "Content-Type": "application/json",
                },
                json=[{"Text": text} for text in texts],
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

        return self._extract(payload, len(texts))

    def _extract(self, payload: Any, expected: int) -> list[str]:
        if not isinstance(payload, list) or len(payload) != expected:
            raise ProviderError(self.name, "unexpected response shape")

        out: list[str] = []
        for item in payload:
            translations = item.get("translations") if isinstance(item, dict) else None
            if not translations:
                raise ProviderError(self.name, "missing translations")
            out.append(str(translations[0].get("text", "")))
        return out
