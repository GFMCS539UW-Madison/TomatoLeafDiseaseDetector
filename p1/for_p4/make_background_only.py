#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = ["pillow>=10,<14", "numpy>=1.24,<3", "scipy>=1.10,<2"]
# ///
"""Black out the leaf in every PlantVillage tomato color image for the background diagnostic.

Leaf mask = pixels of the segmented image whose brightest channel exceeds
--threshold, with interior holes filled, then dilated by --dilate pixels so the
JPEG halo at the leaf edge is also removed. The color image is copied with the
mask set to black and written to background_only/ (overwritten).

Uses the frozen split CSVs from ../for_p2; does not re-split, relabel or exclude.
Writes background_masks.csv (every image) and background_flags.csv (flagged or
skipped images only) with per-image mask statistics.
"""

import argparse
import csv
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np
from PIL import Image
from scipy import ndimage

HERE = Path(__file__).resolve().parent
SPLITS = ("train", "val", "test", "excluded")
FIELDS = [
    "sample_id", "split", "label_id", "label", "group_id", "color_path", "segmented_path", "background_path",
    "status", "leaf_fraction", "filled_fraction", "dilated_fraction", "background_brightness", "flags",
]


def process(row, args):
    out = {k: row[k] for k in ("sample_id", "split", "label_id", "label", "group_id", "color_path", "segmented_path")}
    background_path = Path("background_only") / Path(row["color_path"]).relative_to("color").with_suffix(".png")
    with Image.open(args.color_root / row["color_path"]) as c, Image.open(args.segmented_root / row["segmented_path"]) as s:
        color = np.asarray(c.convert("RGB"))
        seg = np.asarray(s.convert("RGB"))
    if color.shape != seg.shape:
        return dict(out, background_path="", status="skipped_size_mismatch",
                    flags=f"color {color.shape[1]}x{color.shape[0]} vs segmented {seg.shape[1]}x{seg.shape[0]}")
    raw = seg.max(axis=2) > args.threshold
    filled = ndimage.binary_fill_holes(raw)
    mask = ndimage.binary_dilation(filled, iterations=args.dilate) if args.dilate else filled
    background = color.copy()
    background[mask] = 0
    destination = args.output / background_path
    destination.parent.mkdir(parents=True, exist_ok=True)
    Image.fromarray(background).save(destination, optimize=True)
    outside = color[~mask]
    brightness = float(outside.max(axis=1).mean()) if outside.size else 0.0
    flags = []
    leaf = float(mask.mean())
    if leaf < args.low:
        flags.append("small_mask")
    if leaf > args.high:
        flags.append("mask_covers_most_of_image")
    if outside.size and brightness < args.dark:
        flags.append("dark_background_in_color")
    return dict(out, background_path=background_path.as_posix(), status="written",
                leaf_fraction=f"{raw.mean():.4f}", filled_fraction=f"{filled.mean():.4f}",
                dilated_fraction=f"{leaf:.4f}", background_brightness=f"{brightness:.1f}", flags=";".join(flags))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--splits", type=Path, default=HERE.parent / "for_p2", help="Directory with train/val/test/excluded.csv")
    parser.add_argument("--color-root", type=Path, default=HERE.parent / "for_p2", help="Directory containing color/")
    parser.add_argument("--segmented-root", type=Path, default=HERE, help="Directory containing segmented/")
    parser.add_argument("--output", type=Path, default=HERE)
    parser.add_argument("--threshold", type=int, default=20, help="Brightest-channel cut on the segmented image (0-255)")
    parser.add_argument("--dilate", type=int, default=2, help="Mask dilation in pixels")
    parser.add_argument("--low", type=float, default=0.05, help="Flag masks below this image fraction")
    parser.add_argument("--high", type=float, default=0.85, help="Flag masks above this image fraction")
    parser.add_argument("--dark", type=float, default=40, help="Flag color backgrounds darker than this mean brightness")
    args = parser.parse_args()
    rows = []
    for split in SPLITS:
        with (args.splits / f"{split}.csv").open(newline="", encoding="utf-8") as f:
            rows.extend(csv.DictReader(f))
    print(f"Masking {len(rows)} images...", flush=True)
    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(lambda r: process(r, args), rows))
    with (args.output / "background_masks.csv").open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(results)
    with (args.output / "background_flags.csv").open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(r for r in results if r["flags"] or r["status"] != "written")
    written = [r for r in results if r["status"] == "written"]
    flagged = {}
    for r in written:
        for flag in filter(None, r["flags"].split(";")):
            flagged[flag] = flagged.get(flag, 0) + 1
    print(f"Written {len(written)}; skipped {len(results) - len(written)}; flags {flagged}")
    print(f"Images: {args.output / 'background_only'}; tables: background_masks.csv, background_flags.csv")


if __name__ == "__main__":
    main()
