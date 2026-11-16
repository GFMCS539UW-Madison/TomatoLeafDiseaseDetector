# P1 — Data and Evaluation

P1 prepares shared data, documents known issues, and evaluates the frozen models.

| Folder | Contents | Status |
|---|---|---|
| [for_p2](for_p2/README.md) | PlantVillage color images, split CSVs, three standalone scripts, and reviewed issue reports | Prepared; known duplicate and dimension issues retained and documented. PlantDoc field data is in for_p3. |
| [for_p3](for_p3/README.md) | PlantDoc images, localizer boxes, tomato field-train/field-dev split, class map, removal and annotation reports | Prepared; shared with P2 (field fine-tuning, crop arm) and P4 (calibration, Grad-CAM). Field test sealed by P1. |
| [for_p4](for_p4/README.md) | PlantVillage segmented images, background-only image script, flagged-mask report, pointers to shared splits | Prepared. |

The original datasets remain in the repository-root `ECE539_Tomato_Datasets/`
directory. Local images are excluded from Git by the root `.gitignore`.
