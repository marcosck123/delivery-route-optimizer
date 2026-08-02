"""OCR of the J&T delivery-list screen: read, sieve, split into deliveries.

This parser is tailored to ONE screen — the J&T app's delivery list — and
exploits its fixed structure. Each card looks like this:

    888030841672038                  <- order id: 15 digits, starts with 888
    MARCELA FLORINDA FUR...          <- recipient, usually truncated
    RUA RESIDENCIAL FLORENÇA-UM      <- address, repetition 1 (summary)
    RESIDENCIAL FLORENCA Vilhena     <- repetition 1: neighborhood + city
    RO RUA RESIDENCIAL FLORENÇA-     <- "RO" then repetition 2 begins
    UM, 8046, CASA 76985662          <- street + number + complement + CEP
    2026-08-01 18:24:00              <- date/time: the address ends before it
    [buttons]                        <- UI, discarded

So: the order id opens a block, the date closes the address, and the good
address is the LAST street occurrence before that date (repetition 2 is the
complete one). Anything before the first order id is the app header.

Being screen-specific is the point, and the trade-off is accepted: if J&T
changes the layout this breaks. It is a personal tool over a stable screen.

The OCR still garbles characters where the watermark crosses a glyph — the
house number especially. The goal here is not perfection, it is that the
fields arrive filled in and nearly right, so she fixes a digit instead of
typing everything.
"""

import logging
import re
from typing import Any, Optional

import pytesseract

from .image_preprocessing import preprocess_for_ocr

logger = logging.getLogger(__name__)

OCR_LANGUAGE = "por"

# Order id: 15 digits starting with 888. Tolerant on both counts, because the
# OCR sometimes eats or invents one digit.
ORDER_ID_PATTERN = re.compile(r"\b(\d{14,16})\b")

# Closes the address inside a block.
DATE_PATTERN = re.compile(r"\b\d{4}-\d{2}-\d{2}\b")

# Vilhena CEPs come out unformatted: 76985662 -> 76985-662
CEP_PATTERN = re.compile(r"\b(\d{5})-?(\d{3})\b")

STREET_PREFIXES = (
    "RUA",
    "AVENIDA",
    "AV",
    "TRAVESSA",
    "TV",
    "RODOVIA",
    "ALAMEDA",
    "ESTRADA",
    "LINHA",
    "PRACA",
    "PRAÇA",
)
STREET_START_PATTERN = re.compile(
    r"\b(" + "|".join(STREET_PREFIXES) + r")\b[\s.]", re.IGNORECASE
)

COMPLEMENT_KEYWORDS = (
    "CASA",
    "APTO",
    "APARTAMENTO",
    "AP",
    "BLOCO",
    "FUNDOS",
    "QUADRA",
    "LOTE",
    "SOBRADO",
    "CHACARA",
    "CHÁCARA",
)
COMPLEMENT_PATTERN = re.compile(
    r"\b(" + "|".join(COMPLEMENT_KEYWORDS) + r")\b.*$", re.IGNORECASE
)

# Chrome of the app: tabs, filters, search bar, action buttons. Substring
# match, case-insensitive. Extend this list when a new screenshot shows
# something that slipped through.
UI_NOISE_PATTERNS = [
    "recibo de transfer",
    "entrega",
    "pendente",
    "assinado",
    "assinar",
    "pacote",
    "problemático",
    "problematico",
    "últimos 7 dias",
    "ultimos 7 dias",
    "filtro de data",
    "roteirização",
    "roteirizacao",
    "por favor",
    "insira",
    "procurar",
    "nav",
    "telefone",
    "registro de anomalia",
    "número do pedido",
    "numero do pedido",
]

# Watermark leftovers the OCR reads as separate text.
WATERMARK_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"^\d{4}-\d{2}-\d{2}$"),  # bare dates from the watermark grid
    re.compile(r"^\d{17,}$"),  # very long digit runs — never an order id
    re.compile(r"^[|/\\_~—–-]+$"),  # diagonal strokes read as punctuation
]

# The city is fixed; used to pull the neighborhood out of repetition 1.
CITY = "Vilhena"


def _normalize_line(line: str) -> str:
    """Unify dashes and whitespace so the patterns above have one shape to match."""
    line = line.replace("–", "-").replace("—", "-").replace("−", "-")
    return re.sub(r"\s+", " ", line).strip()


def is_order_id(line: str) -> bool:
    stripped = line.strip()
    return bool(ORDER_ID_PATTERN.fullmatch(stripped))


def is_watermark(line: str) -> bool:
    """True when the line is watermark noise rather than delivery data."""
    stripped = line.strip()
    if not stripped:
        return False
    # An order id is a long digit run too — it must never be sieved out, since
    # it is what separates one delivery from the next.
    if is_order_id(stripped):
        return False
    return any(pattern.match(stripped) for pattern in WATERMARK_PATTERNS)


def starts_with_street(line: str) -> bool:
    return bool(STREET_START_PATTERN.match(line.strip()))


def contains_street(line: str) -> bool:
    return bool(STREET_START_PATTERN.search(line.strip()))


def is_ui_noise(line: str) -> bool:
    """True for app chrome (tabs, filters, buttons).

    A line holding an address is never discarded, even when it contains one of
    the fragments above: "AVENIDA NAVEGANTES" contains "nav", and repetition 2
    arrives as "RO AVENIDA NAVEGANTES, 100" — the street is in the middle of
    the line, not at the start, so this check has to look anywhere in it.
    """
    stripped = line.strip().lower()
    if not stripped:
        return False
    if contains_street(stripped) or is_order_id(stripped):
        return False
    return any(pattern in stripped for pattern in UI_NOISE_PATTERNS)


def filter_watermark(text: str) -> str:
    """Drop the lines the watermark contributed.

    Only removes watermark the OCR read as *separate* text. Where it crossed a
    letter and smudged it, the damage is already in the pixels — that is what
    the human review screen is for.
    """
    kept = [line for line in text.splitlines() if not is_watermark(line)]
    return "\n".join(kept)


def extract_text(image_bytes: bytes) -> str:
    """Preprocess, OCR in Portuguese and sieve the watermark."""
    processed = preprocess_for_ocr(image_bytes)
    raw = pytesseract.image_to_string(processed, lang=OCR_LANGUAGE)
    return filter_watermark(raw)


def _clean_lines(ocr_text: str) -> list[str]:
    lines = (_normalize_line(line) for line in ocr_text.splitlines())
    return [
        line
        for line in lines
        if line and not is_watermark(line) and not is_ui_noise(line)
    ]


def _split_into_cards(lines: list[str]) -> list[tuple[str, list[str]]]:
    """Split the screen into (order_id, lines) cards.

    Everything before the first order id is the app header and is dropped.
    """
    cards: list[tuple[str, list[str]]] = []
    order_id: Optional[str] = None
    current: list[str] = []

    for line in lines:
        match = ORDER_ID_PATTERN.fullmatch(line)
        if match:
            if order_id is not None:
                cards.append((order_id, current))
            order_id = match.group(1)
            current = []
            continue
        if order_id is not None:
            current.append(line)

    if order_id is not None:
        cards.append((order_id, current))

    return cards


def _cut_at_date(lines: list[str]) -> tuple[list[str], list[str]]:
    """Split a card at the date: (address side, discarded side)."""
    for index, line in enumerate(lines):
        match = DATE_PATTERN.search(line)
        if match:
            head = lines[:index]
            # keep whatever preceded the date on the same line
            prefix = line[: match.start()].strip()
            if prefix:
                head = head + [prefix]
            return head, lines[index:]
    return lines, []


def _join_address(chunks: list[str]) -> str:
    """Join address chunks, gluing words the screen broke across lines.

    "RUA RESIDENCIAL FLORENÇA-" + "UM, 8046" -> "RUA RESIDENCIAL FLORENÇA-UM, 8046"
    """
    joined = ""
    for chunk in chunks:
        chunk = chunk.strip()
        if not chunk:
            continue
        if not joined:
            joined = chunk
        elif joined.endswith("-"):
            joined += chunk
        else:
            joined += " " + chunk
    return joined


def _find_address_segment(lines: list[str]) -> tuple[Optional[str], list[str]]:
    """Return (address text, lines before it).

    The good address is the LAST street occurrence: repetition 1 is a summary
    without the house number, repetition 2 is the complete one.
    """
    last_line_index: Optional[int] = None
    last_char_index = 0

    for index, line in enumerate(lines):
        for match in STREET_START_PATTERN.finditer(line):
            last_line_index = index
            last_char_index = match.start()

    if last_line_index is None:
        return None, lines

    first_chunk = lines[last_line_index][last_char_index:]
    segment = _join_address([first_chunk, *lines[last_line_index + 1 :]])
    return segment, lines[:last_line_index]


def _fix_ocr_digits(token: str) -> str:
    """Repair O/I read inside a number ("8O46" -> "8046").

    Only touches tokens that are already mostly digits; anything ambiguous is
    left exactly as read, for her to correct.
    """
    if re.fullmatch(r"[0-9OoIl]+", token) and any(char.isdigit() for char in token):
        return token.translate(str.maketrans({"O": "0", "o": "0", "I": "1", "l": "1"}))
    return token


def _extract_cep(segment: str) -> tuple[Optional[str], str]:
    match = CEP_PATTERN.search(segment)
    if not match:
        return None, segment
    cep = f"{match.group(1)}-{match.group(2)}"
    return cep, (segment[: match.start()] + " " + segment[match.end() :]).strip()


def _extract_complement(segment: str) -> tuple[Optional[str], str]:
    match = COMPLEMENT_PATTERN.search(segment)
    if not match:
        return None, segment
    complement = match.group(0).strip(" ,-")
    return (complement or None), segment[: match.start()].strip()


def _extract_number(segment: str) -> tuple[Optional[str], str]:
    """Pull the house number out, leaving the street behind.

    Only digits count as a number: the street "RESIDENCIAL FLORENÇA-UM" ends
    in the *word* "um", which is part of the name, not the number.
    """
    parts = [part.strip() for part in segment.split(",")]

    for index, part in enumerate(parts[1:], start=1):
        fixed = _fix_ocr_digits(part)
        if re.fullmatch(r"\d{1,6}", fixed):
            street = ", ".join(parts[:index]).strip(" ,-")
            return fixed, street

    # No comma: the number may be glued to the end of the street name.
    trailing = re.search(r"\s(\d{1,6})\s*$", parts[0])
    if trailing:
        return trailing.group(1), parts[0][: trailing.start()].strip(" ,-")

    return None, segment.strip(" ,-")


def _guess_neighborhood(lines: list[str]) -> Optional[str]:
    """Read the neighborhood off repetition 1, which carries "<bairro> Vilhena"."""
    for line in reversed(lines):
        if CITY.lower() in line.lower():
            candidate = re.split(CITY, line, flags=re.IGNORECASE)[0]
            candidate = candidate.strip(" ,-")
            if candidate and not starts_with_street(candidate):
                return candidate
    return None


def parse_address_fields(segment: str) -> dict[str, Optional[str]]:
    """Break "RUA X-UM, 8046, CASA 76985662" into its parts."""
    cep, rest = _extract_cep(segment)
    complement, rest = _extract_complement(rest)
    number, street = _extract_number(rest)

    return {
        "street": street.strip(" ,-") or None,
        "number": number,
        "complement": complement,
        "cep": cep,
    }


def parse_addresses(ocr_text: str) -> list[dict[str, Any]]:
    """Split the OCR text into deliveries with their address fields.

    Cards that are clearly noise — no order id, or no street at all — are
    dropped instead of becoming empty entries for her to delete by hand.

    Two orders to the same house stay as two deliveries: no deduplication.
    """
    cards = _split_into_cards(_clean_lines(ocr_text))

    parsed: list[dict[str, Any]] = []
    for order_id, lines in cards:
        if not lines:
            continue

        address_lines, _ = _cut_at_date(lines)
        segment, preceding = _find_address_segment(address_lines)
        if not segment:
            logger.info("Card %s dropped: no street found", order_id)
            continue

        fields = parse_address_fields(segment)
        if not fields["street"]:
            continue

        parsed.append(
            {
                "order_id": order_id,
                "raw_text": "\n".join(lines).strip(),
                "neighborhood": _guess_neighborhood(preceding),
                **fields,
            }
        )

    return parsed
