"""
Delete layout files where the internal layoutId does not match the filename.
These are empty layouts saved before the Script 5 empty-layout guard existed.

Also deletes matching screenshots and cropped screenshots if they exist.

Run from repo root:
    .venv/Scripts/python.exe team_06/python/utils/pf_layouts/delete_mismatched_layouts.py
"""

import json
from pathlib import Path

DATASET = Path(__file__).resolve().parents[3] / "layout_inputs" / "Planfinder_Dataset"
JSON_DIR    = DATASET / "pf_jsons"
PNG_DIR     = DATASET / "pf_screenshots"
CROP_DIR    = DATASET / "pf_screenshots_cropped"

deleted_json = 0
deleted_png  = 0
deleted_crop = 0

for f in sorted(JSON_DIR.glob("*.json")):
    data = json.loads(f.read_text(encoding="utf-8"))
    internal_id = data.get("layoutId", "")
    if internal_id == f.stem:
        continue  # consistent — keep

    # Mismatch: delete JSON
    print(f"DELETE  {f.name}  (internal: {internal_id})")
    f.unlink()
    deleted_json += 1

    # Delete matching screenshot (same filename stem)
    png = PNG_DIR / f"{f.stem}.png"
    if png.exists():
        png.unlink()
        deleted_png += 1

    crop = CROP_DIR / f"{f.stem}.png"
    if crop.exists():
        crop.unlink()
        deleted_crop += 1

print(f"\nDeleted: {deleted_json} JSONs, {deleted_png} screenshots, {deleted_crop} cropped screenshots")
print(f"Remaining JSONs: {len(list(JSON_DIR.glob('*.json')))}")
