"""Fixture-backed providers used when a credential is absent (AGENT.md §3).

These are not stubs for the real path — the real providers are complete. These exist so
the app boots, the chain is exercised end to end, and tests never touch a live API
(SPEC §12). Selection happens in `registry.py`, driven purely by whether a key is set.
"""

from __future__ import annotations

from app.providers.base import LookupResult, Meaning

# Deterministic fixture data: a word mapped to its translations, exactly the shape a
# real provider returns.
_FIXTURES: dict[str, tuple[str | None, list[tuple[str | None, str]]]] = {
    "run": (
        "/rʌn/",
        [("verb", "yugurmoq"), ("verb", "chopmoq"), ("verb", "boshqarmoq"), ("noun", "yugurish")],
    ),
    "book": ("/bʊk/", [("noun", "kitob"), ("verb", "band qilmoq"), ("noun", "daftar")]),
    "serendipity": (
        "/ˌsɛrənˈdɪpɪti/",
        [(None, "tasodifiy omad"), (None, "kutilmagan topilma")],
    ),
    "water": ("/ˈwɔːtər/", [("noun", "suv"), ("verb", "sug'ormoq")]),
}

_GENERIC_IPA = "/ˈfɪkstʃə/"


class FakeDictionaryProvider:
    """Serves the fixtures above, and a plausible generic entry for anything else."""

    name = "fake_dictionary"

    def supports(self, source_lang: str) -> bool:
        del source_lang
        return True

    async def lookup(
        self, term: str, source_lang: str, target_lang: str | None = None
    ) -> LookupResult | None:
        target = target_lang or "uz"
        key = term.strip().casefold()

        if key in _FIXTURES:
            ipa, rows = _FIXTURES[key]
            meanings = [Meaning(pos=pos, definition=text, gloss_en=None) for pos, text in rows]
        else:
            ipa = _GENERIC_IPA
            meanings = [
                Meaning(pos=None, definition=f"{term} ({target} tarjimasi {index})", gloss_en=None)
                for index in (1, 2)
            ]

        return LookupResult(
            term=term,
            source_lang=source_lang,
            target_lang=target,
            ipa=ipa,
            meanings=meanings,
            provider=self.name,
        )


class FakeTranslationProvider:
    """Echoes each text with a marker, so a missed translation is visible in tests."""

    name = "fake_translation"

    async def translate(self, texts: list[str], source_lang: str, target_lang: str) -> list[str]:
        if source_lang == target_lang:
            return list(texts)
        return [f"[{target_lang}] {text}" for text in texts]
