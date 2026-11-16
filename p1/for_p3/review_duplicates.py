#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = ["pillow>=10,<14"]
# ///
"""Build one HTML page that shows every near-duplicate candidate pair side by side.

Reads duplicates.csv and the original PlantDoc GitHub zip (the pairs include
test and removed photos, which the Drive mirror does not contain). Writes a
self-contained duplicate_review.html. Does not change data, labels or splits;
decisions made on the page stay in the browser until copied out.
"""

import argparse
import base64
import csv
import io
import json
import zipfile
from pathlib import Path

from PIL import Image, ImageOps

HERE = Path(__file__).resolve().parent
PAGE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>PlantDoc duplicate review</title>
<style>
:root { --bg:#f6f5f1; --card:#fff; --ink:#1d1f1c; --muted:#676b63; --line:#deddd6; --accent:#2f6f4f;
  --same:#2f6f4f; --diff:#b3452c; --unsure:#8a6d1a; --badge:#ecebe4; }
@media (prefers-color-scheme: dark) {
  :root { --bg:#16181a; --card:#1f2225; --ink:#e9e8e3; --muted:#9a9d95; --line:#33373b; --accent:#6fbf95;
    --same:#6fbf95; --diff:#e58a70; --unsure:#d9b65a; --badge:#2a2e32; }
}
* { box-sizing:border-box; }
body { margin:0; background:var(--bg); color:var(--ink); font:14px/1.45 -apple-system, "Segoe UI", system-ui, sans-serif; }
header { position:sticky; top:0; z-index:5; background:var(--bg); border-bottom:1px solid var(--line); padding:10px 16px; }
h1 { font-size:17px; margin:0 0 2px; }
.sub { color:var(--muted); margin:0 0 8px; max-width:95ch; }
.bar { display:flex; flex-wrap:wrap; gap:6px; align-items:center; }
.chip, .act { font:inherit; border:1px solid var(--line); background:var(--card); color:var(--ink); border-radius:999px;
  padding:4px 11px; cursor:pointer; }
.chip[aria-pressed="true"] { background:var(--ink); color:var(--bg); border-color:var(--ink); }
.progress { margin-left:auto; color:var(--muted); font-variant-numeric:tabular-nums; }
main { padding:14px 16px 40px; display:grid; gap:14px; grid-template-columns:repeat(auto-fill, minmax(min(100%, 560px), 1fr)); }
.card { background:var(--card); border:1px solid var(--line); border-radius:10px; padding:10px; border-left:5px solid var(--line); }
.card[data-decision="same"] { border-left-color:var(--same); }
.card[data-decision="different"] { border-left-color:var(--diff); }
.card[data-decision="unsure"] { border-left-color:var(--unsure); }
.head { display:flex; flex-wrap:wrap; gap:6px; align-items:center; margin-bottom:8px; }
.num { font-weight:650; font-variant-numeric:tabular-nums; }
.badge { background:var(--badge); border-radius:4px; padding:1px 6px; font-size:12px; }
.badge.warn { color:var(--diff); font-weight:600; }
.dist { margin-left:auto; color:var(--muted); font-size:12px; }
.pair { display:grid; grid-template-columns:1fr 1fr; gap:8px; }
figure { margin:0; min-width:0; }
.frame { aspect-ratio:1 / 1; background:var(--badge); border-radius:6px; overflow:hidden; display:flex; align-items:center; justify-content:center; }
.frame img { width:100%; height:100%; object-fit:contain; display:block; }
figcaption { margin-top:5px; font-size:12px; overflow-wrap:anywhere; }
.name { color:var(--muted); }
.cls { font-weight:600; }
.where { color:var(--muted); }
.decide { display:flex; flex-wrap:wrap; gap:6px; margin-top:9px; align-items:center; }
.decide button { font:inherit; border:1px solid var(--line); background:var(--card); color:var(--ink); border-radius:6px; padding:5px 12px; cursor:pointer; }
.decide button[aria-pressed="true"][data-v="same"] { background:var(--same); border-color:var(--same); color:var(--bg); }
.decide button[aria-pressed="true"][data-v="different"] { background:var(--diff); border-color:var(--diff); color:var(--bg); }
.decide button[aria-pressed="true"][data-v="unsure"] { background:var(--unsure); border-color:var(--unsure); color:var(--bg); }
.decide input { flex:1; min-width:120px; font:inherit; padding:5px 8px; border:1px solid var(--line); border-radius:6px; background:var(--card); color:var(--ink); }
footer { padding:0 16px 40px; }
textarea { width:100%; height:220px; font:12px/1.4 ui-monospace, Menlo, Consolas, monospace; background:var(--card); color:var(--ink);
  border:1px solid var(--line); border-radius:8px; padding:8px; }
button:focus-visible, input:focus-visible { outline:2px solid var(--accent); outline-offset:1px; }
</style>
</head>
<body>
<header>
  <h1>PlantDoc near-duplicate candidates</h1>
  <p class="sub">Each card is one pair from duplicates.csv. Point at either photo to see the other one in its place (move in and out to flicker).
  Mark each pair, then copy the result box at the bottom.</p>
  <div class="bar" id="filters"></div>
</header>
<main id="cards"></main>
<footer>
  <div class="bar" style="margin-bottom:8px">
    <strong>Result</strong>
    <button class="act" id="copy">Copy</button>
    <button class="act" id="allsame">Mark all undecided as same</button>
    <button class="act" id="reset">Clear all</button>
    <span class="progress" id="copied"></span>
  </div>
  <textarea id="out" readonly></textarea>
</footer>
<script>
const PAIRS = __PAIRS__;
const IMG = __IMAGES__;
const KEY = "plantdoc-duplicate-review-v1";
let state = {};
try { state = JSON.parse(localStorage.getItem(KEY) || "{}"); } catch (e) {}
const save = () => { try { localStorage.setItem(KEY, JSON.stringify(state)); } catch (e) {} };
const FILTERS = [
  ["all", "All", p => true],
  ["test", "Train \\u2194 test", p => p.cross],
  ["labels", "Labels differ", p => p.labelsDiffer],
  ["tomato", "Tomato", p => p.tomato],
  ["todo", "Undecided", p => !(state[p.row] || {}).d],
];
let active = "all";
const el = (tag, cls, text) => { const n = document.createElement(tag); if (cls) n.className = cls; if (text != null) n.textContent = text; return n; };

function figure(p, side) {
  const me = p[side], other = p[side === "a" ? "b" : "a"];
  const fig = el("figure");
  const frame = el("div", "frame");
  const img = el("img");
  img.src = IMG[me.img]; img.alt = side.toUpperCase() + ": " + me.id; img.loading = "lazy";
  frame.addEventListener("mouseenter", () => { img.src = IMG[other.img]; });
  frame.addEventListener("mouseleave", () => { img.src = IMG[me.img]; });
  frame.appendChild(img);
  const cap = el("figcaption");
  cap.appendChild(el("div", "cls", side.toUpperCase() + " \\u00b7 " + (me.classes || "no label")));
  cap.appendChild(el("div", "where", me.where + " \\u00b7 " + me.size));
  cap.appendChild(el("div", "name", me.id));
  fig.append(frame, cap);
  return fig;
}

function render() {
  const main = document.getElementById("cards");
  main.textContent = "";
  const test = FILTERS.find(f => f[0] === active)[2];
  for (const p of PAIRS.filter(test)) {
    const s = state[p.row] || {};
    const card = el("section", "card");
    if (s.d) card.dataset.decision = s.d;
    const head = el("div", "head");
    head.appendChild(el("span", "num", "Row " + p.row));
    if (p.cross) head.appendChild(el("span", "badge warn", "train \\u2194 test"));
    if (p.labelsDiffer) head.appendChild(el("span", "badge warn", "labels differ"));
    if (p.tomato) head.appendChild(el("span", "badge", "tomato"));
    head.appendChild(el("span", "dist", "pHash " + p.phash + " \\u00b7 dHash " + p.dhash));
    const pair = el("div", "pair");
    pair.append(figure(p, "a"), figure(p, "b"));
    const decide = el("div", "decide");
    for (const [v, label] of [["same", "Same photo"], ["different", "Different"], ["unsure", "Unsure"]]) {
      const b = el("button", null, label);
      b.dataset.v = v; b.setAttribute("aria-pressed", String(s.d === v));
      b.addEventListener("click", () => {
        const cur = state[p.row] || {};
        state[p.row] = { ...cur, d: cur.d === v ? "" : v };
        save(); render();
      });
      decide.appendChild(b);
    }
    const note = el("input");
    note.placeholder = "Note (optional)"; note.value = s.n || "";
    note.addEventListener("input", () => { state[p.row] = { ...(state[p.row] || {}), n: note.value }; save(); output(); });
    decide.appendChild(note);
    card.append(head, pair, decide);
    main.appendChild(card);
  }
  filters(); output();
}

function filters() {
  const bar = document.getElementById("filters");
  bar.textContent = "";
  for (const [id, label, test] of FILTERS) {
    const b = el("button", "chip", label + " " + PAIRS.filter(test).length);
    b.setAttribute("aria-pressed", String(active === id));
    b.addEventListener("click", () => { active = id; render(); window.scrollTo(0, 0); });
    bar.appendChild(b);
  }
  const done = PAIRS.filter(p => (state[p.row] || {}).d).length;
  bar.appendChild(el("span", "progress", done + " / " + PAIRS.length + " decided"));
}

function output() {
  const count = v => PAIRS.filter(p => ((state[p.row] || {}).d || "") === v).length;
  const lines = ["# PlantDoc duplicate review: same " + count("same") + ", different " + count("different") +
    ", unsure " + count("unsure") + ", undecided " + count(""), "row\\tdecision\\ta_image_id\\tb_image_id\\tnote"];
  for (const p of PAIRS) {
    const s = state[p.row] || {};
    lines.push([p.row, s.d || "undecided", p.a.id, p.b.id, s.n || ""].join("\\t"));
  }
  document.getElementById("out").value = lines.join("\\n");
}

document.getElementById("copy").addEventListener("click", async () => {
  const out = document.getElementById("out");
  let ok = false;
  try { await navigator.clipboard.writeText(out.value); ok = true; } catch (e) {
    out.focus(); out.select();
    try { ok = document.execCommand("copy"); } catch (e2) {}
  }
  document.getElementById("copied").textContent = ok ? "Copied" : "Select the text and copy it manually";
});
document.getElementById("allsame").addEventListener("click", () => {
  for (const p of PAIRS) if (!(state[p.row] || {}).d) state[p.row] = { ...(state[p.row] || {}), d: "same" };
  save(); render();
});
document.getElementById("reset").addEventListener("click", () => {
  if (confirm("Clear every decision and note?")) { state = {}; save(); render(); }
});
render();
</script>
</body>
</html>
"""


def read_csv(path):
    with path.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def thumbnail(data, size):
    with Image.open(io.BytesIO(data)) as im:
        im = ImageOps.exif_transpose(im).convert("RGB")
        full = f"{im.width}×{im.height}"
        im.thumbnail((size, size))
        buffer = io.BytesIO()
        im.save(buffer, "JPEG", quality=82)
    return "data:image/jpeg;base64," + base64.b64encode(buffer.getvalue()).decode("ascii"), full


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", required=True, type=Path, help="Original PlantDoc GitHub zip")
    parser.add_argument("--dataset", type=Path, default=HERE)
    parser.add_argument("--output", type=Path, default=HERE / "duplicate_review.html")
    parser.add_argument("--size", type=int, default=560, help="Longest thumbnail side in pixels")
    args = parser.parse_args()
    where = {}
    for row in read_csv(args.dataset / "localizer_train.csv"):
        where[row["image_id"]] = "localizer train"
    for row in read_csv(args.dataset / "field_train.csv"):
        where[row["image_id"]] = "field-train + localizer train"
    for row in read_csv(args.dataset / "field_dev.csv"):
        where[row["image_id"]] = "field-dev"
    for row in read_csv(args.dataset / "excluded.csv"):
        where[row["image_id"]] = "removed: " + row["exclusion_reason"].replace(";", ", ")
    archive = zipfile.ZipFile(args.archive)
    prefix = archive.namelist()[0].split("/")[0] + "/"
    folder = {"train": "TRAIN", "test": "TEST"}
    images, sizes, pairs = {}, {}, []

    def side(row, s):
        split, image_id, classes = row[f"{s}_plantdoc_split"], row[f"{s}_image_id"], row[f"{s}_classes"]
        key = f"{split}/{image_id}"
        if key not in images:
            images[key], sizes[key] = thumbnail(archive.read(f"{prefix}{folder[split]}/{image_id}"), args.size)
        if split == "test":
            status = "sealed tomato test" if classes.startswith("Tomato") else "PlantDoc test (not used)"
        else:
            status = where.get(image_id, "train, not used (near-duplicate of field-dev or unresolved boxes)")
        return {"id": image_id, "classes": classes.replace(";", " + "), "where": status, "size": sizes[key], "img": key}

    for number, row in enumerate(read_csv(args.dataset / "duplicates.csv"), 1):
        if row["kind"] != "near_candidate":
            continue
        pairs.append({
            "row": number, "a": side(row, "a"), "b": side(row, "b"),
            "cross": row["crosses_train_test"] == "True", "tomato": row["involves_tomato"] == "True",
            "labelsDiffer": row["a_classes"] != row["b_classes"],
            "phash": row["phash_distance"], "dhash": row["dhash_distance"],
        })
    embed = lambda value: json.dumps(value, ensure_ascii=False).replace("</", "<\\/")
    args.output.write_text(PAGE.replace("__PAIRS__", embed(pairs)).replace("__IMAGES__", embed(images)), encoding="utf-8")
    print(f"{len(pairs)} pairs, {len(images)} photos: {args.output}")


if __name__ == "__main__":
    main()
