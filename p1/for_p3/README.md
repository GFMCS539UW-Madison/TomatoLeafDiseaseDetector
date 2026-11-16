# PlantDoc field data for P3

Prepared by P1, November 7, 2026. This package contains the PlantDoc boxes for
training the one-class leaf localizer (C1) and the tomato field-train /
field-dev split. It is also the shared PlantDoc source for P2 (field fine-tuning
and crop arm) and P4 (calibration and Grad-CAM in-box fraction); those packages
point here instead of copying the CSVs.

## Download the images

The images are shared separately from Git:
[Download the PlantDoc image archive from Google Drive](https://drive.google.com/file/d/116kK8jd8YB-uTBB0pTJVMnwaila71hS5/view?usp=sharing).

After cloning the repository, download and extract the archive, then place the
extracted `PlantDoc/` folder directly inside `p1/for_p3/`. The resulting layout
should be `p1/for_p3/PlantDoc/TRAIN/<file>`, with `PlantDoc/` alongside the
CSVs. The supplied `image_path` values will then work without modification;
there is no need to run `extract_plantdoc.py` for this download.

The archive (849 MB) holds only the 2,295 train images the manifests use. The
sealed test photos and the removed photos are not in it.

**Open files by `image_path`, not `image_id`.** `image_id` is the original
PlantDoc file name. 137 images are stored under a changed name
(`<name>__<sha8>.<ext>`) because the original name contains a character Windows
forbids (81, mostly `?`), is longer than 100 characters (36 more), or differs
from another name only by letter case (20, for example `car1.jpg` and
`CAR1.jpg`). For the same reason, do not unzip the original PlantDoc GitHub
archive on macOS or Windows: the case-colliding files overwrite each other and
their boxes end up on the wrong image.

## Contents and use

```text
PlantDoc/TRAIN/<file>             2,295 images (download)
localizer_train.csv               7,826 boxes in 2,196 photos, all crops
field_train.csv                     556 tomato photos
field_dev.csv                        99 tomato photos
field_boxes.csv                   2,622 boxes of field_train (2,168) and field_dev (454)
class_map.csv                        10 rows, PlantDoc class -> label_id
excluded.csv                         64 train photos removed, with reasons
duplicates.csv                       64 exact or near-duplicate pairs
annotation_issues.csv                55 files with frame, size or mode notes
extract_plantdoc.py               Copy the images out of the original PlantDoc zip
build_manifests.py                Rebuild every CSV from the original PlantDoc zip
draw_boxes.py                     Draw boxes for visual inspection
review_duplicates.py              Side-by-side page of near-duplicate pairs (P1 review)
README.md                         Instructions and known-issue report
```

**Image loading and box frame.** Every box is in pixel coordinates of the
EXIF-corrected image. Load each image exactly like this:

```python
from PIL import Image, ImageOps
image = ImageOps.exif_transpose(Image.open(package_dir / row["image_path"])).convert("RGB")
```

`width` and `height` in the CSVs are the size after `exif_transpose`. Skipping
`exif_transpose` (for example `torchvision.io.read_image`) misplaces the boxes
on 21 rotated photos; skipping `convert("RGB")` fails on CMYK, RGBA and
grayscale files. Boxes are `xmin, ymin, xmax, ymax`, already clipped to the image.

**Localizer (C1).** Train on `localizer_train.csv`. Every box has `label=leaf`;
the original PlantDoc class stays in `plantdoc_class` for reference only. It
covers all crops' train photos except removed photos (`excluded.csv`), tomato
field-dev photos and their near-duplicates, and 5 photos whose box frame could
not be determined. Tomato field-train photos are included, as the proposal allows.

**Tomato field split.** `field_train.csv` and `field_dev.csv` hold one row per
photo, with integer `label_id` (0–9) and `label` matching the PlantVillage
names in `../for_p2`. Their boxes are in `field_boxes.csv` (join on
`image_path`). Read `field_train.csv` for training and `field_dev.csv` for model
selection, `s_min`, `T` and `τ`. Field-dev is never used to train the localizer.

**Development criterion (Nov 15).** The proposal's test, computed the way P1 will
check it: for each of the 99 `field_dev.csv` photos take the single top-scoring
predicted box; the photo is a hit if that box has IoU ≥ 0.5 with any of its
annotated boxes in `field_boxes.csv`. C1 is kept if hits ≥ 80% of photos
(≥ 80 of 99); otherwise switch to the Segment Anything fallback.

**Sealed field test.** The 69 official tomato test photos are held by P1 and
are not shipped. They are excluded from all training here. P1 runs the final
test once per frozen configuration.

## Classes

`class_map.csv` maps the 8 PlantDoc tomato classes one-to-one to our labels.
`Tomato___Spider_mites Two-spotted_spider_mite` (5) and `Tomato___Target_Spot`
(6) have no PlantDoc class (`in_field_data=False`): field metrics cover the 8
shared classes, and those two classes are evaluated on PlantVillage only. The
only two PlantDoc spider-mite boxes are inside mixed-label photos, which are removed.

| label_id | Field-train | Field-dev | Total |
|---:|---:|---:|---:|
| 0 Bacterial spot | 85 | 15 | 100 |
| 1 Early blight | 59 | 10 | 69 |
| 2 Late blight | 84 | 15 | 99 |
| 3 Leaf mold | 72 | 13 | 85 |
| 4 Septoria leaf spot | 117 | 20 | 137 |
| 7 Yellow leaf curl virus | 58 | 11 | 69 |
| 8 Mosaic virus | 37 | 7 | 44 |
| 9 Healthy | 44 | 8 | 52 |
| **Total** | **556** | **99** | **655** |

The split is 85/15 per class, seed 539, over near-duplicate groups (`group_id`):
photos in one group always share a split. Field-dev averages 4.6 boxes per
photo, field-train 3.9; the PlantDoc test averages fewer (1.92 vs 3.61 for all
train photos), which is why C1 is judged by recall.

## Known issues and P1's decision

**Apply the removals stated in the proposal, plus 3 train photos that are
near-duplicates of test photos; keep every other photo and label.**
Box coordinates were normalised to one frame, but no box was moved by hand and
no label was changed.

### Removed photos (`excluded.csv`)

Of 2,367 PlantDoc train photos, 64 are removed:

| Reason | Photos | Tomato |
|---|---:|---:|
| File name shared with a test photo (11 of these byte-identical, 1 near-identical) | 16 | 4 |
| Near-duplicate of a test photo, different file name | 3 | 3 |
| Mixed labels in one photo | 20 | 15 |
| Image file absent from the archive | 3 | 0 |
| Image in the archive with no annotation rows | 22 | 0 |

These reproduce the proposal's counts: 677 tomato train photos, 662 single-label
in 8 classes, 15 mixed-label dropped, 69 test photos; 11 byte-identical and 16
shared names across splits; 20 mixed-label train photos. Removing the 7 tomato
photos that overlap the test set leaves 655 for the field split.

### Duplicates

`duplicates.csv` lists 64 pairs found with the PlantVillage method (pHash
distance ≤ 6, dHash ≤ 10, aspect-ratio difference ≤ 2%, on EXIF-corrected
images), across train and test and all crops: 12 exact-byte pairs (11 train↔test)
and 52 near candidates (4 train↔test). 38 pairs involve a tomato photo.

- P1 compared all 52 near candidates side by side and confirmed every one as a
  duplicate on November 10, 2026 (`confirmed_duplicate_by_P1_2026-11-10`). The
  review only records them: it removed and relabelled nothing.
- The train member of every train↔test pair was already removed when the
  manifests were built (above), so that no copy of a test photo is trained on.
  For 3 tomato photos the near-duplicate is the only tie to the test set; the
  proposal does not list this case, and P1 decided on November 10, 2026 to keep
  them removed.
- Within train, both photos of every pair are kept. They share a `group_id`, so
  they fall in the same field split.
- 26 of the 52 confirmed pairs carry different class labels, tomato against
  potato included.
- 7 tomato groups contain photos with different disease labels, e.g. the same
  image labelled Bacterial spot and Septoria (`FS547-4-big.jpg` group). 3 photos
  labelled potato in train are near-duplicates of tomato field-dev photos and are
  kept out of localizer training. Labels are recorded, not corrected; PlantDoc's
  authors warn some labels may be wrong.

### Box frames (`annotation_issues.csv`)

The original label CSV records each photo's width and height; 55 files needed
attention. `box_fix` says what was done:

| box_fix | Files | Action |
|---|---:|---|
| `exif_raw_frame` | 16 | Annotated on raw pixels of an EXIF-rotated JPEG; boxes rotated into the corrected frame (4 tomato field photos). |
| `csv_size_missing` | 4 | CSV size 0×0; boxes lie inside the actual image and are used as is. |
| `rescaled` | 3 | CSV size is a scaled copy with the same aspect ratio; boxes scaled to the actual image. |
| `unresolved` | 5 | EXIF rotation by 180° or a square photo, so the frame cannot be told from sizes. Not in any manifest (all non-tomato). |
| `none` | 27 | Boxes unchanged; noted for case-colliding names (20, stored under a changed name) or CMYK/RGBA/L images (7). |

P1 reviewed the `draw_boxes.py` overlays of all 23 corrected files
(`exif_raw_frame`, `csv_size_missing`, `rescaled`) and confirmed that the boxes
sit on the leaves (`review_status=confirmed_by_P1_2026-11-10`). After
normalisation every box lies inside its image. All 655 tomato field photos have
usable boxes.

### Other observations

A visual sample shows some PlantDoc "field" photos are illustrations, collages or
slide screenshots, and box density varies widely (one to 20+ leaves per photo).
These were kept. They limit how far field-dev recall predicts phone-photo behaviour.

## Scripts

Run the following from this directory. `extract_plantdoc.py` uses only Python's
standard library; the others use Pillow (and NumPy and SciPy for hashing);
`uv run` supplies them automatically. Scripts that take `--archive` need the
original PlantDoc zip from GitHub (commit
`4730a233a555b30ee98e0879c63ad25d82407455`), not the Drive archive.

Re-create `PlantDoc/` from the original zip, using the CSVs shipped here (each
image is checked against its `sha256`; no new split):

```bash
python3 -B extract_plantdoc.py --archive "/path/to/PlantDoc-Object-Detection-Dataset.zip"
```

Rebuild every CSV from the original zip (removals, box frames, portable file
names, duplicate groups, field split with seed 539):

```bash
uv run build_manifests.py --archive "/path/to/PlantDoc-Object-Detection-Dataset.zip"
```

Results go to `new_manifests/`, leaving the CSVs here untouched. Review
statuses already recorded in `duplicates.csv` are carried over; a pair that
file does not list comes out as `pending_P1_visual_check`.

Draw boxes on the corrected files plus 3 random photos per class:

```bash
uv run draw_boxes.py --split field_train --per-class 3
```

This overwrites only `review/`, with overlays and `review/review.csv`. Inspect
field-train for annotation quality; avoid tuning on what you see in field-dev.

Build a page showing each near-duplicate candidate pair side by side (P1's
review tool; it embeds test photos, so the page is not shared):

```bash
uv run review_duplicates.py --archive "/path/to/PlantDoc-Object-Detection-Dataset.zip"
```

This overwrites only `duplicate_review.html`.

The source dataset is [PlantDoc](https://github.com/pratikkayal/PlantDoc-Object-Detection-Dataset)
(Singh et al., CoDS-COMAD 2020), licensed CC BY 4.0.
