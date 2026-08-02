"""Image preprocessing that makes a watermarked screenshot readable by OCR.

The input is a digital screenshot of the carrier app: black text on white
cards, covered by a light grey diagonal watermark repeated in a grid.

The pipeline below attacks exactly that. Each step is a separate function so
it can be inspected and tested on its own — and so the reasoning survives:

1. ``to_grayscale``      color carries no information here; one channel is
                         faster and every later step expects 2D data.
2. ``boost_contrast``    CLAHE stretches contrast in small tiles, which pushes
                         the light grey watermark towards white and the black
                         text towards black. Global equalization would drag
                         the whole image, including the text, in one direction.
3. ``binarize``          adaptive Gaussian threshold: the cutoff is computed
                         per neighbourhood, so a light watermark over white
                         background falls out completely. A single global
                         cutoff cannot do this without eating thin glyphs.
4. ``remove_speckles``   morphological opening deletes leftover dots from the
                         watermark that survived as isolated pixels.

Honest limit: where the watermark crosses the text, the damage is in the
pixels themselves. No threshold recovers those glyphs — that is what the
human review screen is for.
"""

import cv2
import numpy as np

# Larger tiles wash out local contrast; smaller ones amplify noise.
CLAHE_CLIP_LIMIT = 2.0
CLAHE_TILE_GRID = (8, 8)

# Odd window used by the adaptive threshold. Must be bigger than a glyph so
# the local mean describes the background, not the letter itself.
ADAPTIVE_BLOCK_SIZE = 31
# Subtracted from the local mean: higher values keep only the darkest pixels,
# which is what removes the grey watermark.
ADAPTIVE_C = 15

SPECKLE_KERNEL = np.ones((2, 2), np.uint8)


class ImageDecodeError(ValueError):
    """Raised when the uploaded bytes are not a readable image."""


def decode_image(image_bytes: bytes) -> np.ndarray:
    """Bytes -> BGR array. Raises ``ImageDecodeError`` for anything unreadable."""
    if not image_bytes:
        raise ImageDecodeError("empty image")

    buffer = np.frombuffer(image_bytes, dtype=np.uint8)
    image = cv2.imdecode(buffer, cv2.IMREAD_COLOR)
    if image is None:
        raise ImageDecodeError("could not decode image")
    return image


def to_grayscale(image: np.ndarray) -> np.ndarray:
    if image.ndim == 2:
        return image
    return cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)


def boost_contrast(gray: np.ndarray) -> np.ndarray:
    clahe = cv2.createCLAHE(clipLimit=CLAHE_CLIP_LIMIT, tileGridSize=CLAHE_TILE_GRID)
    return clahe.apply(gray)


def binarize(gray: np.ndarray) -> np.ndarray:
    return cv2.adaptiveThreshold(
        gray,
        maxValue=255,
        adaptiveMethod=cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
        thresholdType=cv2.THRESH_BINARY,
        blockSize=ADAPTIVE_BLOCK_SIZE,
        C=ADAPTIVE_C,
    )


def remove_speckles(binary: np.ndarray) -> np.ndarray:
    return cv2.morphologyEx(binary, cv2.MORPH_OPEN, SPECKLE_KERNEL)


def preprocess_for_ocr(image_bytes: bytes) -> np.ndarray:
    """Full pipeline: raw upload -> binary image ready for Tesseract."""
    image = decode_image(image_bytes)
    gray = to_grayscale(image)
    contrasted = boost_contrast(gray)
    binary = binarize(contrasted)
    return remove_speckles(binary)
