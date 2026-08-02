"""OCR of a delivery-list screenshot: read, sieve the watermark, split blocks.

Scope decision, on purpose: the parser is simple. It finds the address line by
its prefix (RUA/AV/...) and takes a best-effort guess at street/number. It does
not try to cover every possible format — the user reviews and edits every
field before anything is saved, and that editable field is what actually
closes the gap.
"""

import logging
import re
from typing import Any, Optional

import pytesseract

from .image_preprocessing import preprocess_for_ocr

logger = logging.getLogger(__name__)

OCR_LANGUAGE = "por"

# Watermark leftovers the OCR reads as separate text. Extend this list when a
# new screenshot shows a pattern that slipped through.
WATERMARK_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"^\d{4}-\d{2}-\d{2}$"),  # dates like 2026-08-02
    re.compile(r"^\d{10,}$"),  # long digit runs (never a house number)
    re.compile(r"^[|/\\_~—–-]+$"),  # diagonal strokes read as punctuation
]

# Lines that start an address.
STREET_PREFIXES = (
    "RUA",
    "R.",
    "AV",
    "AVENIDA",
    "TRAVESSA",
    "TV",
    "ALAMEDA",
    "ESTRADA",
    "RODOVIA",
    "PRACA",
    "PRAÇA",
    "LINHA",
)

# A delivery block usually starts with the order id.
ORDER_ID_PATTERN = re.compile(r"^[A-Z]{0,4}[-\s]?\d{6,}$")


def is_watermark(line: str) -> bool:
    """True when the line is watermark noise rather than delivery data."""
    stripped = line.strip()
    if not stripped:
        return False
    return any(pattern.match(stripped) for pattern in WATERMARK_PATTERNS)


def filter_watermark(text: str) -> str:
    """Drop the lines the watermark contributed.

    Only removes watermark that the OCR read as *separate* text. Where the
    watermark crossed a letter and smudged it, the damage is already in the
    pixels — that goes to the human review screen.
    """
    kept = [line for line in text.splitlines() if not is_watermark(line)]
    return "\n".join(kept)


def extract_text(image_bytes: bytes) -> str:
    """Preprocess, OCR in Portuguese and sieve the watermark."""
    processed = preprocess_for_ocr(image_bytes)
    raw = pytesseract.image_to_string(processed, lang=OCR_LANGUAGE)
    return filter_watermark(raw)


def _looks_like_street(line: str) -> bool:
    upper = line.strip().upper()
    return any(
        upper.startswith(prefix + " ") or upper.startswith(prefix + ".")
        for prefix in STREET_PREFIXES
    )


def _split_blocks(lines: list[str]) -> list[list[str]]:
    """Split the page into delivery blocks.

    Two heuristics, in order: an order id starts a new block; otherwise a
    blank line separates cards.
    """
    blocks: list[list[str]] = []
    current: list[str] = []

    for line in lines:
        stripped = line.strip()

        if ORDER_ID_PATTERN.match(stripped) and current:
            blocks.append(current)
            current = [stripped]
            continue

        if not stripped:
            if current:
                blocks.append(current)
                current = []
            continue

        current.append(stripped)

    if current:
        blocks.append(current)

    return blocks


def _guess_fields(block: list[str]) -> dict[str, Optional[str]]:
    """Best-effort street/number/neighborhood. Empty when unsure — never invented."""
    guess: dict[str, Optional[str]] = {
        "street": None,
        "number": None,
        "neighborhood": None,
    }

    street_line = next((line for line in block if _looks_like_street(line)), None)
    if street_line is None:
        return guess

    # "RUA RESIDENCIAL FLORENÇA UM, 8046, CASA" -> parts around commas
    parts = [part.strip() for part in street_line.split(",") if part.strip()]
    guess["street"] = parts[0] if parts else None

    for part in parts[1:]:
        if re.fullmatch(r"\d{1,6}", part):
            guess["number"] = part
            break

    if guess["number"] is None:
        # number glued to the end of the street name
        trailing = re.search(r"\b(\d{1,6})\s*$", parts[0] if parts else "")
        if trailing:
            guess["number"] = trailing.group(1)
            guess["street"] = parts[0][: trailing.start()].strip(" ,-")

    # A short line right after the street is usually the neighborhood.
    street_index = block.index(street_line)
    for line in block[street_index + 1 :]:
        candidate = line.strip(" ,-")
        if 2 < len(candidate) <= 40 and not _looks_like_street(candidate):
            if not re.search(r"\d{4,}", candidate):
                guess["neighborhood"] = candidate
                break

    return guess


def parse_addresses(ocr_text: str) -> list[dict[str, Any]]:
    """Split OCR text into delivery blocks with a best-effort field guess.

    Every block always carries ``raw_text`` so the user can fix whatever the
    guess got wrong.
    """
    lines = ocr_text.splitlines()
    blocks = _split_blocks(lines)

    parsed: list[dict[str, Any]] = []
    for block in blocks:
        text = "\n".join(block).strip()
        if not text:
            continue
        parsed.append({"raw_text": text, **_guess_fields(block)})

    return parsed
