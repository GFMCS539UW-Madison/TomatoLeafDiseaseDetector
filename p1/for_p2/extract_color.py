#!/usr/bin/env python3
"""Copy the frozen 10-class tomato color subset from the original PlantVillage.

Uses the CSVs shipped beside this script, including excluded.csv. Does not
re-split data, remove duplicates, or copy segmented/grayscale images.
"""

import argparse
import csv
import shutil
from pathlib import Path

HERE = Path(__file__).resolve().parent
SPLITS = ("train", "val", "test", "excluded")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--raw-root", required=True, type=Path, help="Original PlantVillage directory containing raw/")
    parser.add_argument("--output", type=Path, default=HERE, help="Destination; existing matching files are overwritten")
    args = parser.parse_args()
    output = args.output.resolve()
    rows = []
    for split in SPLITS:
        with (HERE / f"{split}.csv").open(newline="", encoding="utf-8") as f:
            rows.extend(csv.DictReader(f))
    for row in rows:
        source = args.raw_root / "raw" / row["color_path"]
        destination = output / row["color_path"]
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)
    if output != HERE:
        for split in SPLITS:
            shutil.copy2(HERE / f"{split}.csv", output / f"{split}.csv")
    print(f"Copied {len(rows)} color images and preserved the supplied splits: {output}")


if __name__ == "__main__":
    main()
