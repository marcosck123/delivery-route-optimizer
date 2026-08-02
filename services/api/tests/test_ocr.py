"""OCR tests.

Tesseract itself is mocked: the binary is not installed in every environment,
and what we need to prove is the sieve + parser logic over strings. The
OpenCV preprocessing runs for real over a generated image.
"""

import cv2
import numpy as np
import pytest

from app.utils.image_preprocessing import (
    ImageDecodeError,
    binarize,
    boost_contrast,
    decode_image,
    preprocess_for_ocr,
    remove_speckles,
    to_grayscale,
)
from app.utils.ocr import (
    extract_text,
    filter_watermark,
    is_watermark,
    parse_addresses,
)

# Texto realista, como sai do Tesseract sobre um print da transportadora.
SAMPLE_OCR_TEXT = """\
2026-08-02
BR2508140021
MARCELA SOUZA
RUA RESIDENCIAL FLORENÇA UM, 8046, CASA
Residencial Florença
Vilhena RO
82736451928374651928
BR2508140022
JOAO PEREIRA
AV MAJOR AMARANTE, 1000
Centro
Vilhena RO
2026-08-02
BR2508140023
ANA LIMA
TRAVESSA DOS IPES 45
Jardim Eldorado
"""


def make_screenshot(width=600, height=400) -> bytes:
    """White card with black text and a light grey diagonal watermark."""
    image = np.full((height, width, 3), 255, dtype=np.uint8)

    cv2.putText(
        image, "RUA A, 123", (20, 80), cv2.FONT_HERSHEY_SIMPLEX, 1.0, (0, 0, 0), 2
    )
    cv2.putText(
        image, "Centro", (20, 140), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 0, 0), 2
    )

    # marca d'água clara, repetida na diagonal
    for offset in range(-height, width, 120):
        cv2.line(
            image, (offset, 0), (offset + height, height), (215, 215, 215), 6
        )

    return cv2.imencode(".png", image)[1].tobytes()


# ------------------------------------------------------ pré-processamento


def test_decode_image_reads_png():
    image = decode_image(make_screenshot())
    assert image.shape[2] == 3


@pytest.mark.parametrize("payload", [b"", b"isso nao e uma imagem"])
def test_decode_image_rejects_garbage(payload):
    with pytest.raises(ImageDecodeError):
        decode_image(payload)


def test_grayscale_drops_the_color_channel():
    gray = to_grayscale(decode_image(make_screenshot()))
    assert gray.ndim == 2


def test_boost_contrast_keeps_shape_and_dtype():
    gray = to_grayscale(decode_image(make_screenshot()))
    contrasted = boost_contrast(gray)
    assert contrasted.shape == gray.shape
    assert contrasted.dtype == np.uint8


def test_binarize_returns_only_two_levels():
    gray = to_grayscale(decode_image(make_screenshot()))
    binary = binarize(boost_contrast(gray))
    assert set(np.unique(binary)).issubset({0, 255})


def test_remove_speckles_does_not_erase_the_text():
    gray = to_grayscale(decode_image(make_screenshot()))
    binary = binarize(boost_contrast(gray))
    cleaned = remove_speckles(binary)
    # ainda há pixels escuros (o texto) depois da limpeza
    assert (cleaned == 0).sum() > 0


def test_preprocess_pipeline_is_binary_and_2d():
    processed = preprocess_for_ocr(make_screenshot())
    assert processed.ndim == 2
    assert set(np.unique(processed)).issubset({0, 255})


def test_preprocess_removes_most_of_the_watermark():
    """A marca d'água clara sobre fundo branco some no threshold adaptativo."""
    processed = preprocess_for_ocr(make_screenshot())
    dark_ratio = (processed == 0).mean()
    # sobra o texto (pouca área escura); se a marca d'água tivesse ficado,
    # a proporção seria muito maior
    assert 0 < dark_ratio < 0.15


# --------------------------------------------------------------- peneira


@pytest.mark.parametrize(
    "line",
    ["2026-08-02", "82736451928374651928", "1234567890", "||||", "—————"],
)
def test_is_watermark_catches_noise(line):
    assert is_watermark(line)


@pytest.mark.parametrize(
    "line",
    [
        "BR2508140021",  # número do pedido
        "RUA RESIDENCIAL FLORENÇA UM, 8046, CASA",
        "Centro",
        "8046",
        "MARCELA SOUZA",
        "",
    ],
)
def test_is_watermark_keeps_real_data(line):
    assert not is_watermark(line)


def test_filter_watermark_removes_only_the_noise_lines():
    filtered = filter_watermark(SAMPLE_OCR_TEXT)

    assert "2026-08-02" not in filtered
    assert "82736451928374651928" not in filtered
    assert "BR2508140021" in filtered
    assert "RUA RESIDENCIAL FLORENÇA UM, 8046, CASA" in filtered


# ---------------------------------------------------------------- parser


def test_parse_addresses_splits_into_blocks():
    blocks = parse_addresses(filter_watermark(SAMPLE_OCR_TEXT))
    assert len(blocks) == 3


def test_parse_addresses_guesses_street_and_number():
    blocks = parse_addresses(filter_watermark(SAMPLE_OCR_TEXT))

    first = blocks[0]
    assert first["street"] == "RUA RESIDENCIAL FLORENÇA UM"
    assert first["number"] == "8046"
    assert first["neighborhood"] == "Residencial Florença"

    second = blocks[1]
    assert second["street"] == "AV MAJOR AMARANTE"
    assert second["number"] == "1000"


def test_parse_addresses_handles_number_glued_to_the_street():
    blocks = parse_addresses(filter_watermark(SAMPLE_OCR_TEXT))
    third = blocks[2]
    assert third["street"] == "TRAVESSA DOS IPES"
    assert third["number"] == "45"


def test_parse_addresses_always_keeps_raw_text():
    blocks = parse_addresses(filter_watermark(SAMPLE_OCR_TEXT))
    assert all(block["raw_text"] for block in blocks)
    assert "MARCELA SOUZA" in blocks[0]["raw_text"]


def test_parse_addresses_without_a_recognizable_street():
    """Bloco sem rua não quebra: volta só o texto para ela preencher à mão."""
    blocks = parse_addresses("BR2508140099\nFULANO DE TAL\nsem endereço aqui")

    assert len(blocks) == 1
    assert blocks[0]["street"] is None
    assert blocks[0]["number"] is None
    assert "FULANO DE TAL" in blocks[0]["raw_text"]


def test_parse_addresses_on_empty_text():
    assert parse_addresses("") == []
    assert parse_addresses("\n\n   \n") == []


def test_extract_text_pipeline(monkeypatch):
    """extract_text = pré-processamento + Tesseract + peneira."""
    seen = {}

    def fake_image_to_string(image, lang=None):
        seen["ndim"] = image.ndim
        seen["lang"] = lang
        return SAMPLE_OCR_TEXT

    monkeypatch.setattr("app.utils.ocr.pytesseract.image_to_string", fake_image_to_string)

    text = extract_text(make_screenshot())

    assert seen["lang"] == "por"
    assert seen["ndim"] == 2  # recebeu a imagem já binarizada
    assert "2026-08-02" not in text  # peneira aplicada
    assert "RUA RESIDENCIAL FLORENÇA UM, 8046, CASA" in text
