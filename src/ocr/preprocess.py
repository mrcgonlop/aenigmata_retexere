"""Image preprocessing for manuscript folio scans.

Converts raw high-resolution folio images into forms suitable for OCR engines.
All functions accept and return numpy arrays (grayscale or binary, uint8).
"""

from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np


# ---------------------------------------------------------------------------
# Loading
# ---------------------------------------------------------------------------

def load_image(path: Path) -> np.ndarray:
    """Load a folio image as a BGR numpy array."""
    img = cv2.imread(str(path))
    if img is None:
        raise FileNotFoundError(f"Could not load image: {path}")
    return img


def resize_to_width(img: np.ndarray, max_width: int) -> np.ndarray:
    """Downscale image if wider than max_width, preserving aspect ratio."""
    h, w = img.shape[:2]
    if w <= max_width:
        return img
    scale = max_width / w
    return cv2.resize(img, (max_width, int(h * scale)), interpolation=cv2.INTER_AREA)


# ---------------------------------------------------------------------------
# Colour conversion
# ---------------------------------------------------------------------------

def to_grayscale(img: np.ndarray) -> np.ndarray:
    """Convert BGR image to grayscale. No-op if already grayscale."""
    if len(img.shape) == 2:
        return img
    return cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)


# ---------------------------------------------------------------------------
# Binarization
# ---------------------------------------------------------------------------

def binarize_adaptive(
    gray: np.ndarray,
    block_size: int = 51,
    C: int = 10,
) -> np.ndarray:
    """Adaptive Gaussian thresholding.

    Better than Otsu for parchment manuscripts with uneven illumination,
    staining, or vellum transparency. block_size must be odd.
    """
    return cv2.adaptiveThreshold(
        gray, 255,
        cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
        cv2.THRESH_BINARY,
        block_size, C,
    )


def binarize_otsu(gray: np.ndarray) -> np.ndarray:
    """Otsu global thresholding.

    Fast; works when illumination is reasonably uniform.
    """
    _, binary = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    return binary


def denoise(gray: np.ndarray, h: int = 10) -> np.ndarray:
    """Non-local means denoising — useful for heavy parchment grain."""
    return cv2.fastNlMeansDenoising(gray, h=h)


# ---------------------------------------------------------------------------
# Geometry correction
# ---------------------------------------------------------------------------

def deskew(gray: np.ndarray) -> tuple[np.ndarray, float]:
    """Estimate and correct skew angle.

    Returns the corrected image and the detected angle in degrees.
    Very small angles (< 0.1°) are left untouched.
    """
    inverted = cv2.bitwise_not(gray)
    coords = np.column_stack(np.where(inverted > 0))
    if len(coords) < 100:
        return gray, 0.0

    angle = cv2.minAreaRect(coords)[-1]
    if angle < -45:
        angle = -(90 + angle)
    else:
        angle = -angle

    if abs(angle) < 0.1:
        return gray, angle

    h, w = gray.shape
    M = cv2.getRotationMatrix2D((w // 2, h // 2), angle, 1.0)
    corrected = cv2.warpAffine(
        gray, M, (w, h),
        flags=cv2.INTER_CUBIC,
        borderMode=cv2.BORDER_REPLICATE,
    )
    return corrected, angle


# ---------------------------------------------------------------------------
# Column detection
# ---------------------------------------------------------------------------

def detect_columns(binary: np.ndarray, num_cols: int = 3) -> list[int]:
    """Find vertical column-separator x-coordinates using ink projection.

    Scans the vertical ink-density profile (pixels per column) and finds the
    lowest-density x position within each expected inter-column gap.

    Args:
        binary: Binarized grayscale image (uint8, 0=ink / 255=background OR
                standard CV convention — both work because we threshold at 128).
        num_cols: Number of text columns on the page.

    Returns:
        List of (num_cols - 1) x-coordinates that split the image into columns.
        Can be passed directly to :func:`split_columns`.
    """
    ink = (binary < 128).astype(np.float32)
    vproj = ink.sum(axis=0)

    # Light smoothing to suppress local noise
    kernel = np.ones(40, dtype=np.float32) / 40
    smooth = np.convolve(vproj, kernel, mode="same")

    w = binary.shape[1]
    separators: list[int] = []
    num_seps = num_cols - 1

    for i in range(num_seps):
        # Search window centred on the expected separator position.
        # Separators are evenly spaced in [25%, 75%] of the width.
        frac = (i + 1) / num_cols
        center = int(w * frac)
        half_width = int(w * 0.12)
        lo = max(0, center - half_width)
        hi = min(w, center + half_width)
        local_min = lo + int(smooth[lo:hi].argmin())
        separators.append(local_min)

    return separators


def split_columns(img_pil: "PILImage", separators: list[int]) -> list["PILImage"]:
    """Crop a PIL image into column sub-images at the given x-separator positions.

    Args:
        img_pil: Full-page PIL image (any mode).
        separators: x-coordinates where the image should be split.

    Returns:
        List of cropped PIL images, one per column, in left-to-right order.
    """
    from PIL import Image as _PILImage
    w, h = img_pil.size
    xs = [0] + separators + [w]
    cols = []
    for x0, x1 in zip(xs, xs[1:]):
        cols.append(img_pil.crop((x0, 0, x1, h)))
    return cols


# ---------------------------------------------------------------------------
# Composite pipeline
# ---------------------------------------------------------------------------

def preprocess(
    path: Path,
    max_width: int = 3000,
    binarize_method: str = "adaptive",
    do_deskew: bool = True,
    do_denoise: bool = False,
) -> tuple[np.ndarray, dict]:
    """Full preprocessing pipeline for a manuscript folio.

    Args:
        path: Path to the folio image.
        max_width: Downscale if wider than this (Tesseract is happiest ~300 DPI,
                   roughly 2000–3000px for a manuscript page).
        binarize_method: "adaptive" | "otsu" | "none".
        do_deskew: Whether to correct rotation.
        do_denoise: Whether to apply NLM denoising before binarization.

    Returns:
        (processed_image, info_dict) where info_dict contains diagnostics
        (original size, deskew angle, etc.).
    """
    img = load_image(path)
    original_h, original_w = img.shape[:2]

    img = resize_to_width(img, max_width)
    gray = to_grayscale(img)

    angle = 0.0
    if do_deskew:
        gray, angle = deskew(gray)

    if do_denoise:
        gray = denoise(gray)

    if binarize_method == "adaptive":
        result = binarize_adaptive(gray)
    elif binarize_method == "otsu":
        result = binarize_otsu(gray)
    else:
        result = gray

    info = {
        "original_size": (original_w, original_h),
        "processed_size": (result.shape[1], result.shape[0]),
        "deskew_angle_deg": angle,
        "binarize_method": binarize_method,
    }
    return result, info
