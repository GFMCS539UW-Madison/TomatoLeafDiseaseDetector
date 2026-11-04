# PlantVillage tomato data for P2

Prepared by P1, November 4, 2026. This package contains the color images for
10-class tomato disease classification and the current frozen split CSVs.

## Download the images

The color images are shared separately from Git:
[Download the color image archive from Google Drive](https://drive.google.com/file/d/1C16n-CU2GBRAd8gBzu7oyNa5P8S9h50U/view?usp=drive_link).

After cloning the repository, download and extract the archive, then place the
extracted `color/` folder directly inside `p1/for_p2/`. The resulting layout
should be `p1/for_p2/color/<class>/<original filename>`, with `color/` alongside
`train.csv`, `val.csv`, and `test.csv`. The supplied CSV paths will then work
without modification; there is no need to run `extract_color.py` for this download.

## Contents and use

```text
color/<class>/<original filename>   18,160 images
train.csv                          12,428 rows
val.csv                             2,088 rows
test.csv                            3,639 rows
excluded.csv                            5 rows, images still included
duplicates.csv                     Reviewed duplicate pairs
size_issues.csv                    Reviewed dimension mismatch
extract_color.py                   Copy color images using the supplied CSVs
find_duplicates.py                 Reproduce duplicate and dimension findings
random_review.py                   Sample color images for visual inspection
README.md                         Instructions and known-issue report
```

Read `train.csv` for training and `val.csv` for development/model selection.
The official test set is reserved for final evaluation. Load each image as
`package_directory / row['color_path']`, and use integer `label_id` (0–9) as
the classification target; `label` gives the corresponding class name.
Do not load all of `color/` recursively as a training set.

The CSVs preserve the current assignments: official test membership is unchanged,
and approximately 15% of the remaining training groups per class were assigned to
val. The five previously excluded training photos remain listed in `excluded.csv`;
their known groups overlap official test groups. They are physically retained.

The `segmented_path` column is reference metadata for finding the original file
under `PlantVillage/raw/`, **not a file included in this package**. P2's normal
classifier uses only `color_path`. Segmented and grayscale images are not shipped.

## Known issues and P1's decision

**Keep the images, labels, and existing splits. Record the problems only.** No new
exclusions, relabeling, or split changes were applied after the review.

### Duplicates

P1 reviewed the perceptual candidates and confirmed all 108 as duplicates on
November 4, 2026. Together with 14 exact-file duplicate pairs, `duplicates.csv`
contains 122 reviewed pairs involving 233 distinct photos.

- 51 confirmed pairs cross active train/val/test sets.
- 3 confirmed pairs carry different class labels; 1 of these crosses active sets.
- 5 pairs involve an already excluded photo; these do not count as active-set overlap.
- The 14 exact-file pairs do not cross active sets.

The current group IDs do not capture all of these reviewed associations. These
splits therefore contain known cross-set related images: model scores must be
reported with that limitation and cannot be presented as a leakage-free estimate.
Different-label duplicates are recorded without guessing which label is correct.

The detection method used pHash distance <= 6, dHash distance <= 10, and an
aspect-ratio relative difference <= 2%, across all tomato classes. Distances are
similarity measures, not identities. `kind=near_candidate` records how a pair was
found; `review_status` records P1's subsequent confirmation. A fresh script run
generates pending candidates; it does not overwrite the reviewed decisions here.

### Dimension mismatch

`size_issues.csv` records one confirmed mismatch in the test set:

- Class: `Tomato___Spider_mites Two-spotted_spider_mite`.
- Sample: `0db2da38-8650-461a-a785-814cc442f44d___Com.G_SpM_FL 1378`.
- Color: 256×256. Original segmented counterpart: 335×512.

The color image is retained. The mismatch matters when deriving a spatial mask
from the segmented image for P4; it does not prevent loading the color image for
P2. Do not assume that resizing alone establishes correct mask alignment.

### Other segmented-image observations relevant to P4

These are observations from a 100-pair visual sample, not a measured dataset-wide
defect rate. None changed the color classification data or labels.

| Class / original review number | Current split | Observation | Sample ID |
|---|---|---|---|
| Early blight 08 | train | Segmentation removes visibly necrotic leaf tissue. | `bc894aa4-76ca-427e-a964-e86236fc0217___RS_Erly.B 7526` |
| Late blight 01 | train | Upstream color already has a black background, visually almost identical to segmented. | `75c6ecf4-8a75-4bc6-bfcb-2331f5c56b38___GHLB_PS Leaf 24.1 Day 13` |
| Late blight 04 | train | Large diseased leaf regions are removed by segmentation. | `0879b927-2226-455f-9eac-10f5e1f36fdd___RS_Late.B 5331` |
| Late blight 10 | val | Upstream color already has a black background, visually almost identical to segmented. | `c933cfb7-d1c7-420b-88d0-7df28ae6ab2d___GHLB_PS Leaf 36.1 Day 13` |
| Leaf mold 01 | train | Considerable background remains; visible color differences. | `f3ef6606-c66b-4fa0-a542-f09b78b6c3e0___Crnl_L.Mold 9120` |
| Leaf mold 03 | test | Considerable background remains; visible color differences. | `7f283b23-4b47-47e2-9a9f-aa8619669018___Crnl_L.Mold 9044` |
| Leaf mold 06 | train | Background/shadow remains beside the leaf and stem. | `63ed021f-afc3-44cc-ab70-0bacc9815d3e___Crnl_L.Mold 6997` |
| Leaf mold 09 | train | Much of the background remains; visible color differences. | `ec76173b-c354-4711-9bb7-b38dae1ea5b4___Crnl_L.Mold 9074` |

Segmented images must not be assumed to provide accurate leaf masks for the
background-only diagnostic. The two black-background color images may also
introduce class-correlated background cues in ordinary classification.

## Scripts

Run the following from this directory. The extraction and random-sampling scripts
use only Python's standard library. The duplicate script uses Pillow, NumPy and
SciPy; `uv run` supplies them automatically.

Re-create the color subset from the original PlantVillage, using the frozen CSVs
shipped here (no new split or duplicate removal):

```bash
python3 -B extract_color.py --raw-root "/path/to/PlantVillage"
```

Reproduce duplicate findings and the paired dimension mismatch:

```bash
uv run find_duplicates.py --raw-root "/path/to/PlantVillage"
```

Without `--raw-root`, duplicate search still works using this package, but the
color/segmented dimension comparison is explicitly skipped because the segmented
files are not included. Results go to `new_findings/`, leaving the reviewed
`duplicates.csv` and `size_issues.csv` at the package root untouched.

Randomly sample 10 color images per class from the current train/val/test CSVs:

```bash
python3 -B random_review.py --per-class 10 --seed 539
```

This overwrites only `review/`, with sampled images and their source paths in
`review/review.csv`. Use `--split train` to inspect training photos only. The
default all-split sample is for data quality inspection, not model tuning.

The source dataset is [PlantVillage](https://github.com/spMohanty/PlantVillage-Dataset).
This handoff covers its tomato subset only; PlantDoc field fine-tuning data is
outside this package.
