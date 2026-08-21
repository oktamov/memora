"""Call Gemini for real and report what happened.

Exists because a model name, an API key and a response schema can only be verified by
a live request. Guessing at any of the three costs a deploy cycle to find out.

    uv run python scripts/check_gemini.py            # the configured model
    uv run python scripts/check_gemini.py gemini-2.5-flash
    uv run python scripts/check_gemini.py --list     # models the key can actually use
"""

from __future__ import annotations

import asyncio
import sys

import httpx

from app.core.config import settings
from app.providers.base import ProviderError
from app.providers.dictionary.gemini import GeminiDictionaryProvider


async def list_models(client: httpx.AsyncClient) -> int:
    response = await client.get(
        f"{settings.GEMINI_ENDPOINT}/models",
        headers={"x-goog-api-key": settings.GEMINI_API_KEY},
        timeout=20,
    )
    if response.status_code >= 400:
        print(f"✗ HTTP {response.status_code} — {response.text[:300]}")
        return 1

    names = [
        model["name"].removeprefix("models/")
        for model in response.json().get("models", [])
        if "generateContent" in model.get("supportedGenerationMethods", [])
    ]
    print(f"Models this key can call ({len(names)}):")
    for name in sorted(names):
        print(f"  {name}")
    return 0


async def check(client: httpx.AsyncClient, model: str) -> int:
    print(f"model:  {model}")
    print("request: translate 'water' from en to uz, structured output\n")

    provider = GeminiDictionaryProvider(client, api_key=settings.GEMINI_API_KEY, model=model)
    try:
        result = await provider.lookup("water", "en", "uz")
    except ProviderError as error:
        print(f"✗ {error}")
        return 1

    if result is None:
        print("✗ the model returned no translations for a word that plainly has some")
        return 1

    print(f"✓ ipa:          {result.ipa}")
    print(f"✓ translations: {', '.join(m.definition for m in result.meanings)}")
    print(f"✓ parts:        {[m.pos for m in result.meanings]}")
    return 0


async def main() -> int:
    if not settings.GEMINI_API_KEY:
        print("✗ GEMINI_API_KEY is not set. Put it in .env and re-run.")
        return 2

    async with httpx.AsyncClient() as client:
        if "--list" in sys.argv:
            return await list_models(client)
        model = next(
            (arg for arg in sys.argv[1:] if not arg.startswith("-")), settings.GEMINI_MODEL
        )
        return await check(client, model)


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
