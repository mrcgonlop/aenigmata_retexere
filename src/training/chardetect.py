"""Connected-component character detection for manuscript line images.

Given a greyscale or colour PNG of a single text line (as saved by the extractor),
this module detects per-character bounding boxes by:

  1. Binarising with Otsu's method (numpy-only, no OpenCV required).
  2. Labelling connected ink components (scipy.ndimage.label).
  3. Filtering noise by area relative to total ink area.
  4. Merging split glyphs that are likely parts of the same character:
       - Xi (Ξ): three separate horizontal bars → one bbox
       - Corrector marks sitting directly above a letter → merged with letter
       - Any ink fragment with a tiny gap to a larger neighbour

Requirements: scipy (installed as a transitive dependency of kraken / scikit-learn)
"""

from __future__ import annotations

import numpy as np
from pathlib import Path


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def detect_chars(
    line_image: "np.ndarray | Path",
    *,
    min_ink_frac: float = 0.003,
    max_ink_frac: float = 0.70,
    merge_gap_px: int = 4,
    merge_v_frac: float = 0.45,
) -> list[dict]:
    """Detect character bounding boxes in a line image.

    Args:
        line_image: Greyscale numpy array (uint8) or Path to a PNG file.
        min_ink_frac: Minimum component area as a fraction of total ink pixels.
                      Filters dust/speckle noise.
        max_ink_frac: Maximum component area as a fraction of total ink pixels.
                      Filters huge connected blobs (touching multi-char runs).
        merge_gap_px: Maximum horizontal gap (pixels) between two components for
                      them to be considered the same character.
        merge_v_frac: Maximum vertical gap as a fraction of the line image height
                      allowed when merging (prevents merging characters in adjacent lines
                      if two lines were accidentally bundled into one crop).

    Returns:
        List of ``{'bbox': [x1, y1, x2, y2]}`` dicts, sorted left-to-right by x1.
        Returns an empty list if scipy is not available or no ink is found.
    """
    try:
        from scipy.ndimage import label as _nd_label
    except ImportError:
        return []

    img = _load_grey(line_image)
    h, w = img.shape

    binary = _otsu_binarize(img)          # True = ink (dark pixel)
    total_ink = int(binary.sum())
    if total_ink == 0:
        return []

    labeled, n_components = _nd_label(binary)
    if n_components == 0:
        return []

    components: list[dict] = []
    for idx in range(1, n_components + 1):
        rows, cols = np.where(labeled == idx)
        area = int(len(rows))
        if area < min_ink_frac * total_ink:
            continue                          # noise / speckle
        if area > max_ink_frac * total_ink:
            continue                          # massive connected run
        components.append({
            "bbox": [int(cols.min()), int(rows.min()),
                     int(cols.max()) + 1, int(rows.max()) + 1],
            "area": area,
        })

    if not components:
        return []

    # Sort left-to-right
    components.sort(key=lambda c: c["bbox"][0])

    # Pass 1: merge horizontally-split glyphs (Ξ bars, binarisation gaps)
    merged = _merge_split_glyphs(components, img_height=h,
                                  merge_gap_px=merge_gap_px,
                                  merge_v_frac=merge_v_frac)

    # Pass 2: assign diacritic marks to their host letter by horizontal overlap
    return _merge_diacritics(merged)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _load_grey(src: "np.ndarray | Path") -> np.ndarray:
    from PIL import Image
    if isinstance(src, Path):
        img = Image.open(src).convert("L")
        return np.asarray(img, dtype=np.uint8)
    arr = np.asarray(src)
    if arr.ndim == 3:
        # weighted luminance conversion
        return (0.299 * arr[:, :, 0]
                + 0.587 * arr[:, :, 1]
                + 0.114 * arr[:, :, 2]).astype(np.uint8)
    return arr.astype(np.uint8)


def _otsu_binarize(img: np.ndarray) -> np.ndarray:
    """Return boolean array (True = ink) using Otsu's threshold."""
    hist, _ = np.histogram(img.ravel(), bins=256, range=(0, 256))
    total = int(img.size)
    sum_total = int(np.dot(np.arange(256, dtype=np.int64), hist))

    sum_bg = 0
    count_bg = 0
    best_thresh = 128
    best_var: float = 0.0

    for t in range(256):
        count_bg += int(hist[t])
        if count_bg == 0:
            continue
        count_fg = total - count_bg
        if count_fg == 0:
            break
        sum_bg += t * int(hist[t])
        mean_bg = sum_bg / count_bg
        mean_fg = (sum_total - sum_bg) / count_fg
        var = count_bg * count_fg * (mean_bg - mean_fg) ** 2
        if var > best_var:
            best_var = var
            best_thresh = t

    return img < best_thresh


def _merge_diacritics(components: list[dict]) -> list[dict]:
    """Merge small diacritic/superscript components with their host letter.

    Identifies components whose height is less than half the median component
    height — breathing marks, accents, iota subscripts, and corrector marks
    all fall into this category.  Each such component is merged with the base
    component (larger-height component) that has the greatest horizontal overlap.

    Components with no horizontal overlap with any base component are kept as
    standalone entries (e.g. punctuation that sits far from any letter).
    """
    if len(components) < 2:
        return components

    heights = sorted(c["bbox"][3] - c["bbox"][1] for c in components)
    median_h = heights[len(heights) // 2]

    base: list[dict] = []
    small: list[dict] = []
    for c in components:
        h = c["bbox"][3] - c["bbox"][1]
        if h < 0.5 * median_h:
            small.append(c)
        else:
            base.append(c)

    if not small:
        return components

    result = [c.copy() for c in base]

    for d in small:
        dx1, dy1, dx2, dy2 = d["bbox"]
        best_idx = -1
        best_overlap = 0

        for i, b in enumerate(result):
            bx1, _, bx2, _ = b["bbox"]
            overlap = max(0, min(dx2, bx2) - max(dx1, bx1))
            if overlap > best_overlap:
                best_overlap = overlap
                best_idx = i

        if best_idx >= 0 and best_overlap > 0:
            b = result[best_idx]
            bx1, by1, bx2, by2 = b["bbox"]
            result[best_idx] = {
                "bbox": [min(bx1, dx1), min(by1, dy1),
                         max(bx2, dx2), max(by2, dy2)],
                "area": b["area"] + d["area"],
            }
        else:
            # No overlapping base — keep as standalone (punctuation etc.)
            result.append(d.copy())

    result.sort(key=lambda c: c["bbox"][0])
    return result


def _merge_split_glyphs(
    components: list[dict],
    *,
    img_height: int,
    merge_gap_px: int,
    merge_v_frac: float,
) -> list[dict]:
    """Single left-to-right pass: merge neighbouring components that are parts
    of the same glyph.

    Merge condition (both must hold):
      • Horizontal gap between the two components ≤ merge_gap_px  (they nearly
        touch — e.g. the three bars of Ξ, or a hair-line gap from binarisation)
      • Vertical gap between the two components < img_height * merge_v_frac
        (they live on the same text baseline)

    A second pass is run until convergence so multi-part characters (like Ξ
    with three bars) get fully merged even if the first pass only joins two bars.
    """
    max_v_gap = img_height * merge_v_frac

    changed = True
    result = [c.copy() for c in components]

    while changed:
        changed = False
        merged: list[dict] = [result[0]]

        for curr in result[1:]:
            prev = merged[-1]
            px1, py1, px2, py2 = prev["bbox"]
            cx1, cy1, cx2, cy2 = curr["bbox"]

            h_gap = cx1 - px2                         # positive = gap, negative = overlap
            v_gap = max(0, max(cy1, py1) - min(cy2, py2))  # 0 if they overlap vertically

            if h_gap <= merge_gap_px and v_gap <= max_v_gap:
                merged[-1] = {
                    "bbox": [min(px1, cx1), min(py1, cy1),
                             max(px2, cx2), max(py2, cy2)],
                    "area": prev["area"] + curr["area"],
                }
                changed = True
            else:
                merged.append(curr)

        result = merged

    return result
