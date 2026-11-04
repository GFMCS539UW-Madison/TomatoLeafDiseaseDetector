#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = ["pillow>=10,<14", "numpy>=1.24,<3", "scipy>=1.10,<2"]
# ///
"""Find duplicate color candidates and mismatched color/segmented dimensions.

Writes two short CSVs only. No deletion, re-splitting, integrity audit, or source
file comparison. Original segmented images are optional and are not in this pack.
"""

import argparse
import csv
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np
from PIL import Image
from scipy.fft import dctn

HERE = Path(__file__).resolve().parent
DUPLICATE_FIELDS = [
    "kind", "a_sample_id", "b_sample_id", "a_label", "b_label", "a_split", "b_split",
    "a_color_path", "b_color_path", "cross_active_splits", "different_labels",
    "phash_distance", "dhash_distance", "review_status",
]
SIZE_FIELDS = ["sample_id", "label", "split", "color_path", "segmented_path", "color_size", "segmented_size", "review_status"]


def write_csv(path, rows, fields):
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def features(path):
    with Image.open(path) as im:
        width, height = im.size
        gray = im.convert("RGB").convert("L")
        small = np.asarray(gray.resize((32, 32), Image.Resampling.LANCZOS), dtype=float)
        low = dctn(small, type=2, norm="ortho")[:8, :8]
        bits = low > np.median(low.ravel()[1:])
        bits[0, 0] = False
        phash = int("".join("1" if x else "0" for x in bits.ravel()), 2)
        small = np.asarray(gray.resize((9, 8), Image.Resampling.LANCZOS))
        dhash = int("".join("1" if x else "0" for x in (small[:, 1:] > small[:, :-1]).ravel()), 2)
        return width, height, phash, dhash


class HashTree:
    """Search perceptual hashes without comparing every possible image pair."""

    def __init__(self):
        self.root = None

    def add(self, value, index):
        if self.root is None:
            self.root = [value, [index], {}]
            return
        node = self.root
        while True:
            distance = (value ^ node[0]).bit_count()
            if distance == 0:
                node[1].append(index)
                return
            if distance not in node[2]:
                node[2][distance] = [value, [index], {}]
                return
            node = node[2][distance]

    def query(self, value, radius):
        pending = [self.root] if self.root else []
        while pending:
            node = pending.pop()
            distance = (value ^ node[0]).bit_count()
            if distance <= radius:
                yield from node[1]
            pending.extend(child for edge, child in node[2].items() if distance - radius <= edge <= distance + radius)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, default=HERE)
    parser.add_argument("--raw-root", type=Path, help="Original PlantVillage containing raw/segmented; enables paired size checks")
    parser.add_argument("--output", type=Path, default=HERE / "new_findings", help="Separate output directory, leaving reviewed reports untouched")
    args = parser.parse_args()
    rows = []
    for split in ("train", "val", "test", "excluded"):
        with (args.dataset / f"{split}.csv").open(newline="", encoding="utf-8") as f:
            rows.extend(csv.DictReader(f))
    rows.sort(key=lambda row: row["sample_id"])
    print(f"Reading {len(rows)} color images...", flush=True)
    with ThreadPoolExecutor(max_workers=8) as pool:
        values = list(pool.map(features, (args.dataset / r["color_path"] for r in rows)))
    duplicates, size_issues = [], []
    tree = HashTree()
    for i, (width, height, phash, dhash) in enumerate(values):
        b = rows[i]
        for j in tree.query(phash, 6):
            w, h, p, d = values[j]
            pd, dd = (phash ^ p).bit_count(), (dhash ^ d).bit_count()
            if dd > 10 or abs(width / height - w / h) / max(width / height, w / h) > 0.02:
                continue
            a = rows[j]
            left, right = args.dataset / a["color_path"], args.dataset / b["color_path"]
            if left.read_bytes() == right.read_bytes():
                kind = "exact_bytes"
            else:
                with Image.open(left) as x, Image.open(right) as y:
                    same_pixels = x.size == y.size and x.convert("RGB").tobytes() == y.convert("RGB").tobytes()
                kind = "exact_pixels" if same_pixels else "near_candidate"
            duplicates.append({
                "kind": kind, "a_sample_id": a["sample_id"], "b_sample_id": b["sample_id"],
                "a_label": a["label"], "b_label": b["label"], "a_split": a["split"], "b_split": b["split"],
                "a_color_path": a["color_path"], "b_color_path": b["color_path"],
                "cross_active_splits": a["split"] != b["split"] and "excluded" not in (a["split"], b["split"]),
                "different_labels": a["label"] != b["label"], "phash_distance": pd, "dhash_distance": dd,
                "review_status": "pending" if kind == "near_candidate" else "exact_match",
            })
        tree.add(phash, i)
        if args.raw_root:
            segmented = args.raw_root / "raw" / b["segmented_path"]
            with Image.open(segmented) as im:
                seg_size = im.size
            if (width, height) != seg_size:
                size_issues.append({
                    "sample_id": b["sample_id"], "label": b["label"], "split": b["split"],
                    "color_path": b["color_path"], "segmented_path": b["segmented_path"],
                    "color_size": f"{width}x{height}", "segmented_size": f"{seg_size[0]}x{seg_size[1]}",
                    "review_status": "observed",
                })
    duplicates.sort(key=lambda r: (not r["cross_active_splits"], r["phash_distance"], r["dhash_distance"], r["a_sample_id"], r["b_sample_id"]))
    args.output.mkdir(parents=True, exist_ok=True)
    write_csv(args.output / "duplicates.csv", duplicates, DUPLICATE_FIELDS)
    if args.raw_root:
        write_csv(args.output / "size_issues.csv", size_issues, SIZE_FIELDS)
    print(f"Duplicate pairs: {len(duplicates)}; cross active splits: {sum(r['cross_active_splits'] for r in duplicates)}")
    print(f"Paired dimension issues: {len(size_issues)}" if args.raw_root else "Paired dimension check skipped: pass --raw-root to access original segmented images.")
    print(f"Reports: {args.output}; no images, labels, or splits changed.")


if __name__ == "__main__":
    main()
