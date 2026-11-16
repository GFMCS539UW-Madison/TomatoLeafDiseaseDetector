#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = ["pillow>=10,<14"]
# ///
"""Draw the shipped boxes on EXIF-corrected images for visual inspection.

Writes overlays to review/ (overwritten). Does not change data, boxes or splits.
Default: every image listed in annotation_issues.csv that still has usable boxes,
plus a random sample of tomato field-train photos per class.
"""

import argparse
import csv
import random
import shutil
from collections import defaultdict
from pathlib import Path

from PIL import Image, ImageDraw, ImageOps

HERE = Path(__file__).resolve().parent


def load(path):
    with Image.open(path) as im:
        return ImageOps.exif_transpose(im).convert("RGB")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, default=HERE)
    parser.add_argument("--output", type=Path, help="Default: dataset/review (overwritten)")
    parser.add_argument("--split", choices=("field_train", "field_dev"), default="field_train",
                        help="Tomato split for the random sample")
    parser.add_argument("--per-class", type=int, default=3)
    parser.add_argument("--seed", type=int, default=539)
    args = parser.parse_args()
    output = args.output or args.dataset / "review"
    boxes = defaultdict(list)
    for name in ("localizer_train.csv", "field_boxes.csv"):
        with (args.dataset / name).open(newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                key = (row["image_id"], row["image_path"])
                box = tuple(int(row[k]) for k in ("xmin", "ymin", "xmax", "ymax"))
                if box not in boxes[key]:
                    boxes[key].append(box)
    chosen = []
    with (args.dataset / "annotation_issues.csv").open(newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            if row["boxes_usable"] == "True" and row["box_fix"] != "none":
                chosen.append(("issue_" + row["box_fix"], row["image_id"], row["image_path"]))
    by_class = defaultdict(list)
    with (args.dataset / f"{args.split}.csv").open(newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            if row["boxes_usable"] == "True":
                by_class[row["label"]].append(row)
    rng = random.Random(args.seed)
    for label in sorted(by_class):
        for row in rng.sample(sorted(by_class[label], key=lambda r: r["image_id"]), min(args.per_class, len(by_class[label]))):
            chosen.append((f"{args.split}_{label}", row["image_id"], row["image_path"]))
    if output.exists():
        shutil.rmtree(output)
    records = []
    for number, (group, image_id, image_path) in enumerate(chosen, 1):
        im = load(args.dataset / image_path)
        draw = ImageDraw.Draw(im)
        width = max(2, round(max(im.size) / 250))
        for box in boxes[(image_id, image_path)]:
            draw.rectangle(box, outline=(255, 0, 255), width=width)
        im.thumbnail((1024, 1024))
        destination = output / group / f"{number:03d}.jpg"
        destination.parent.mkdir(parents=True, exist_ok=True)
        im.save(destination, quality=90)
        records.append({"review_path": destination.relative_to(output).as_posix(), "image_id": image_id,
                        "image_path": image_path, "n_boxes": len(boxes[(image_id, image_path)])})
    with (output / "review.csv").open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["review_path", "image_id", "image_path", "n_boxes"])
        writer.writeheader()
        writer.writerows(records)
    print(f"{len(records)} overlays: {output}")


if __name__ == "__main__":
    main()
