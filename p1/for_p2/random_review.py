#!/usr/bin/env python3
"""Copy a random color-image sample per class. Does not change data or splits."""

import argparse
import csv
import random
import shutil
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, default=HERE)
    parser.add_argument("--output", type=Path, help="Default: dataset/review (overwritten)")
    parser.add_argument("--split", choices=("all", "train", "val", "test"), default="all")
    parser.add_argument("--per-class", type=int, default=10)
    parser.add_argument("--seed", type=int, default=539)
    args = parser.parse_args()
    if args.per_class < 1:
        parser.error("--per-class must be positive")
    output = args.output or args.dataset / "review"
    by_class = defaultdict(list)
    for split in ("train", "val", "test") if args.split == "all" else (args.split,):
        with (args.dataset / f"{split}.csv").open(newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                by_class[row["label"]].append(row)
    rng = random.Random(args.seed)
    chosen = []
    for label in sorted(by_class):
        pool = sorted(by_class[label], key=lambda r: r["sample_id"])
        if len(pool) < args.per_class:
            parser.error(f"{label}: fewer than {args.per_class} photos")
        for number, row in enumerate(rng.sample(pool, args.per_class), 1):
            path = Path(label) / f"{number:02d}{Path(row['color_path']).suffix}"
            chosen.append(dict(row, review_path=path.as_posix()))
    if output.exists():
        shutil.rmtree(output)
    for row in chosen:
        destination = output / row["review_path"]
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(args.dataset / row["color_path"], destination)
    with (output / "review.csv").open("w", newline="", encoding="utf-8") as f:
        fields = ["sample_id", "label", "split", "color_path", "review_path"]
        writer = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(chosen)
    print(f"{len(chosen)} color photos: {output}")


if __name__ == "__main__":
    main()
