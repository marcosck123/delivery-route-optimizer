"""Preprocessing, watermark sieve and the OCR entry point.

Tesseract itself is mocked: the binary is not installed in every environment,
and what we need to prove is the sieve/parser logic over strings. The OpenCV
preprocessing runs for real over a generated image.

The parser tailored to the J&T screen lives in ``test_ocr_parser.py``.
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
from app.utils.ocr import extract_text, filter_watermark, is_watermark

# Trecho realista da tela da J&T, com a marca d'água lida como texto solto.
SAMPLE_OCR_TEXT = """\
Recibo de Transferência
Entrega pendente   Assinado   Pacote problemático
2026-08-02
888030841672038
MARCELA FLORINDA FUR...
RUA RESIDENCIAL FLORENÇA–UM
RESIDENCIAL FLORENCA Vilhena
RO RUA RESIDENCIAL FLORENÇA–
UM, 8046, CASA 76985662
2026-08-01 18:24:00
82736451928374651928
[navegação]  Telefone  Registro de anomalia  Assinar
888030841672039
VANDERLEI VIERA ROCHA
RUA RESIDENCIAL FLORENÇA–TRÊS
RESIDENCIAL FLORENCA Vilhena
RO RUA RESIDENCIAL FLORENÇA–
TRÊS, 1290, FUNDOS 76985663
2026-08-01 18:25:00
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
    assert (cleaned == 0).sum() > 0


def test_preprocess_pipeline_is_binary_and_2d():
    processed = preprocess_for_ocr(make_screenshot())
    assert processed.ndim == 2
    assert set(np.unique(processed)).issubset({0, 255})


def test_preprocess_removes_most_of_the_watermark():
    """A marca d'água clara sobre fundo branco some no threshold adaptativo."""
    processed = preprocess_for_ocr(make_screenshot())
    dark_ratio = (processed == 0).mean()
    assert 0 < dark_ratio < 0.15


# --------------------------------------------------------------- peneira


@pytest.mark.parametrize(
    "line",
    ["2026-08-02", "82736451928374651928", "||||", "—————"],
)
def test_is_watermark_catches_noise(line):
    assert is_watermark(line)


@pytest.mark.parametrize(
    "line",
    [
        "888030841672038",  # número do pedido: marcador de bloco
        "RUA RESIDENCIAL FLORENÇA-UM, 8046, CASA",
        "MARCELA FLORINDA FUR...",
        "8046",
        "76985662",
        "2026-08-01 18:24:00",  # data COM hora é do card, não da marca d'água
        "",
    ],
)
def test_is_watermark_keeps_real_data(line):
    assert not is_watermark(line)


def test_filter_watermark_removes_only_the_noise_lines():
    filtered = filter_watermark(SAMPLE_OCR_TEXT)

    assert "\n2026-08-02\n" not in f"\n{filtered}\n"
    assert "82736451928374651928" not in filtered
    assert "888030841672038" in filtered  # o marcador de bloco sobrevive
    assert "UM, 8046, CASA 76985662" in filtered


# --------------------------------------------------------- extract_text


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
    assert "82736451928374651928" not in text  # peneira aplicada
    assert "UM, 8046, CASA 76985662" in text
