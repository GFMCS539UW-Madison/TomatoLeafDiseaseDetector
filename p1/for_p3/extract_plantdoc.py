#!/usr/bin/env python3
"""Copy the PlantDoc images used by this package out of the original GitHub zip.

Uses the CSVs shipped beside this script. Only images listed in field_train.csv,
field_dev.csv and localizer_train.csv are written, each to its `image_path` and
checked against its sha256. The sealed tomato test photos and removed photos
are not extracted. Does not re-split data or change boxes.

Reads the zip directly instead of unpacking it: some original file names differ
only by letter case or contain characters Windows forbids.
"""

import argparse
import csv
import hashlib
import zipfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
MANIFESTS = ("field_train.csv", "field_dev.csv", "localizer_train.csv")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", required=True, type=Path, help="Original PlantDoc GitHub zip")
    parser.add_argument("--output", type=Path, default=HERE, help="Destination; existing matching files are overwritten")
    args = parser.parse_args()
    wanted = {}
    for name in MANIFESTS:
        with (HERE / name).open(newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                wanted[row["image_path"]] = (row["image_id"], row["sha256"])
    archive = zipfile.ZipFile(args.archive)
    prefix = archive.namelist()[0].split("/")[0] + "/"
    for image_path, (image_id, expected) in sorted(wanted.items()):
        data = archive.read(f"{prefix}TRAIN/{image_id}")
        if hashlib.sha256(data).hexdigest() != expected:
            raise SystemExit(f"sha256 mismatch for {image_id}; this is not the archive P1 used.")
        destination = args.output / image_path
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(data)
    print(f"Copied and verified {len(wanted)} images: {args.output / 'PlantDoc' / 'TRAIN'}")


if __name__ == "__main__":
    main()
