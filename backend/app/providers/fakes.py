"""Fixture-backed providers used when a credential is absent (AGENT.md §3).

These are not stubs for the real path — the real providers are complete. These exist so
the app boots, the chain is exercised end to end, and tests never touch a live API
(SPEC §12). Selection happens in `registry.py`, driven purely by whether a key is set.
"""

from __future__ import annotations

from app.providers.base import LookupResult, Meaning

# Deterministic fixture data. `run` is the word SPEC §11 M2 accepts against.
_FIXTURES: dict[str, tuple[str | None, list[tuple[str | None, str, str]]]] = {
    "run": (
        "/rʌn/",
        [
            ("verb", "yugurmoq", "to move at a speed faster than walking"),
            ("verb", "boshqarmoq", "to manage or operate something"),
            ("noun", "yugurish", "an act of running"),
            ("noun", "muddat", "a continuous period of something"),
        ],
    ),
    "serendipity": (
        "/ˌsɛrənˈdɪpɪti/",
        [
            ("noun", "tasodifiy omad", "the occurrence of happy events by chance"),
            ("noun", "kutilmagan topilma", "an unplanned fortunate discovery"),
            ("noun", "xushtasodif", "the faculty of making desirable discoveries by accident"),
        ],
    ),
    "book": (
        "/bʊk/",
        [
            ("noun", "kitob", "a written or printed work consisting of pages"),
            ("verb", "band qilmoq", "to reserve something in advance"),
            ("noun", "daftar", "a set of blank sheets bound together"),
        ],
    ),
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
            meanings = [
                Meaning(pos=pos, definition=definition, gloss_en=gloss)
                for pos, definition, gloss in rows
            ]
        else:
            ipa = _GENERIC_IPA
            meanings = [
                Meaning(
                    pos="noun",
                    definition=f"{term} (namunaviy ma'no {index})",
                    gloss_en=f"fixture meaning {index} of {term}",
                    examples=[f"This is a fixture sentence with {term}."],
                )
                for index in (1, 2, 3)
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
