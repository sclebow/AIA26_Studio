"""
Crop planfinder viewport screenshots to their content bounds.

Reads from:  Planfinder_Dataset/pf_screenshots/
Writes to:   Planfinder_Dataset/pf_screenshots_cropped/

Logic: detect non-white pixels (threshold < 240), crop to their bounding box
plus 28px padding on each side.

Run from repo root with venv active:
    .venv/Scripts/python.exe team_06/layout_inputs/crop_pf_screenshots.py
"""

import os
import shutil
import numpy as np
from pathlib import Path
from PIL import Image

PADDING = 28
THRESHOLD = 240

script_dir = Path(__file__).resolve().parent
src_dir = script_dir / "Planfinder_Dataset" / "pf_screenshots"
dst_dir = script_dir / "Planfinder_Dataset" / "pf_screenshots_cropped"
dst_dir.mkdir(parents=True, exist_ok=True)

files = sorted(f for f in os.listdir(src_dir) if f.endswith(".png"))
print(f"Cropping {len(files)} screenshots...")

for fname in files:
    img = Image.open(src_dir / fname).convert("RGB")
    arr = np.array(img)
    W, H = img.size

    mask = np.any(arr < THRESHOLD, axis=2)
    rows = np.where(mask.any(axis=1))[0]
    cols = np.where(mask.any(axis=0))[0]

    if len(rows) == 0 or len(cols) == 0:
        shutil.copy(src_dir / fname, dst_dir / fname)
        continue

    left   = max(0, cols[0]  - PADDING)
    top    = max(0, rows[0]  - PADDING)
    right  = min(W, cols[-1] + PADDING + 1)
    bottom = min(H, rows[-1] + PADDING + 1)

    cropped = img.crop((left, top, right, bottom))
    cropped.save(dst_dir / fname)

print(f"Done. Cropped images saved to: {dst_dir}")
