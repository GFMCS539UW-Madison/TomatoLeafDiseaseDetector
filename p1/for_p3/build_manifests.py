#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = ["pillow>=10,<14", "numpy>=1.24,<3", "scipy>=1.10,<2"]
# ///
"""Rebuild the PlantDoc manifests shipped in this package from the original archive.

Reads TRAIN/, TEST/ and the label CSVs straight from the original PlantDoc
GitHub zip, so the result is identical on case-insensitive file systems (macOS,
Windows), where extracting that zip silently overwrites 10 of the TRAIN images.
Applies the
removals stated in the proposal, normalises every box to the EXIF-corrected
image frame, groups near-duplicate photos, and draws the tomato field-train /
field-dev split. Writes CSVs only; no image is copied, modified or deleted.

By default results go to new_manifests/ so the reviewed CSVs at the package
root are not overwritten. Pass --output . only to deliberately replace them.
"""

import argparse
import csv
import hashlib
import io
import random
import re
import zipfile
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np
from PIL import Image, ImageOps
from scipy.fft import dctn

HERE = Path(__file__).resolve().parent
SEED = 539
DEV_FRACTION = 0.15
TRANSPOSE = {
    2: Image.Transpose.FLIP_LEFT_RIGHT, 3: Image.Transpose.ROTATE_180,
    4: Image.Transpose.FLIP_TOP_BOTTOM, 5: Image.Transpose.TRANSPOSE,
    6: Image.Transpose.ROTATE_270, 7: Image.Transpose.TRANSVERSE,
    8: Image.Transpose.ROTATE_90,
}
# Ambiguous frames (EXIF rotation that keeps the image size). Empty: those 5
# photos stay unresolved. To recover one, inspect it and add
# {"<file name>": "raw" or "fixed"} for the frame its CSV boxes use.
AMBIGUOUS_FRAME_DECISIONS = {}
# PlantDoc tomato class -> PlantVillage label_id (same order as for_p2 CSVs).
CLASS_MAP = [
    (0, "Tomato___Bacterial_spot", "Tomato leaf bacterial spot"),
    (1, "Tomato___Early_blight", "Tomato Early blight leaf"),
    (2, "Tomato___Late_blight", "Tomato leaf late blight"),
    (3, "Tomato___Leaf_Mold", "Tomato mold leaf"),
    (4, "Tomato___Septoria_leaf_spot", "Tomato Septoria leaf spot"),
    (5, "Tomato___Spider_mites Two-spotted_spider_mite", ""),
    (6, "Tomato___Target_Spot", ""),
    (7, "Tomato___Tomato_Yellow_Leaf_Curl_Virus", "Tomato leaf yellow virus"),
    (8, "Tomato___Tomato_mosaic_virus", "Tomato leaf mosaic virus"),
    (9, "Tomato___healthy", "Tomato leaf"),
]
TO_LABEL = {pd: (i, pv) for i, pv, pd in CLASS_MAP if pd}
UNSAFE = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
MAX_NAME = 100


def portable_name(name, sha256, image_format, case_collision):
    """File name that extracts identically on Windows, macOS and Linux.

    Unchanged unless the original has a character Windows forbids, is longer
    than MAX_NAME, or differs from another name only by letter case.
    """
    if not (case_collision or UNSAFE.search(name) or len(name) > MAX_NAME or name.endswith((".", " "))):
        return name
    stem, dot, ext = name.rpartition(".")
    if not dot or not re.fullmatch(r"[A-Za-z0-9]{1,5}", ext):
        stem, ext = name, {"JPEG": "jpg", "MPO": "jpg"}.get(image_format, image_format.lower())
    stem = UNSAFE.sub("_", stem)[:80].rstrip(". ")
    return f"{stem}__{sha256[:8]}.{ext}"


def write_csv(path, rows, fields):
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def read_labels(text):
    by_file = defaultdict(list)
    for row in csv.DictReader(io.StringIO(text)):
        by_file[row["filename"]].append(row)
    return by_file


def image_info(data):
    """Size before/after EXIF correction, orientation, hashes on the corrected image."""
    with Image.open(io.BytesIO(data)) as im:
        raw = im.size
        orientation = im.getexif().get(274, 1)
        fixed = ImageOps.exif_transpose(im)
        gray = fixed.convert("RGB").convert("L")
        small = np.asarray(gray.resize((32, 32), Image.Resampling.LANCZOS), dtype=float)
        low = dctn(small, type=2, norm="ortho")[:8, :8]
        bits = low > np.median(low.ravel()[1:])
        bits[0, 0] = False
        phash = int("".join("1" if x else "0" for x in bits.ravel()), 2)
        small = np.asarray(gray.resize((9, 8), Image.Resampling.LANCZOS))
        dhash = int("".join("1" if x else "0" for x in (small[:, 1:] > small[:, :-1]).ravel()), 2)
        return {
            "raw_size": raw, "size": fixed.size, "orientation": orientation if orientation in TRANSPOSE else 1,
            "phash": phash, "dhash": dhash, "sha256": hashlib.sha256(data).hexdigest(), "mode": im.mode,
            "format": im.format,
        }


def close_aspect(a, b, tolerance=0.02):
    ra, rb = a[0] / a[1], b[0] / b[1]
    return abs(ra - rb) / max(ra, rb) <= tolerance


def transform_box(box, raw_size, orientation):
    """Map a raw-frame box into the EXIF-corrected frame using PIL's own transpose."""
    mask = Image.new("L", raw_size, 0)
    mask.paste(255, box)
    return mask.transpose(TRANSPOSE[orientation]).getbbox()


def normalise(filename, rows, info):
    """Return (box_fix, note, boxes in the EXIF-corrected frame or None)."""
    csv_size = (int(rows[0]["width"]), int(rows[0]["height"]))
    raw, size, orientation = info["raw_size"], info["size"], info["orientation"]
    boxes = [tuple(int(r[k]) for k in ("xmin", "ymin", "xmax", "ymax")) for r in rows]
    if csv_size == (0, 0):
        fix, note, frame, scale = "csv_size_missing", "CSV size 0x0; boxes lie in the actual image frame", "raw", None
    elif orientation != 1 and csv_size == size and csv_size != raw:
        fix, note, frame, scale = "none", "CSV uses the EXIF-corrected frame", "fixed", None
    elif orientation != 1 and csv_size == raw and csv_size != size:
        fix, note, frame, scale = "exif_raw_frame", "CSV uses raw pixels; boxes rotated to the EXIF-corrected frame", "raw", None
    elif orientation != 1 and csv_size == raw == size:
        decided = AMBIGUOUS_FRAME_DECISIONS.get(filename)
        if decided is None:
            return "unresolved", f"EXIF orientation {orientation} keeps the size; frame not determinable from sizes", None
        fix, note, frame, scale = f"ambiguous_{decided}_reviewed", f"EXIF orientation {orientation}; frame decided visually", decided, None
    elif csv_size == raw:
        fix, note, frame, scale = "none", "", "raw", None
    elif close_aspect(csv_size, raw):
        fix, note, frame, scale = "rescaled", f"CSV size {csv_size[0]}x{csv_size[1]}; boxes scaled to the actual image", "raw", (raw[0] / csv_size[0], raw[1] / csv_size[1])
    else:
        return "unresolved", f"CSV size {csv_size[0]}x{csv_size[1]} vs actual {raw[0]}x{raw[1]}; aspect differs", None
    out = []
    for box in boxes:
        if scale:
            box = (round(box[0] * scale[0]), round(box[1] * scale[1]), round(box[2] * scale[0]), round(box[3] * scale[1]))
        width, height = raw if frame == "raw" else size
        box = (max(0, box[0]), max(0, box[1]), min(width, box[2]), min(height, box[3]))
        if box[2] <= box[0] or box[3] <= box[1]:
            return "unresolved", "box outside the image after normalisation", None
        if frame == "raw" and orientation != 1:
            box = transform_box(box, raw, orientation)
        out.append(box)
    return fix, note, out


class HashTree:
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
            pending.extend(c for e, c in node[2].items() if distance - radius <= e <= distance + radius)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", type=Path, required=True, help="Original PlantDoc GitHub zip (not the Drive mirror)")
    parser.add_argument("--output", type=Path, default=HERE / "new_manifests")
    args = parser.parse_args()
    archive = zipfile.ZipFile(args.archive)
    prefix = archive.namelist()[0].split("/")[0] + "/"
    labels = {s: read_labels(archive.read(f"{prefix}{s}_labels.csv").decode("utf-8")) for s in ("train", "test")}
    folder = {"train": "TRAIN", "test": "TEST"}

    # Every image in the archive (labelled or not) takes part in duplicate search.
    photos = []
    for split in ("train", "test"):
        members = {n[len(prefix) + len(folder[split]) + 1:] for n in archive.namelist()
                   if n.startswith(f"{prefix}{folder[split]}/") and not n.endswith("/") and not n.lower().endswith(".xml")}
        lower = Counter(n.lower() for n in members | set(labels[split]))
        for name in sorted(members | set(labels[split])):
            photos.append({"split": split, "filename": name, "rows": labels[split].get(name, []), "exists": name in members,
                           "case_collision": lower[name.lower()] > 1, "member": f"{prefix}{folder[split]}/{name}"})
    present = [p for p in photos if p["exists"]]
    print(f"Hashing {len(present)} images...", flush=True)
    with ThreadPoolExecutor(max_workers=8) as pool:
        for p, info in zip(present, pool.map(image_info, (archive.read(p["member"]) for p in present))):
            p.update(info)
    for p in photos:
        name = p["filename"]
        if p["exists"]:
            name = portable_name(name, p["sha256"], p["format"], p["case_collision"])
        p["image_path"] = f"PlantDoc/{folder[p['split']]}/{name}"
    stored = Counter(p["image_path"].lower() for p in present)
    assert max(stored.values()) == 1, "image_path values must stay unique on case-insensitive file systems"

    # Exact and near-duplicate pairs (same thresholds as the PlantVillage package).
    pairs, tree = [], HashTree()
    for i, b in enumerate(present):
        for j in tree.query(b["phash"], 6):
            a = present[j]
            pd, dd = (a["phash"] ^ b["phash"]).bit_count(), (a["dhash"] ^ b["dhash"]).bit_count()
            if dd > 10 or not close_aspect(a["size"], b["size"]):
                continue
            kind = "exact_bytes" if a["sha256"] == b["sha256"] else "near_candidate"
            pairs.append((a, b, kind, pd, dd))
        tree.add(b["phash"], i)
    parent = {id(p): id(p) for p in present}

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    for a, b, *_ in pairs:
        parent[find(id(a))] = find(id(b))
    members = defaultdict(list)
    for p in present:
        members[find(id(p))].append(p)

    # Removals stated in the proposal, plus unusable files.
    test_names = set(labels["test"])
    exclusions = {}
    for p in photos:
        if p["split"] != "train":
            continue
        classes = sorted({r["class"] for r in p["rows"]})
        reasons = []
        if not p["exists"]:
            reasons.append("image_missing")
        if not p["rows"]:
            reasons.append("no_annotations")
        if p["filename"] in test_names:
            reasons.append("filename_shared_with_test")
        if p["exists"] and any(q["split"] == "test" and q["sha256"] == p["sha256"] for q in members[find(id(p))]):
            reasons.append("byte_identical_to_test")
        elif p["exists"] and any(q["split"] == "test" for q in members[find(id(p))]):
            reasons.append("near_duplicate_of_test")
        if len(classes) > 1:
            reasons.append("mixed_labels")
        if reasons:
            exclusions[p["filename"]] = reasons
        p["classes"] = classes

    # Box normalisation for every labelled train photo that exists.
    issues = []
    for p in photos:
        if p["split"] != "train" or not p["exists"] or not p["rows"]:
            continue
        fix, note, boxes = normalise(p["filename"], p["rows"], p)
        p["box_fix"], p["boxes"] = fix, boxes
        if fix != "none" or p["mode"] != "RGB" or p["case_collision"]:
            if p["case_collision"]:
                note = "; ".join(x for x in (note, f"file name differs from another only by case; stored as {p['image_path']}") if x)
            issues.append({
                "image_id": p["filename"], "image_path": p["image_path"], "classes": ";".join(p["classes"]),
                "exif_orientation": p["orientation"], "raw_size": "{}x{}".format(*p["raw_size"]),
                "corrected_size": "{}x{}".format(*p["size"]),
                "csv_size": "{}x{}".format(p["rows"][0]["width"], p["rows"][0]["height"]),
                "image_mode": p["mode"], "n_boxes": len(p["rows"]), "box_fix": fix,
                "boxes_usable": boxes is not None, "note": note or f"{p['mode']} image; convert('RGB') when loading",
                "review_status": "confirmed_by_P1_2026-11-10" if fix in ("rescaled", "exif_raw_frame", "csv_size_missing") else "",
            })

    # Tomato field split over near-duplicate groups, stratified by class.
    group_ids = {}
    for key, ms in members.items():
        name = min(m["filename"] for m in ms)
        for m in ms:
            group_ids[id(m)] = f"pd::{name}"
    tomato = [p for p in photos if p["split"] == "train" and p["filename"] not in exclusions
              and p["classes"] and p["classes"][0].startswith("Tomato")]
    groups = defaultdict(list)
    for p in tomato:
        groups[group_ids[id(p)]].append(p)
    by_class = defaultdict(list)
    for gid, ps in sorted(groups.items()):
        cls = Counter(p["classes"][0] for p in ps).most_common(1)[0][0]
        by_class[cls].append(gid)
    rng = random.Random(SEED)
    dev_groups = set()
    for cls in sorted(by_class):
        gids = sorted(by_class[cls])
        rng.shuffle(gids)
        target = round(DEV_FRACTION * sum(len(groups[g]) for g in gids))
        taken = 0
        for gid in gids:
            if taken >= target:
                break
            dev_groups.add(gid)
            taken += len(groups[gid])

    field = {"field_train": [], "field_dev": []}
    field_boxes = []
    dev_group_set = dev_groups
    for p in sorted(tomato, key=lambda q: q["filename"]):
        gid = group_ids[id(p)]
        split = "field_dev" if gid in dev_group_set else "field_train"
        label_id, label = TO_LABEL[p["classes"][0]]
        usable = p["boxes"] is not None
        row = {
            "image_id": p["filename"], "split": split, "label_id": label_id, "label": label,
            "plantdoc_class": p["classes"][0], "image_path": p["image_path"],
            "width": p["size"][0], "height": p["size"][1], "n_boxes": len(p["rows"]),
            "group_id": gid, "boxes_usable": usable, "box_fix": p["box_fix"], "sha256": p["sha256"],
        }
        field[split].append(row)
        for box in p["boxes"] or []:
            field_boxes.append(dict(row, xmin=box[0], ymin=box[1], xmax=box[2], ymax=box[3]))

    # Localizer: all crops, minus removals, tomato field-dev groups, unresolved boxes.
    localizer = []
    for p in photos:
        if p["split"] != "train" or p["filename"] in exclusions or not p.get("boxes"):
            continue
        gid = group_ids[id(p)]
        if gid in dev_group_set:
            continue
        for box, r in zip(p["boxes"], p["rows"]):
            localizer.append({
                "image_id": p["filename"], "image_path": p["image_path"], "width": p["size"][0], "height": p["size"][1],
                "xmin": box[0], "ymin": box[1], "xmax": box[2], "ymax": box[3], "label": "leaf",
                "plantdoc_class": r["class"], "box_fix": p["box_fix"], "group_id": gid, "sha256": p["sha256"],
            })
    excluded_from_localizer = sorted({p["filename"] for p in photos if p["split"] == "train" and p["filename"] not in exclusions
                                      and p.get("rows") and p.get("exists") and p.get("boxes") is None})

    excluded = []
    for p in photos:
        if p["split"] == "train" and p["filename"] in exclusions:
            excluded.append({
                "image_id": p["filename"], "plantdoc_split": "train", "classes": ";".join(p["classes"]),
                "n_boxes": len(p["rows"]), "image_path": p["image_path"],
                "exclusion_reason": ";".join(exclusions[p["filename"]]),
            })

    # Statuses P1 already recorded in the shipped duplicates.csv are carried over;
    # only pairs that file does not list come out as pending.
    reviewed = {}
    if (HERE / "duplicates.csv").exists():
        with (HERE / "duplicates.csv").open(newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                key = (row["a_plantdoc_split"], row["a_image_id"], row["b_plantdoc_split"], row["b_image_id"])
                reviewed[key] = row["review_status"]
    duplicates = []
    for a, b, kind, pd, dd in pairs:
        pending = "exact_match" if kind == "exact_bytes" else "pending_P1_visual_check"
        duplicates.append({
            "kind": kind, "a_image_id": a["filename"], "b_image_id": b["filename"],
            "a_plantdoc_split": a["split"], "b_plantdoc_split": b["split"],
            "a_classes": ";".join(sorted({r["class"] for r in a["rows"]})),
            "b_classes": ";".join(sorted({r["class"] for r in b["rows"]})),
            "a_image_path": a["image_path"], "b_image_path": b["image_path"],
            "involves_tomato": any(r["class"].startswith("Tomato") for r in a["rows"] + b["rows"]),
            "crosses_train_test": a["split"] != b["split"], "phash_distance": pd, "dhash_distance": dd,
            "review_status": reviewed.get((a["split"], a["filename"], b["split"], b["filename"]), pending),
        })
    duplicates.sort(key=lambda r: (not r["crosses_train_test"], not r["involves_tomato"], r["phash_distance"], r["a_image_id"]))

    args.output.mkdir(parents=True, exist_ok=True)
    field_fields = ["image_id", "split", "label_id", "label", "plantdoc_class", "image_path", "width", "height",
                    "n_boxes", "group_id", "boxes_usable", "box_fix", "sha256"]
    write_csv(args.output / "field_train.csv", field["field_train"], field_fields)
    write_csv(args.output / "field_dev.csv", field["field_dev"], field_fields)
    write_csv(args.output / "field_boxes.csv", field_boxes,
              ["image_id", "split", "label_id", "label", "image_path", "width", "height", "xmin", "ymin", "xmax", "ymax", "box_fix", "group_id"])
    write_csv(args.output / "localizer_train.csv", localizer,
              ["image_id", "image_path", "width", "height", "xmin", "ymin", "xmax", "ymax", "label", "plantdoc_class", "box_fix", "group_id", "sha256"])
    write_csv(args.output / "excluded.csv", excluded, ["image_id", "plantdoc_split", "classes", "n_boxes", "image_path", "exclusion_reason"])
    write_csv(args.output / "annotation_issues.csv", sorted(issues, key=lambda r: (r["box_fix"], r["image_id"])),
              ["image_id", "image_path", "classes", "exif_orientation", "raw_size", "corrected_size", "csv_size", "image_mode",
               "n_boxes", "box_fix", "boxes_usable", "note", "review_status"])
    write_csv(args.output / "duplicates.csv", duplicates,
              ["kind", "a_image_id", "b_image_id", "a_plantdoc_split", "b_plantdoc_split", "a_classes", "b_classes",
               "a_image_path", "b_image_path", "involves_tomato", "crosses_train_test", "phash_distance", "dhash_distance", "review_status"])
    write_csv(args.output / "class_map.csv",
              [{"label_id": i, "label": pv, "plantdoc_class": pd, "in_field_data": bool(pd)} for i, pv, pd in CLASS_MAP],
              ["label_id", "label", "plantdoc_class", "in_field_data"])

    reasons = Counter(r for rs in exclusions.values() for r in rs)
    tomato_all = [p for p in photos if p["split"] == "train" and any(r["class"].startswith("Tomato") for r in p["rows"])]
    print(f"Train photos: {sum(p['split'] == 'train' for p in photos)}; excluded: {len(exclusions)} {dict(reasons)}")
    print(f"Tomato train photos with labels: {len(tomato_all)}; single-label: {sum(len(p['classes']) == 1 for p in tomato_all)}")
    print(f"Field split: train {len(field['field_train'])}, dev {len(field['field_dev'])}; per class dev/total:")
    for cls in sorted(by_class):
        n = sum(len(groups[g]) for g in by_class[cls])
        d = sum(len(groups[g]) for g in by_class[cls] if g in dev_groups)
        print(f"  {cls}: {d}/{n}")
    print(f"Localizer boxes: {len(localizer)} in {len({r['image_id'] for r in localizer})} photos; "
          f"labelled photos without usable boxes: {len(excluded_from_localizer)}")
    print(f"Duplicate pairs: {len(pairs)}; crossing train/test: {sum(r['crosses_train_test'] for r in duplicates)}")
    print(f"Annotation issues: {Counter(r['box_fix'] for r in issues)}")
    print(f"Wrote {args.output}; no images changed.")


if __name__ == "__main__":
    main()
