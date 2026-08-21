"""Providers against recorded fixtures — never a live API (SPEC §12)."""

import json
from pathlib import Path
from typing import Any

import httpx
import pytest

from app.providers.base import LookupResult, ProviderError
from app.providers.dictionary.azure_dictionary import AzureDictionaryProvider
from app.providers.dictionary.free_dictionary import FreeDictionaryProvider
from app.providers.dictionary.gemini import GeminiDictionaryProvider
from app.providers.registry import ProviderRegistry
from app.providers.translation.azure import AzureTranslationProvider
from app.providers.translation.gemini import GeminiTranslationProvider

FIXTURES = Path(__file__).parent / "fixtures"


def load(name: str) -> Any:
    return json.loads((FIXTURES / name).read_text())


def mock_client(handler: httpx.MockTransport) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=handler)


# --- FreeDictionary -------------------------------------------------------------


async def test_free_dictionary_parses_pos_ipa_definitions_and_examples() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path.endswith("/en/run")
        return httpx.Response(200, json=load("free_dictionary_run.json"))

    async with mock_client(httpx.MockTransport(handler)) as client:
        result = await FreeDictionaryProvider(client).lookup("run", "en")

    assert result is not None
    assert result.ipa == "/ɹʌn/"
    assert len(result.meanings) == 4
    assert [meaning.pos for meaning in result.meanings] == ["verb", "verb", "noun", "noun"]
    assert result.meanings[0].examples == ["He ran to the station."]
    # English text is preserved as the gloss for the translation step to keep.
    assert result.meanings[0].gloss_en == result.meanings[0].definition


async def test_free_dictionary_returns_none_for_an_unknown_word() -> None:
    async def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(404, json={"title": "No Definitions Found"})

    async with mock_client(httpx.MockTransport(handler)) as client:
        assert await FreeDictionaryProvider(client).lookup("zzzzqq", "en") is None


async def test_free_dictionary_raises_on_a_server_error() -> None:
    async def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(502, text="bad gateway")

    async with mock_client(httpx.MockTransport(handler)) as client:
        with pytest.raises(ProviderError):
            await FreeDictionaryProvider(client).lookup("run", "en")


async def test_free_dictionary_declines_non_english_source() -> None:
    async with mock_client(httpx.MockTransport(lambda _: httpx.Response(200))) as client:
        provider = FreeDictionaryProvider(client)
        assert provider.supports("en") is True
        assert provider.supports("uz") is False
        assert await provider.lookup("kitob", "uz") is None


# --- Azure ---------------------------------------------------------------------


async def test_azure_sends_one_batched_call_and_preserves_order() -> None:
    calls: list[list[dict[str, str]]] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        calls.append(json.loads(request.content))
        assert request.headers["Ocp-Apim-Subscription-Key"] == "key"
        assert request.url.params["to"] == "uz"
        return httpx.Response(200, json=load("azure_translate_run.json"))

    async with mock_client(httpx.MockTransport(handler)) as client:
        provider = AzureTranslationProvider(client, key="key", region="westeurope")
        out = await provider.translate(["a", "b", "c", "d", "e", "f"], "en", "uz")

    assert len(calls) == 1  # SPEC §6: one call, not one per string
    assert len(calls[0]) == 6
    assert out[0] == "Yugurib harakat qilmoq"
    assert out[-1] == "Uzluksiz davom etgan muddat"


async def test_azure_short_circuits_when_the_languages_match() -> None:
    async def handler(_: httpx.Request) -> httpx.Response:  # pragma: no cover
        raise AssertionError("no HTTP call should happen")

    async with mock_client(httpx.MockTransport(handler)) as client:
        provider = AzureTranslationProvider(client, key="key", region="r")
        assert await provider.translate(["a"], "uz", "uz") == ["a"]
        assert await provider.translate([], "en", "uz") == []


async def test_azure_rejects_a_response_of_the_wrong_length() -> None:
    """A misaligned batch would attach the wrong meaning to a word."""

    async def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=[{"translations": [{"text": "bitta"}]}])

    async with mock_client(httpx.MockTransport(handler)) as client:
        provider = AzureTranslationProvider(client, key="k", region="r")
        with pytest.raises(ProviderError):
            await provider.translate(["a", "b"], "en", "uz")


# --- Gemini --------------------------------------------------------------------


def _gemini_envelope(payload: dict[str, Any]) -> dict[str, Any]:
    return {"candidates": [{"content": {"parts": [{"text": json.dumps(payload)}]}}]}


async def test_gemini_returns_every_translation_via_a_hard_response_schema() -> None:
    captured: dict[str, Any] = {}

    async def handler(request: httpx.Request) -> httpx.Response:
        captured.update(json.loads(request.content))
        return httpx.Response(
            200,
            json=_gemini_envelope(
                {
                    "ipa": "/rʌn/",
                    "translations": [
                        {"text": "yugurmoq", "pos": "verb"},
                        {"text": "chopmoq", "pos": "verb"},
                        {"text": "boshqarmoq", "pos": "verb"},
                    ],
                }
            ),
        )

    async with mock_client(httpx.MockTransport(handler)) as client:
        provider = GeminiDictionaryProvider(client, api_key="k", model="gemini-3.6-flash")
        result = await provider.lookup("run", "en", "uz")

    assert captured["generationConfig"]["responseMimeType"] == "application/json"
    assert "responseSchema" in captured["generationConfig"]
    assert result is not None
    assert result.target_lang == "uz"
    assert [meaning.definition for meaning in result.meanings] == [
        "yugurmoq",
        "chopmoq",
        "boshqarmoq",
    ]
    assert result.ipa == "/rʌn/"


async def test_gemini_drops_repeated_translations() -> None:
    """A duplicate in a comma-separated line reads as a bug."""

    async def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json=_gemini_envelope(
                {
                    "translations": [
                        {"text": "suv"},
                        {"text": "Suv"},
                        {"text": "sug'ormoq"},
                    ]
                }
            ),
        )

    async with mock_client(httpx.MockTransport(handler)) as client:
        provider = GeminiDictionaryProvider(client, api_key="k", model="m")
        result = await provider.lookup("water", "en", "uz")

    assert result is not None
    assert [meaning.definition for meaning in result.meanings] == ["suv", "sug'ormoq"]


async def test_gemini_returns_none_for_a_word_that_does_not_exist() -> None:
    async def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=_gemini_envelope({"translations": []}))

    async with mock_client(httpx.MockTransport(handler)) as client:
        provider = GeminiDictionaryProvider(client, api_key="k", model="m")
        assert await provider.lookup("qqqzzz", "uz", "en") is None


async def test_gemini_dictionary_raises_on_an_unparseable_envelope() -> None:
    async def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"nope": True})

    async with mock_client(httpx.MockTransport(handler)) as client:
        provider = GeminiDictionaryProvider(client, api_key="k", model="m")
        with pytest.raises(ProviderError):
            await provider.lookup("run", "en", "uz")


async def test_gemini_translation_rejects_a_mismatched_batch() -> None:
    async def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=_gemini_envelope({"translations": ["bitta"]}))

    async with mock_client(httpx.MockTransport(handler)) as client:
        provider = GeminiTranslationProvider(client, api_key="k", model="m")
        with pytest.raises(ProviderError):
            await provider.translate(["a", "b"], "en", "uz")


# --- Registry ------------------------------------------------------------------


async def test_registry_falls_back_to_fakes_without_credentials() -> None:
    async with mock_client(httpx.MockTransport(lambda _: httpx.Response(200))) as client:
        registry = ProviderRegistry(client)

    assert registry.uses_fakes is True


async def test_the_chain_falls_back_to_gemini_for_any_pair() -> None:
    """Without Azure configured, one provider covers every language pair."""
    async with mock_client(httpx.MockTransport(lambda _: httpx.Response(200))) as client:
        registry = ProviderRegistry(client)
        chain = registry.chain_for("ru", "uz")

    assert chain.providers == (registry.gemini,)


async def test_azure_goes_first_when_it_covers_the_pair(monkeypatch: Any) -> None:
    """One dictionary call beats a model call on latency and on cost."""
    from app.core.config import settings

    monkeypatch.setattr(settings, "AZURE_TRANSLATOR_KEY", "key")
    monkeypatch.setattr(settings, "AZURE_TRANSLATOR_REGION", "westeurope")
    monkeypatch.setattr(settings, "UZ_PREFER_LLM", False)

    async with mock_client(httpx.MockTransport(lambda _: httpx.Response(200))) as client:
        registry = ProviderRegistry(client)

        covered = registry.chain_for("en", "ru")
        assert covered.providers[0] is registry.azure
        assert covered.providers[1] is registry.gemini

        # Azure's dictionary only goes to or from English.
        uncovered = registry.chain_for("ru", "tr")
        assert uncovered.providers == (registry.gemini,)


async def test_uz_prefer_llm_keeps_azure_out_of_the_way(monkeypatch: Any) -> None:
    """SPEC §6: general NMT handles Uzbek unevenly, so the model leads for `uz`."""
    from app.core.config import settings

    monkeypatch.setattr(settings, "AZURE_TRANSLATOR_KEY", "key")
    monkeypatch.setattr(settings, "AZURE_TRANSLATOR_REGION", "westeurope")
    monkeypatch.setattr(settings, "UZ_PREFER_LLM", True)

    async with mock_client(httpx.MockTransport(lambda _: httpx.Response(200))) as client:
        registry = ProviderRegistry(client)
        chain = registry.chain_for("en", "uz")

    assert chain.providers == (registry.gemini,)


async def test_azure_dictionary_parses_alternative_translations() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path.endswith("/dictionary/lookup")
        return httpx.Response(
            200,
            json=[
                {
                    "normalizedSource": "run",
                    "displaySource": "run",
                    "translations": [
                        {"displayTarget": "бежать", "posTag": "VERB"},
                        {"displayTarget": "запускать", "posTag": "VERB"},
                        {"displayTarget": "бежать", "posTag": "VERB"},
                    ],
                }
            ],
        )

    async with mock_client(httpx.MockTransport(handler)) as client:
        provider = AzureDictionaryProvider(client, key="k", region="r")
        result = await provider.lookup("run", "en", "ru")

    assert result is not None
    # Duplicates collapsed, order preserved.
    assert [meaning.definition for meaning in result.meanings] == ["бежать", "запускать"]
    assert result.meanings[0].pos == "verb"


async def test_azure_dictionary_declines_a_pair_it_cannot_serve() -> None:
    async with mock_client(httpx.MockTransport(lambda _: httpx.Response(200))) as client:
        provider = AzureDictionaryProvider(client, key="k", region="r")

        assert provider.supports_pair("en", "ru") is True
        assert provider.supports_pair("ru", "tr") is False
        assert provider.supports_pair("en", "uz") is False  # uz is not in the dictionary
        assert await provider.lookup("kitob", "uz", "tr") is None


def test_lookup_result_round_trips_through_json() -> None:
    original = LookupResult(
        term="run",
        source_lang="en",
        target_lang="uz",
        ipa="/ɹʌn/",
        meanings=[],
        provider="test",
    )

    assert LookupResult.from_dict(original.to_dict()) == original


def test_the_gemini_schema_uses_the_api_enum_casing() -> None:
    """Gemini's REST reference declares `Schema.type` as an enum — OBJECT, ARRAY,
    STRING — so that is the form sent, rather than JSON-Schema's lowercase spelling.

    This pins the documented contract. It was *not* the cause of the production
    failure that prompted it: that was a retired model name, which the response body
    named outright once provider errors started carrying it.
    """
    from app.providers.dictionary.gemini import _RESPONSE_SCHEMA

    def types(node: object) -> list[str]:
        found: list[str] = []
        if isinstance(node, dict):
            value = node.get("type")
            if isinstance(value, str):
                found.append(value)
            for child in node.values():
                found.extend(types(child))
        return found

    collected = types(_RESPONSE_SCHEMA)
    assert collected, "the schema declares no types at all"
    assert all(name.isupper() for name in collected), collected


async def test_a_provider_http_failure_carries_the_reason() -> None:
    """ "HTTP 400" alone cannot be acted on; the body is the only place that says why."""

    async def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(
            400, json={"error": {"message": "Invalid JSON payload received at generationConfig"}}
        )

    async with mock_client(httpx.MockTransport(handler)) as client:
        provider = GeminiDictionaryProvider(client, api_key="k", model="m")
        with pytest.raises(ProviderError) as exc:
            await provider.lookup("run", "en", "uz")

    assert "400" in str(exc.value)
    assert "Invalid JSON payload" in str(exc.value)


def test_the_default_gemini_model_is_configurable() -> None:
    """Google retires model names, and a retired one 404s the whole chain.

    The default has to be overridable without a code change, because the fix arrives
    as an error message in production, not as a deploy window.
    """
    from app.core.config import Settings

    assert Settings(GEMINI_MODEL="gemini-9-future").GEMINI_MODEL == "gemini-9-future"


async def test_a_transport_failure_is_named_and_marked_retryable() -> None:
    """An httpx timeout stringifies to nothing, so the naive form logs "gemini: "."""

    async def handler(_: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("")

    async with mock_client(httpx.MockTransport(handler)) as client:
        provider = GeminiDictionaryProvider(client, api_key="k", model="m")
        with pytest.raises(ProviderError) as exc:
            await provider.lookup("run", "en", "uz")

    assert "ReadTimeout" in str(exc.value)
    assert exc.value.retryable is True


async def test_an_http_failure_is_not_retryable() -> None:
    """The same request earns the same refusal; retrying only wastes the user's time."""

    async def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(400, json={"error": {"message": "bad request"}})

    async with mock_client(httpx.MockTransport(handler)) as client:
        provider = GeminiDictionaryProvider(client, api_key="k", model="m")
        with pytest.raises(ProviderError) as exc:
            await provider.lookup("run", "en", "uz")

    assert exc.value.retryable is False


async def test_a_transient_failure_is_retried_once_and_succeeds() -> None:
    """Measured at roughly one transient in sixteen live calls — enough that a user
    would meet it, in an app whose premise is that they do nothing extra."""
    attempts = 0

    async def handler(_: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise httpx.ConnectError("")
        return httpx.Response(
            200, json=_gemini_envelope({"translations": [{"text": "suv", "pos": "noun"}]})
        )

    from app.services.lookup_service import _call_with_one_retry

    async with mock_client(httpx.MockTransport(handler)) as client:
        provider = GeminiDictionaryProvider(client, api_key="k", model="m")
        result = await _call_with_one_retry(provider, "water", "en", "uz")

    assert attempts == 2
    assert result is not None
    assert result.meanings[0].definition == "suv"


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("'wɔːtər", "/ˈwɔːtər/"),
        ("kiˈtɔb", "/kiˈtɔb/"),
        ("/ˌsɛrənˈdɪpɪti/", "/ˌsɛrənˈdɪpɪti/"),
        ("[rʌn]", "/rʌn/"),
        ("", None),
        (None, None),
    ],
)
def test_ipa_is_normalised_to_one_form(raw: object, expected: str | None) -> None:
    """The model is inconsistent about slashes and stress marks within one prompt, and
    the app renders the value verbatim in a mono face."""
    from app.providers.dictionary.gemini import _normalise_ipa

    assert _normalise_ipa(raw) == expected
