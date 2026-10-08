"""The language of a task, found by its alphabet (no model needed).

Used to tell the model which language to write in, and to check that it
did. An alphabet cannot tell Russian from Ukrainian or English from
German: the first language of each alphabet is assumed. That is enough
for the model note ("write in Russian"); a wrong guess still gives text
in the right alphabet.
"""

import re
import unicodedata
from dataclasses import dataclass


@dataclass(frozen=True)
class Language:
    code: str
    name: str  # in English, for prompts


ENGLISH = Language("en", "English")

# Unicode name prefix of a letter -> language.
_SCRIPTS = (
    ("CYRILLIC", Language("ru", "Russian")),
    ("GREEK", Language("el", "Greek")),
    ("ARABIC", Language("ar", "Arabic")),
    ("HEBREW", Language("he", "Hebrew")),
    ("DEVANAGARI", Language("hi", "Hindi")),
    ("HANGUL", Language("ko", "Korean")),
    ("HIRAGANA", Language("ja", "Japanese")),
    ("KATAKANA", Language("ja", "Japanese")),
    ("CJK", Language("zh", "Chinese")),
    ("LATIN", ENGLISH),
)

# Not part of the text: [n] marks, links, code spans.
_NOISE = re.compile(r"\[\d+\]|https?://\S+|`[^`]*`")


def _script(char: str) -> str | None:
    name = unicodedata.name(char, "")
    for prefix, _ in _SCRIPTS:
        if name.startswith(prefix):
            return prefix
    return None


def _shares(text: str) -> dict[str, float]:
    counts: dict[str, int] = {}
    total = 0
    for char in _NOISE.sub(" ", text):
        if char.isalpha():
            total += 1
            if script := _script(char):
                counts[script] = counts.get(script, 0) + 1
    return {s: n / total for s, n in counts.items()} if total else {}


def detect(text: str) -> Language:
    """The language of the alphabet most letters use; English if unsure."""
    shares = _shares(text)
    if not shares:
        return ENGLISH
    best = max(shares, key=lambda s: shares[s])
    if best == "CJK" and ("HIRAGANA" in shares or "KATAKANA" in shares):
        best = "HIRAGANA"  # Japanese mixes kana and kanji
    return next(lang for prefix, lang in _SCRIPTS if prefix == best)


def matches(text: str, language: Language, minimum: float = 0.5) -> bool:
    """Is most of the text in the alphabet of this language? Short texts
    (a few letters) always match: there is nothing to judge."""
    shares = _shares(text)
    letters_needed = 20
    if sum(1 for c in text if c.isalpha()) < letters_needed:
        return True
    prefixes = {p for p, lang in _SCRIPTS if lang.code == language.code}
    if language.code == "ja":
        prefixes.add("CJK")
    return sum(shares.get(p, 0) for p in prefixes) >= minimum


def note(language: Language) -> str | None:
    """The line added to every prompt of a task that is not in English."""
    if language.code == ENGLISH.code:
        return None
    return (
        f"Language: the task is written in {language.name}. Write all your own text "
        f"(questions, claims, headings, paragraphs, summaries, notes) in {language.name}. "
        "Copy quotes word for word in the language of their source; do not translate them. "
        "Keep code, file names, JSON keys and fixed answer values as they are."
    )
