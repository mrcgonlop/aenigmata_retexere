"""Export confirmed training samples to Kraken ground-truth format.

Kraken's ketos train expects pairs of files with matching stems:
    images/line_0001.png
    images/line_0001.gt.txt   (UTF-8 plain text transcription)

Output layout (one directory per scribal hand):
    data/training/export/
    ├── hand_a/
    │   ├── train/
    │   │   ├── <filename>.png
    │   │   └── <filename>.gt.txt
    │   └── eval/
    │       └── ...
    └── hand_b/
        ├── train/
        └── eval/

Usage:
    python -m src.training.export --hand b
    python -m src.training.export --hand all --eval-split 0.1
"""

from __future__ import annotations

import random
import shutil
from pathlib import Path

from src.training.db import get_training_connection, list_samples

_DATA_DIR = Path("data")
_IMAGES_DIR = _DATA_DIR / "training" / "images"
_EXPORT_DIR = _DATA_DIR / "training" / "export"


def export_hand(
    hand_id: str,
    eval_split: float = 0.10,
    seed: int = 42,
    export_dir: Path = _EXPORT_DIR,
) -> dict[str, int]:
    """Export confirmed samples for one scribal hand to Kraken training format.

    Args:
        hand_id: 'a', 'b', or 'unknown'.
        eval_split: Fraction of samples to place in the eval set (default 0.10).
        seed: Random seed for reproducible train/eval split.
        export_dir: Root output directory.

    Returns:
        Dict with keys 'train' and 'eval' showing how many pairs were written.
    """
    conn = get_training_connection()
    samples = list_samples(conn, hand_id=hand_id, status="confirmed", limit=100_000)
    conn.close()

    if not samples:
        return {"train": 0, "eval": 0}

    random.seed(seed)
    random.shuffle(samples)

    n_eval = max(1, int(len(samples) * eval_split))
    eval_set = samples[:n_eval]
    train_set = samples[n_eval:]

    hand_dir = export_dir / f"hand_{hand_id}"
    counts: dict[str, int] = {}
    for split_name, split_samples in [("train", train_set), ("eval", eval_set)]:
        split_dir = hand_dir / split_name
        split_dir.mkdir(parents=True, exist_ok=True)
        written = 0
        for s in split_samples:
            src_img = _IMAGES_DIR / s["line_image_path"]
            if not src_img.exists():
                continue
            stem = src_img.stem
            shutil.copy2(src_img, split_dir / src_img.name)
            gt_path = split_dir / f"{stem}.gt.txt"
            gt_path.write_text(s["ground_truth"] or "", encoding="utf-8")
            written += 1
        counts[split_name] = written

    return counts


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="Export confirmed labels to Kraken training format.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
After export, train with:
  ketos train --load data/models/model_grc_catlips.mlmodel \\
              --ground-truth "data/training/export/hand_b/train/*.gt.txt" \\
              --evaluation-files "data/training/export/hand_b/eval/*.gt.txt" \\
              --output data/models/model_vat_hand_b
        """,
    )
    parser.add_argument(
        "--hand",
        required=True,
        choices=["a", "b", "unknown", "all"],
        help="Which scribal hand to export.",
    )
    parser.add_argument(
        "--eval-split",
        type=float,
        default=0.10,
        metavar="FRAC",
        help="Fraction of data for eval set (default 0.10).",
    )
    parser.add_argument(
        "--seed", type=int, default=42, help="Random seed for train/eval split."
    )
    args = parser.parse_args()

    hands = ["a", "b", "unknown"] if args.hand == "all" else [args.hand]
    for h in hands:
        counts = export_hand(h, eval_split=args.eval_split, seed=args.seed)
        total = counts["train"] + counts["eval"]
        if total == 0:
            print(f"Hand {h}: no confirmed samples — nothing to export.")
        else:
            print(
                f"Hand {h}: {counts['train']} train + {counts['eval']} eval "
                f"→ data/training/export/hand_{h}/"
            )
