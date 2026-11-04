# P1 → P4

This is a partial handoff. The existing 18,160 PlantVillage tomato `segmented/`
images are available locally only and are excluded from Git. Cloning the
repository will not download them; a shared download link is still pending.
No images were repaired or newly excluded.

Use the shared split CSVs in [for_p2](../for_p2/README.md) to pair the versions:

- Color image: `for_p2 / row['color_path']`.
- Segmented image: `for_p4 / row['segmented_path']`.
- The CSV row supplies the sample ID, label, group, and current split.

The [known-issue report](../for_p2/README.md#known-issues-and-p1s-decision) records
incorrect segmentation, retained background, already-black-background color
images, confirmed duplicates, and the dimension mismatch. Detailed duplicate and
size records are in [duplicates.csv](../for_p2/duplicates.csv) and
[size_issues.csv](../for_p2/size_issues.csv).

Segmented images are not reliable ground-truth masks without further review.
The background-diagnostic method and the remaining P4 handoff are still pending.
