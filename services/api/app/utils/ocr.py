"""OCR of the J&T delivery-list screen: read, sieve, split into deliveries.

This parser is tailored to ONE screen — the J&T app's delivery list. Idealized,
a card looks like this:

    888030841672038                  <- order id
    MARCELA FLORINDA FUR...          <- recipient, usually truncated
    RUA RESIDENCIAL FLORENÇA-UM      <- address, repetition 1 (summary)
    RESIDENCIAL FLORENCA Vilhena     <- repetition 1: neighborhood + city
    RO RUA RESIDENCIAL FLORENÇA-     <- "RO" then repetition 2 begins
    UM, 8046, CASA 76985662          <- street + number + complement + CEP
    2026-08-01 18:24:00              <- date/time: the address ends here
    [buttons]                        <- UI, discarded

What actually comes out of Tesseract is nothing like that clean. Real output:

    | ss8030841672038 O GU
    1;RUA RESIDENCIAL FLORENÇA-UM O nav...ção
    RO RUA RESIDENCIAL ori o eo) Telefone
    UM, 8046, CASA 76985662 q”

The order id lost its leading digits to letters, the address is split across
lines with UI text wedged in the middle, and whole cards arrive glued into a
single line with no separators at all. So this parser does NOT read structure
line by line. It:

1. flattens everything into one continuous string;
2. masks timestamps (they also close an address) so a CEP cannot fuse with a
   year into a fake order id — "76985662" + "2026-08-01" reads as 12 digits;
3. deletes known UI chrome;
4. cuts cards at any run of 12+ digits, keeping only the digits as the id;
5. extracts each field independently by regex over the whole card, so a
   mangled street does not cost us the house number or the CEP.

Robustness beats precision here: the text is dirty by nature, every field is
editable in the UI, and returning three cards with nearly-right fields is worth
much more than returning none. Fields that cannot be read are left empty — the
parser never invents one.
"""

import logging
import re
from typing import Any, Optional

import pytesseract

from .image_preprocessing import preprocess_for_ocr

logger = logging.getLogger(__name__)

OCR_LANGUAGE = "por"

# Order id: a long digit run anywhere, however dirty its surroundings
# ("| ss8030841672038 O GU" -> "8030841672038"). Only the digits are kept, and
# a missing or extra digit is accepted — it is OCR. The second alternative
# survives one stray character dropped inside the run ("88803084:672038");
# it never spans whitespace, so two separate numbers cannot fuse into one.
ORDER_ID_DIGITS = re.compile(r"\d{12,}|\d{8,}[^\d\s]\d{4,}")

# Timestamps close an address; everything after one is buttons.
DATE_PATTERN = re.compile(r"\b\d{4}-\d{2}-\d{2}\b")
LOOSE_DATE_PATTERN = re.compile(r"\d{3,4}\D{0,3}-\D{0,2}\d{2}\D{0,2}-\D{0,2}\d{2}")
TIME_PATTERN = re.compile(r"\d{1,2}\s*[:.]\s*\d{2}\s*[:.]\s*\d{2}")
# No \b before the year on purpose: the OCR glues the CEP to the date
# ("...CASA 769856622026-08-01"), and a word boundary would never fire there,
# leaving a 12-digit run that reads as a fake order id.
TIMESTAMP_PATTERN = re.compile(
    r"\d{4}-\d{2}-\d{2}(?:\s*\d{1,2}[:.]\d{2}(?:[:.]\d{2})?)?"
)
# Marks where a timestamp was, so a card can still be cut there.
DATE_SENTINEL = "\x00"

# Marks where a line ended. The screen prints the street on one line and
# "<bairro> Vilhena" on the next; flattening everything into one string loses
# that boundary and the street swallows the neighborhood. Field regexes ignore
# this marker (they run over a flattened copy), but a street name never crosses
# it.
LINE_BREAK = "\x01"

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
# No \b at the front: the OCR glues the street to the previous word
# ("Viera fochaRua Residencial..."), and requiring a boundary there loses the
# cleanest spelling of the name. A prefix caught inside another word yields a
# short clean run and loses the scoring anyway.
STREET_START_PATTERN = re.compile(
    r"(" + "|".join(STREET_PREFIXES) + r")\b[\s.]", re.IGNORECASE
)

COMPLEMENT_KEYWORDS = (
    "CASA",
    "APTO",
    "APARTAMENTO",
    "BLOCO",
    "FUNDOS",
    "QUADRA",
    "LOTE",
    "SOBRADO",
    "CHACARA",
    "CHÁCARA",
)
# The keyword plus, at most, a short unit designation ("APTO 302", "BLOCO B").
# The unit part stays case-sensitive — under IGNORECASE, [A-Z] would also match
# the lowercase debris the OCR leaves behind ("CASA q”").
COMPLEMENT_PATTERN = re.compile(
    r"\b(?i:" + "|".join(COMPLEMENT_KEYWORDS) + r")\b(?:\s+(?:\d{1,5}[A-Z]?|[A-Z]{1,2}\b))?"
)

# App chrome. Word boundaries where a fragment could otherwise eat an address:
# plain "nav" would corrupt "AVENIDA NAVEGANTES".
UI_NOISE_PATTERNS = [
    re.compile(pattern, re.IGNORECASE)
    for pattern in (
        r"registro de anomalia",
        r"nav\.{2,}\S*",
        r"\bnav\b",
        r"navega[çc][ãa]o",
        r"\btelefone\b",
        r"por favor,?\s*insira",
        r"\binsira\b",
        r"recibo de \w*",
        r"transfer\w*",
        r"\bentrega\b",
        r"pendente(?:\(\d+\))?",
        r"\bassinad[oa]\b",
        r"\bassinar\b",
        r"\bpacote\b",
        r"problem[áa]tico",
        r"[úu]ltimos \d+ dias",
        r"filtro de datas?v?",
        r"roteiriza[çc][ãa]o",
        r"\bprocurar\b",
        r"\bcoser\b",
        r"n[úu]\.{2,}dido",
    )
]

# Watermark leftovers the OCR reads as separate text.
WATERMARK_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"^\d{4}-\d{2}-\d{2}$"),  # bare dates from the watermark grid
    re.compile(r"^\d{17,}$"),  # very long digit runs — never an order id
    re.compile(r"^[|/\\_~—–-]+$"),  # diagonal strokes read as punctuation
]

# The city is fixed; used to pull the neighborhood out of repetition 1.
CITY = "Vilhena"

# Characters the OCR sprinkles around real words.
JUNK_EDGE = "\"'“”‘’()[]{}<>*|;:,.!?~^`—–-_ "
# A quote or bracket glued to the FRONT of a word marks a seam where the OCR
# ran two screen elements together ("FLORENÇA-UMEK “RESIDENCIAL"). A street
# name never continues past one.
SEAM_PREFIX = "\"“”'‘’([{<*"
CONNECTORS = {"DE", "DA", "DO", "DAS", "DOS", "E"}


# --------------------------------------------------------------- leitura


def read_raw_text(image_bytes: bytes) -> str:
    """Preprocess and OCR in Portuguese, with no sieve applied.

    Split out from ``extract_text`` so the caller can see exactly what
    Tesseract produced, before anything is dropped.
    """
    processed = preprocess_for_ocr(image_bytes)
    return pytesseract.image_to_string(processed, lang=OCR_LANGUAGE)


def extract_text(image_bytes: bytes) -> str:
    """Preprocess, OCR in Portuguese and sieve the watermark."""
    return filter_watermark(read_raw_text(image_bytes))


def looks_like_timestamp(line: str) -> bool:
    """Date and/or time — where the address ends inside a card."""
    stripped = line.strip()
    return bool(
        DATE_PATTERN.search(stripped)
        or TIME_PATTERN.search(stripped)
        or LOOSE_DATE_PATTERN.search(stripped)
    )


def read_order_id(text: str) -> Optional[str]:
    """Return the order id in this text, keeping only its digits.

    A timestamp collapses to 14 digits too ("2026-08-01 18:24:00"), so it is
    ruled out first — otherwise every card would be split twice.
    """
    stripped = text.strip()
    if not stripped or looks_like_timestamp(stripped):
        return None

    match = ORDER_ID_DIGITS.search(stripped)
    return re.sub(r"\D", "", match.group(0)) if match else None


def is_order_id(text: str) -> bool:
    return read_order_id(text) is not None


def is_watermark(line: str) -> bool:
    """True when the line is watermark noise rather than delivery data."""
    stripped = line.strip()
    if not stripped:
        return False
    # The 17-digit threshold is what keeps an order id (13-15 digits) out of
    # here: it is the marker separating one delivery from the next, and sieving
    # it out used to make the whole screen unparseable.
    return any(pattern.match(stripped) for pattern in WATERMARK_PATTERNS)


def starts_with_street(line: str) -> bool:
    return bool(STREET_START_PATTERN.match(line.strip()))


def contains_street(line: str) -> bool:
    return bool(STREET_START_PATTERN.search(line.strip()))


def is_ui_noise(line: str) -> bool:
    """True for app chrome (tabs, filters, buttons).

    A line holding an address is never discarded, even when it contains one of
    the fragments above.
    """
    stripped = line.strip()
    if not stripped:
        return False
    if contains_street(stripped) or is_order_id(stripped):
        return False
    return any(pattern.search(stripped) for pattern in UI_NOISE_PATTERNS)


def filter_watermark(text: str) -> str:
    """Drop the lines the watermark contributed.

    Only removes watermark the OCR read as *separate* text. Where it crossed a
    letter and smudged it, the damage is already in the pixels — that is what
    the human review screen is for.
    """
    kept = [line for line in text.splitlines() if not is_watermark(line)]
    return "\n".join(kept)


# ------------------------------------------------------------ normalização


def _normalize_text(text: str) -> str:
    """Unify dashes and collapse spacing, keeping line ends as a soft marker."""
    text = text.replace("–", "-").replace("—", "-").replace("−", "-")
    lines = [re.sub(r"[^\S\n]+", " ", line).strip() for line in text.splitlines()]
    return f" {LINE_BREAK} ".join(line for line in lines if line)


def _flatten(text: str) -> str:
    """Drop the line markers, for the regexes that must span a broken line."""
    return re.sub(r"\s+", " ", text.replace(LINE_BREAK, " ")).strip()


def _mask_timestamps(text: str) -> str:
    """Replace timestamps with a sentinel.

    Two jobs: mark where an address ends, and stop a CEP from fusing with the
    following year into a fake order id ("76985662" + "2026-..." = 12 digits).
    """
    return TIMESTAMP_PATTERN.sub(DATE_SENTINEL, text)


def _strip_ui_noise(text: str) -> str:
    for pattern in UI_NOISE_PATTERNS:
        text = pattern.sub(" ", text)
    return re.sub(r"\s+", " ", text)


# ------------------------------------------------------------- tokenização


def _core(token: str) -> str:
    return token.strip(JUNK_EDGE)


def _is_word_token(token: str) -> bool:
    """A token that can plausibly belong to a street name."""
    if token[:1] in SEAM_PREFIX:
        return False
    core = _core(token)
    if not core:
        return False
    if not re.fullmatch(r"[A-Za-zÀ-ÿ0-9º°ª'.\-]+", core):
        return False
    return len(core) > 2 or core.upper() in CONNECTORS


def _clean_run(text: str, limit: int = 8) -> str:
    """Longest prefix of ``text`` made of plausible words.

    Three things end the run:

    * a token that is not a plausible word — this is what separates
      "RUA RESIDENCIAL FLORENÇA-UM ..." from "RUA RESIDENCIAL ori o eo) UM",
      which dies at "o";
    * the city name, which never belongs to the street;
    * a word already used in the run. The screen prints the address twice, so
      a repeat means the second copy started
      ("RUA RESIDENCIAL FLORENÇA-UM RESIDENCIAL FLORENCA Vilhena").
    """
    words: list[str] = []
    seen: set[str] = set()

    for token in text.split():
        if token == LINE_BREAK or not _is_word_token(token) or len(words) >= limit:
            break
        core = _core(token)
        key = core.upper()
        if key == CITY.upper() or key in seen:
            break
        seen.add(key)
        words.append(core)

    return " ".join(words)


# ------------------------------------------------------------------ campos


def _extract_cep(segment: str) -> tuple[Optional[str], str]:
    match = CEP_PATTERN.search(segment)
    if not match:
        return None, segment
    cep = f"{match.group(1)}-{match.group(2)}"
    return cep, (segment[: match.start()] + " " + segment[match.end() :])


def _extract_complement(segment: str) -> Optional[str]:
    match = COMPLEMENT_PATTERN.search(segment)
    if not match:
        return None
    return re.sub(r"\s+", " ", match.group(0)).strip(JUNK_EDGE) or None


def _fix_ocr_digits(token: str) -> Optional[str]:
    """Repair O/I read inside a number ("8O46" -> "8046").

    Anything still ambiguous returns ``None``: better an empty field she fills
    than a wrong house number she does not notice.
    """
    if not re.fullmatch(r"[0-9OoIl]{1,6}", token):
        return None
    fixed = token.translate(str.maketrans({"O": "0", "o": "0", "I": "1", "l": "1"}))
    return fixed if fixed.isdigit() else None


def _extract_number(segment: str) -> Optional[str]:
    """House number: between commas, or right before CASA/APTO/...

    Only digits count. The street "FLORENÇA-UM" ends in the *word* "um", which
    is part of the name, not a number.
    """
    between_commas = re.search(r",\s*([0-9OoIl]{1,6})\s*,", segment)
    if between_commas:
        fixed = _fix_ocr_digits(between_commas.group(1))
        if fixed:
            return fixed

    before_complement = re.search(
        r"\b([0-9OoIl]{1,6})\s*,?\s*(?:" + "|".join(COMPLEMENT_KEYWORDS) + r")\b",
        segment,
        re.IGNORECASE,
    )
    if before_complement:
        return _fix_ocr_digits(before_complement.group(1))

    return None


def _extract_street(segment: str) -> Optional[str]:
    """Best street candidate in the card.

    Every occurrence of a street prefix is a candidate; the winner is the one
    whose run of plausible words is longest. Repetition 1 is usually cleaner
    than repetition 2, but not always — scoring picks whichever survived the
    watermark better, instead of trusting a fixed position.
    """
    best: Optional[str] = None
    for match in STREET_START_PATTERN.finditer(segment):
        candidate = segment[match.start() :].split(",")[0]
        run = _clean_run(candidate)
        if run and (best is None or len(run) > len(best)):
            best = run
    return best


def _extract_neighborhood(segment: str) -> Optional[str]:
    """Read the neighborhood off repetition 1, which carries "<bairro> Vilhena"."""
    match = re.search(CITY, segment, re.IGNORECASE)
    if not match:
        return None

    words: list[str] = []
    for token in reversed(segment[: match.start()].split()):
        if token == LINE_BREAK or not _is_word_token(token) or len(words) >= 4:
            break
        core = _core(token)
        if core.upper() in STREET_PREFIXES:
            break
        words.append(core)

    return " ".join(reversed(words)) or None


def parse_address_fields(segment: str) -> dict[str, Optional[str]]:
    """Break a card's text into address fields, in whatever order they appear.

    Number, complement and CEP are read from a flattened copy, because the
    screen breaks "RO RUA RESIDENCIAL" / "UM, 8046, CASA 76985662" across two
    lines. Street and neighborhood are read with the line markers in place,
    which is what keeps the street from swallowing the neighborhood.
    """
    cep, without_cep = _extract_cep(segment)
    flat = _flatten(without_cep)

    return {
        "street": _extract_street(without_cep),
        "number": _extract_number(flat),
        "complement": _extract_complement(flat),
        "cep": cep,
        "neighborhood": _extract_neighborhood(without_cep),
    }


# ----------------------------------------------------------- segmentação


def _split_cards(text: str) -> list[tuple[Optional[str], str]]:
    """Cut the screen into (order_id, text) cards at every long digit run.

    Text before the first order id is the app header and is dropped. A card
    with no readable id can still be recovered later, from the tail.
    """
    matches = list(ORDER_ID_DIGITS.finditer(text))
    if not matches:
        return []

    cards: list[tuple[Optional[str], str]] = []
    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        cards.append((re.sub(r"\D", "", match.group(0)), text[match.end() : end]))
    return cards


def _card_and_tail(body: str) -> tuple[str, str]:
    """Split a card at its timestamp: (address side, everything after)."""
    head, _, tail = body.partition(DATE_SENTINEL)
    return head, tail


def _build_block(order_id: Optional[str], body: str) -> Optional[dict[str, Any]]:
    fields = parse_address_fields(body)
    if not fields["street"]:
        return None

    raw_text = _flatten(body.replace(DATE_SENTINEL, " "))
    return {"order_id": order_id, "raw_text": raw_text, **fields}


def parse_addresses(ocr_text: str) -> list[dict[str, Any]]:
    """Split dirty OCR text into deliveries with their address fields.

    Cards without any street are dropped instead of becoming empty entries for
    her to delete by hand. A delivery whose order id did not survive the OCR is
    still returned when it carries an address — the street anchors it, and the
    id simply comes back empty.

    Two orders to the same house stay as two deliveries: no deduplication.
    """
    text = _strip_ui_noise(_mask_timestamps(_normalize_text(ocr_text)))

    blocks: list[dict[str, Any]] = []
    for order_id, body in _split_cards(text):
        card, tail = _card_and_tail(body)

        block = _build_block(order_id, card)
        if block:
            blocks.append(block)
        else:
            logger.info("Card %s dropped: no street found", order_id)

        # What follows the timestamp is usually buttons — but a card whose own
        # order id was destroyed by the watermark also lands here.
        if tail.strip():
            orphan = _build_block(None, tail)
            if orphan:
                blocks.append(orphan)

    return blocks
