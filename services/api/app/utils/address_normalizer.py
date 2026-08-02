"""Brazilian address normalization helpers.

Two jobs:

1. ``normalize_address_key`` builds the stable key used by the geocode cache,
   so "Rua Três, 120 — Centro" and "rua tres 120 centro" hit the same entry.
2. ``spell_out_to_number`` / ``street_with_digits`` turn spelled-out street
   numbers into digits ("Rua três mil e quinhentos" -> "Rua 3500"). Delivery
   apps write these both ways, and Google returns different points depending
   on the spelling — the cross-check in ``geocoding.py`` relies on this.
"""

import re
import unicodedata
from typing import Optional

# Word -> value. Accent-free keys: the text is normalized before lookup.
_UNITS = {
    "um": 1,
    "uma": 1,
    "dois": 2,
    "duas": 2,
    "tres": 3,
    "quatro": 4,
    "cinco": 5,
    "seis": 6,
    "sete": 7,
    "oito": 8,
    "nove": 9,
}

_TEENS = {
    "dez": 10,
    "onze": 11,
    "doze": 12,
    "treze": 13,
    "catorze": 14,
    "quatorze": 14,
    "quinze": 15,
    "dezesseis": 16,
    "dezessete": 17,
    "dezoito": 18,
    "dezenove": 19,
}

_TENS = {
    "vinte": 20,
    "trinta": 30,
    "quarenta": 40,
    "cinquenta": 50,
    "sessenta": 60,
    "setenta": 70,
    "oitenta": 80,
    "noventa": 90,
}

_HUNDREDS = {
    "cem": 100,
    "cento": 100,
    "duzentos": 200,
    "trezentos": 300,
    "quatrocentos": 400,
    "quinhentos": 500,
    "seiscentos": 600,
    "setecentos": 700,
    "oitocentos": 800,
    "novecentos": 900,
}

_ADDENDS = {**_UNITS, **_TEENS, **_TENS, **_HUNDREDS}
_MULTIPLIERS = {"mil": 1000}

# Words that may appear inside a spelled-out number without breaking it.
_GLUE = {"e"}

NUMBER_WORDS = set(_ADDENDS) | set(_MULTIPLIERS)


def strip_accents(text: str) -> str:
    decomposed = unicodedata.normalize("NFKD", text)
    return "".join(char for char in decomposed if not unicodedata.combining(char))


def normalize_address_key(
    street: str, number: str, neighborhood: str, city: str = ""
) -> str:
    """Stable cache key: lowercase, accent-free, punctuation-free, single spaces."""
    raw = " ".join(part for part in (street, number, neighborhood, city) if part)
    text = strip_accents(raw).lower()
    text = re.sub(r"[^a-z0-9\s]", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def spell_out_to_number(text: str) -> Optional[int]:
    """Parse a Portuguese spelled-out number. Returns ``None`` when unsure.

    Never guesses: any unknown word makes the whole parse fail, so we don't
    invent a house number that was never written.
    """
    if not text or not text.strip():
        return None

    words = [
        word
        for word in re.split(r"[\s-]+", strip_accents(text).lower())
        if word and word not in _GLUE
    ]
    if not words:
        return None

    total = 0
    current = 0
    saw_value = False

    for word in words:
        if word in _ADDENDS:
            current += _ADDENDS[word]
            saw_value = True
        elif word in _MULTIPLIERS:
            # "mil" alone means 1000; "três mil" means 3 * 1000
            current = (current or 1) * _MULTIPLIERS[word]
            total += current
            current = 0
            saw_value = True
        else:
            return None  # unknown word: refuse to guess

    return total + current if saw_value else None


def _number_word_runs(words: list[str]) -> list[tuple[int, int]]:
    """Index ranges of consecutive number words (glue words allowed inside)."""
    runs: list[tuple[int, int]] = []
    start: Optional[int] = None

    for index, word in enumerate(words):
        normalized = strip_accents(word).lower().strip(".,;:")
        if normalized in NUMBER_WORDS:
            if start is None:
                start = index
            end = index
        elif normalized in _GLUE and start is not None:
            continue  # "e" only counts when surrounded by number words
        elif start is not None:
            runs.append((start, end))
            start = None

    if start is not None:
        runs.append((start, end))
    return runs


def street_with_digits(street: str) -> Optional[str]:
    """Rewrite spelled-out numbers in a street name as digits.

    Returns ``None`` when there is nothing to convert, which tells the caller
    to skip the cross-check entirely.
    """
    if not street or not street.strip():
        return None

    words = street.split()
    runs = _number_word_runs(words)
    if not runs:
        return None

    replaced = False
    result = list(words)

    # Replace from the end so earlier indexes stay valid.
    for start, end in reversed(runs):
        phrase = " ".join(words[start : end + 1])
        value = spell_out_to_number(phrase)
        if value is None:
            continue
        result[start : end + 1] = [str(value)]
        replaced = True

    if not replaced:
        return None

    candidate = " ".join(result)
    return candidate if candidate != street else None


def build_full_address(
    street: str,
    number: str,
    neighborhood: str,
    cep: Optional[str] = None,
    complement: Optional[str] = None,
) -> str:
    """Human-readable one-liner stored in ``Delivery.address``."""
    head = f"{street}, {number}".strip().strip(",")
    parts = [head]
    if complement:
        parts.append(complement)
    if neighborhood:
        parts.append(neighborhood)
    if cep:
        parts.append(f"CEP {cep}")
    return " - ".join(part for part in parts if part)
