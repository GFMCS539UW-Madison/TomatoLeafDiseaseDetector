# Data for P4: background diagnostic, calibration and Grad-CAM

Prepared by P1, November 7, 2026. This package contains the PlantVillage
segmented images, a script that blacks out the leaf in every color image for the
background-shortcut diagnostic, and a reviewed list of images where that mask
is unreliable. Calibration and Grad-CAM use the PlantDoc field split in
[for_p3](../for_p3/README.md); nothing is copied here.

## Download the images

The segmented images are shared separately from Git:
[Download the segmented image archive from Google Drive](https://drive.google.com/file/d/1qDlPwSXRlCazIHfnrtU2W2AF7xCFoFu9/view?usp=drive_link).

After cloning the repository, download and extract the archive, then place the
extracted `segmented/` folder directly inside `p1/for_p4/`. The resulting layout
should be `p1/for_p4/segmented/<class>/<original filename>`. You also need the
color images in `p1/for_p2/color/`, as described in the
[P2 package](../for_p2/README.md#download-the-images).

Then build the background-only images (about 1 minute, 1 GB of PNG):

```bash
uv run make_background_only.py
```

## Contents and use

```text
segmented/<class>/<original filename>   18,160 images (download)
background_only/<class>/<name>.png      18,159 images (generated, not in Git)
background_masks.csv                    18,160 rows (generated, not in Git)
background_flags.csv                       173 rows, reviewed flags
make_background_only.py                 Build background_only/ and both tables
README.md                               Instructions and known-issue report
```

### 1. Background diagnostic (PlantVillage)

Train the same ResNet-18 recipe as P2 on images whose leaf is blacked out.
Use the frozen splits in `../for_p2` unchanged: rows of `background_masks.csv`
carry `sample_id`, `split`, `label_id` and `group_id` from those CSVs. Read
`split=train` for training, `split=val` for model selection, and `split=test`
for the reported score; `split=excluded` rows are reference only. Load each
image as `package_directory / row['background_path']`. Only rows with
`status=written` have an image; the one skipped row is listed below.

The mask recipe, fixed before any diagnostic run:

1. Leaf = segmented pixels whose brightest channel exceeds 20 (of 255). The
   segmented background is near zero; JPEG ringing at the leaf edge stays below
   about 20.
2. Fill interior holes, so dark lesions inside the leaf are also removed.
3. Dilate by 2 pixels, so the bright halo along the leaf edge is removed.
4. Set those pixels to black in the color image; save as PNG (lossless).

`--threshold` and `--dilate` change steps 1 and 3. If you change them, commit
the values before training, and rerun the script so the flags match.

Chance level is 10% on 10 classes; accuracy well above it confirms the shortcut
on our subset. Report the score with the limitations below.

### 2. Calibration and abstention (PlantDoc field-dev)

Download the PlantDoc images as described in the
[P3 package](../for_p3/README.md#download-the-images), and open them by `image_path`.
Fit `T`, `τ` and (with P3) `s_min` on the 99 photos of
[`../for_p3/field_dev.csv`](../for_p3/field_dev.csv), using its integer
`label_id`. Field-dev covers the 8 classes with PlantDoc data; classes 5
(Spider mites) and 6 (Target spot) never appear there, so calibration error and
coverage are field-dev figures over those 8 classes. The 69 official tomato test
photos are sealed and held by P1.

### 3. Grad-CAM in-box fraction

Annotated leaf boxes for field-dev photos are in
[`../for_p3/field_boxes.csv`](../for_p3/field_boxes.csv) (`split=field_dev`,
454 boxes). Boxes are pixel coordinates of the EXIF-corrected image. Upsample
the 7×7 map to that frame, after loading with
`ImageOps.exif_transpose(Image.open(path)).convert("RGB")`, before measuring the
share of heat inside the boxes. In the crop arm, map the box back from crop
coordinates to the full photo first.

## Known issues and P1's decision

**Keep every image, label and split; record unreliable masks only.** No mask
was edited by hand and no image was excluded from the diagnostic. Whether to
also report the score without flagged images is P4's choice, to be committed
before testing.

### Flagged masks (`background_flags.csv`)

The script flags images automatically; examples of each flag were checked on a
contact sheet on November 7, 2026.

| Flag | Images | Classes (split) | What the background image shows |
|---|---:|---|---|
| `dark_background_in_color` | 151 | Late blight only (91 train, 20 val, 38 test, 2 excluded) | The upstream color photo already has a black background, so the result is almost entirely black. The blackness is itself a Late-blight cue. |
| `mask_covers_most_of_image` | 18 | Late blight 10, Leaf mold 3, YLCV 3, Bacterial spot 2 | Segmentation kept the whole frame; the result is entirely black. |
| `small_mask` | 4 | Septoria 2, YLCV 2 | Septoria (2): segmentation failed and most of the leaf remains visible. YLCV (2): genuinely tiny leaves; the mask is correct. |
| skipped | 1 | Spider mites (test) | Size mismatch, see below. No image written. |

One image carries two flags, so the counts sum to 174 for 173 rows.

### Problems the flags do not catch

- **Removed disease tissue survives.** Where segmentation cut necrotic tissue out
  of the leaf, that tissue stays visible in the background image, carrying a
  disease cue into what should be background only. Confirmed for Early blight 08
  (`bc894aa4-76ca-427e-a964-e86236fc0217___RS_Erly.B 7526`) and Late blight 04 (`0879b927-2226-455f-9eac-10f5e1f36fdd___RS_Late.B 5331`)
  from the P2 sample; the rate across the dataset is not measured.
- **Retained background is blacked out.** Where segmentation kept background
  beside the leaf (mainly Leaf mold, e.g. `f3ef6606-c66b-4fa0-a542-f09b78b6c3e0___Crnl_L.Mold 9120`), that
  background is removed with the leaf, so less background remains to measure.
- **The leaf silhouette remains.** The black shape shows the leaf's outline,
  size and position. The diagnostic therefore measures background plus
  silhouette, not background alone; Noyan (2022) used 8 background pixels only.
- **Dimension mismatch.** Sample `0db2da38-8650-461a-a785-814cc442f44d___Com.G_SpM_FL 1378` (test) has a
  256×256 color image and a 335×512 segmented counterpart named without the uuid
  prefix. Its mask cannot be aligned by resizing, so it is skipped.
- **Inherited split issues.** The 122 reviewed duplicate pairs (51 crossing
  train/val/test) and the 5 excluded photos documented in
  [for_p2](../for_p2/README.md#known-issues-and-p1s-decision) apply here too.
  The diagnostic score is not a leakage-free estimate.

## Scripts

Run from this directory. `uv run` supplies Pillow, NumPy and SciPy.

```bash
uv run make_background_only.py
```

This overwrites only `background_only/`, `background_masks.csv` and
`background_flags.csv`. A run with the default settings reproduces the shipped
`background_flags.csv`. Options: `--threshold`, `--dilate`, and the flag limits
`--low` (0.05), `--high` (0.85) and `--dark` (40).

The source dataset is [PlantVillage](https://github.com/spMohanty/PlantVillage-Dataset)
(segmented version). This handoff covers its tomato subset only.
