"""
Generate semantic descriptions for Planfinder layouts using PNG + JSON.

Reads:   Planfinder_Dataset/pf_jsons/*.json
         Planfinder_Dataset/pf_screenshots/*.png
Writes:  Planfinder_Dataset/pf_descriptions/{layoutId}.json  (one file per layout)

Usage (from repo root):
    ".venv/Scripts/python.exe" team_06/layout_inputs/generate_pf_descriptions.py

Skips layouts that already have a description — safe to re-run after crashes.
Delete pf_descriptions/ to regenerate everything from scratch.
"""

import json, time, os, io
from pathlib import Path
from dotenv import load_dotenv
from google import genai
from google.genai import types
from PIL import Image
import numpy as np

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
REPO_ROOT    = Path(__file__).resolve().parents[2]
DATASET_DIR  = Path(__file__).resolve().parent / "Planfinder_Dataset"
JSONS_DIR        = DATASET_DIR / "pf_jsons"
SCREENS_DIR      = DATASET_DIR / "pf_screenshots"
SCREENS_CROP_DIR = DATASET_DIR / "pf_screenshots_cropped"
OUTPUT_DIR       = DATASET_DIR / "pf_descriptions"
OUTPUT_DIR.mkdir(exist_ok=True)
SCREENS_CROP_DIR.mkdir(exist_ok=True)

# ---------------------------------------------------------------------------
# API client
# ---------------------------------------------------------------------------
load_dotenv(REPO_ROOT / ".env")
API_KEY = os.environ.get("GOOGLE_API_KEY")
if not API_KEY:
    raise ValueError("GOOGLE_API_KEY not found in repo root .env")
client = genai.Client(api_key=API_KEY)
MODEL  = os.environ.get("GOOGLE_MODEL", "gemini-2.5-flash-lite")

# ---------------------------------------------------------------------------
# Step 1 — deterministic extraction from JSON (no LLM, no cost)
# ---------------------------------------------------------------------------
def extract_context(layout: dict) -> dict:
    rooms    = layout.get("rooms", [])
    doors    = layout.get("doors", [])
    programs = [r["attributes"]["program"] for r in rooms]

    bed_ids   = {r["id"] for r in rooms if r["attributes"]["program"] == "bed"}
    bath_ids  = {r["id"] for r in rooms if r["attributes"]["program"] == "bath"}
    extra_ids = {r["id"] for r in rooms if r["attributes"]["program"] == "extra"}
    living_ids = {r["id"] for r in rooms if r["attributes"]["program"] == "living"}

    bed_areas = sorted(
        [r["attributes"]["area"] for r in rooms if r["attributes"]["program"] == "bed"],
        reverse=True
    )
    n_bed     = len(bed_areas)
    n_bath    = programs.count("bath")
    open_plan = "kitchen" not in programs
    has_store = bool(extra_ids)

    layout_id = layout.get("layoutId", "")
    try:
        de = int(layout_id.split("_de")[1].split("_")[0])
    except (IndexError, ValueError):
        de = -1
    entry_side = {0: "bottom", 1: "right", 2: "top", 3: "left"}.get(de, "unknown")
    n_facades  = len(layout.get("facades", []))

    # En-suite: any door directly connecting a bedroom to a bathroom
    ensuite = any(
        set(d["attributes"]["connectsRooms"]) & bed_ids and
        set(d["attributes"]["connectsRooms"]) & bath_ids
        for d in doors
    )

    # Storage in kitchen zone: any extra room has a door directly to the living room
    storage_kitchen_zone = any(
        set(d["attributes"]["connectsRooms"]) & extra_ids and
        set(d["attributes"]["connectsRooms"]) & living_ids
        for d in doors
    )

    # Door between corridor/extra and living room (separates private zone from living)
    corridor_door_to_living = any(
        set(d["attributes"]["connectsRooms"]) & extra_ids and
        set(d["attributes"]["connectsRooms"]) & living_ids
        for d in doors
    )

    # Facade sides — which walls have windows
    def _facade_sides(layout):
        outline = layout.get("outline", [])
        if not outline:
            return []
        xs = [p[0] for p in outline]
        ys = [p[1] for p in outline]
        mid_x = (min(xs) + max(xs)) / 2
        mid_y = (min(ys) + max(ys)) / 2
        sides = []
        for f in layout.get("facades", []):
            geom = f.get("geometry", [])
            if len(geom) < 2:
                continue
            p1, p2 = geom[0], geom[-1]
            if abs(p2[0] - p1[0]) > abs(p2[1] - p1[1]):  # horizontal
                y_avg = (p1[1] + p2[1]) / 2
                sides.append("top" if y_avg > mid_y else "bottom")
            else:  # vertical
                x_avg = (p1[0] + p2[0]) / 2
                sides.append("right" if x_avg > mid_x else "left")
        return list(dict.fromkeys(sides))

    facade_sides = _facade_sides(layout)
    if n_facades == 1:
        aspect = "single-aspect"
    elif n_facades == 2:
        aspect = "double-aspect"
    elif n_facades >= 3:
        aspect = "corner-aspect"
    else:
        aspect = "unknown aspect"

    return {
        "space_type":                "studio" if n_bed == 0 else f"{n_bed}-bedroom",
        "open_plan":                 open_plan,
        "bedroom_count":             n_bed,
        "secondary_count":           max(0, n_bed - 1),
        "bathroom_count":            n_bath,
        "has_storage_room":          has_store,
        "entry_side":                entry_side,
        "double_aspect":             n_facades >= 2,
        "ensuite_from_json":         ensuite,
        "storage_kitchen_zone":      storage_kitchen_zone,
        "corridor_door_to_living":   corridor_door_to_living,
        "facade_sides":              facade_sides,
        "aspect":                    aspect,
    }

# ---------------------------------------------------------------------------
# Crop PNG to floor plan bounding box before sending to LLM
# Finds all non-background pixels (red lines on grey) and crops to their extent
# ---------------------------------------------------------------------------
def crop_to_plan(png_path: Path, padding: int = 30) -> bytes:
    img = Image.open(png_path).convert("RGB")
    arr = np.array(img)
    r, g, b = arr[:,:,0].astype(int), arr[:,:,1].astype(int), arr[:,:,2].astype(int)

    # Non-background: pixels where channels differ significantly (red lines)
    # or significantly darker than the grey background (~224,224,224)
    mask = (np.abs(r - g) > 15) | (np.abs(r - b) > 15) | (r < 180)

    rows = np.where(mask.any(axis=1))[0]
    cols = np.where(mask.any(axis=0))[0]

    if len(rows) == 0 or len(cols) == 0:
        return png_path.read_bytes()  # fallback: return full image

    top    = max(0, int(rows[0])  - padding)
    bottom = min(img.height, int(rows[-1]) + padding)
    left   = max(0, int(cols[0])  - padding)
    right  = min(img.width,  int(cols[-1]) + padding)

    cropped = img.crop((left, top, right, bottom))
    buf = io.BytesIO()
    cropped.save(buf, format="PNG")
    return buf.getvalue()

# ---------------------------------------------------------------------------
# Step 2 — vision LLM: fixed structured questionnaire, returns JSON only
# ---------------------------------------------------------------------------
QUESTIONNAIRE = """\
You are reading an architectural floor plan (line drawing, red lines on grey background).
Answer the questions below based only on what is visible in the image.
Return a single valid JSON object with exactly these keys. No prose, no explanation.

Context (from JSON data): {context}

{{
  "kitchen_island":                 "yes / no",
  "hob_location":                   "island / wall / unclear",
  "sink_location":                  "island / wall / unclear",
  "cook_faces_room":                "yes / no / partial",
  "living_arrangement":             "linear kitchen-dining-living / split seating-kitchen-dining / L-shaped / kitchen-dominant / living-dominant / corner / other",
  "dining_table_visible":           "yes / no",
  "dining_chair_count":             "<number or unclear>",
  "tv_visible":                     "yes / no",
  "tv_wall_relative_to_entry":      "same wall as entry / opposite wall to entry / left of entry / right of entry / unclear / na",
  "cook_can_see_tv":                "yes / no / unclear / na",
  "diners_face_tv":                 "yes / no / unclear / na",
  "walk_in_wardrobe":               "yes / no",
  "walk_in_wardrobe_type":          "open two facing units no door / enclosed with door / none",
  "bathrooms_with_bathtub":         "<number>",
  "bathrooms_with_shower_only":     "<number>",
  "wc_only_rooms":                  "<number>",
  "desk_secondary_1":               "yes / no / na",
  "desk_secondary_2":               "yes / no / na",
  "entry_storage_visible":          "yes / no",
  "entry_proximity_to_kitchen":     "immediate / short corridor / long corridor",
  "entry_proximity_to_living":      "immediate / short corridor / long corridor",
  "sleeping_area_separation":       "none / partial partition / alcove / fully open / na",
  "bed_type_studio":                "single / double / sofa bed / unclear / na",
  "kitchen_near_window":            "yes / no / unclear"
}}
"""

def get_cropped_png(png_path: Path) -> bytes:
    """Return cropped bytes, generating and caching the cropped file if needed."""
    cropped_path = SCREENS_CROP_DIR / png_path.name
    if not cropped_path.exists():
        img_bytes = crop_to_plan(png_path)
        cropped_path.write_bytes(img_bytes)
    return cropped_path.read_bytes()

def call_vision_llm(png_path: Path, context: dict) -> dict:
    img_data = get_cropped_png(png_path)  # use cropped version, originals untouched
    entry    = context.get("entry_side", "unknown")
    prompt   = (
        QUESTIONNAIRE.replace("{context}", json.dumps(context))
        + f"\n\nSpatial reference: the entry door is on the {entry} side of the image. "
          f"Use this to determine which wall the TV is on, cook orientation, etc."
    )

    response = client.models.generate_content(
        model=MODEL,
        contents=[
            types.Part.from_bytes(data=img_data, mime_type="image/png"),
            types.Part.from_text(text=prompt),
        ]
    )
    raw = response.text.strip()
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
    return json.loads(raw.strip())

# ---------------------------------------------------------------------------
# Step 3 — assemble description from context + vision answers
# ---------------------------------------------------------------------------
def assemble(ctx: dict, vis: dict, layout_id: str) -> dict:
    parts        = []
    not_suitable = []
    cook_faces   = vis.get("cook_faces_room", "")
    desk_count   = 0

    # --- Room list opening ---
    n_bathtub_pre = int(vis.get("bathrooms_with_bathtub", 0) or 0)
    n_shower_pre  = int(vis.get("bathrooms_with_shower_only", 0) or 0)
    n_wc_pre      = int(vis.get("wc_only_rooms", 0) or 0)

    rl = []
    if ctx["space_type"] == "studio":
        rl.append("Studio apartment")
    else:
        n_s = ctx["secondary_count"]
        bed_label = "1 master suite" if ctx["ensuite_from_json"] else "1 double bedroom"
        rl.append(bed_label)
        if n_s == 1:
            rl.append("1 single bedroom")
        elif n_s > 1:
            rl.append(f"{n_s} single bedrooms")
    bath_rl = []
    if n_bathtub_pre:
        bath_rl.append(f"{n_bathtub_pre} bathroom{'s' if n_bathtub_pre > 1 else ''} with bathtub")
    if n_shower_pre:
        bath_rl.append(f"{n_shower_pre} shower bathroom{'s' if n_shower_pre > 1 else ''}")
    if n_wc_pre:
        bath_rl.append(f"{n_wc_pre} WC")
    if bath_rl:
        rl.append(", ".join(bath_rl))
    rl.append("open plan living-kitchen-dining" if ctx["open_plan"] else "separate kitchen and living")
    if ctx["has_storage_room"]:
        rl.append("1 storage room")
    parts.append(", ".join(rl) + ".")

    # --- Aspect and natural light ---
    aspect    = ctx.get("aspect", "")
    f_sides   = ctx.get("facade_sides", [])
    sides_str = " and ".join(f_sides) if f_sides else "unknown"
    parts.append(f"{aspect.capitalize()} apartment — windows on {sides_str} facade(s).")
    kitchen_lit = vis.get("kitchen_near_window", "unclear")
    if kitchen_lit == "yes":
        parts.append("Kitchen is adjacent to a window — well-lit cooking position.")
    elif kitchen_lit == "no":
        parts.append("Kitchen is on an interior wall away from windows — less natural light at the cooking position.")

    # Bedroom / studio classification
    if ctx["space_type"] == "studio":
        sep = vis.get("sleeping_area_separation", "unclear")
        bed = vis.get("bed_type_studio", "unclear")
        parts.append(
            f"Studio apartment. Sleeping area: {bed} bed. "
            f"Separation from living area: {sep}."
        )
        not_suitable += ["families with children",
                         "household requiring separate rooms for different functions simultaneously"]
    else:
        n_single = ctx["secondary_count"]
        wc_label = "with walk-in wardrobe" if vis.get("walk_in_wardrobe") == "yes" else "no walk-in wardrobe"
        # Suite only if en-suite confirmed from JSON (bedroom door directly to bathroom)
        if ctx["ensuite_from_json"]:
            bed_label = f"1 master suite (en-suite bathroom, {wc_label})"
        else:
            bed_label = f"1 double bedroom ({wc_label}, no en-suite)"
        parts.append(
            f"{bed_label}, {n_single} single bedroom(s). "
            f"Single bedrooms can each function as bedroom, home office, hobby room or guest room."
        )

    # Walk-in wardrobe detail
    if vis.get("walk_in_wardrobe") == "yes":
        parts.append(f"Walk-in wardrobe: {vis.get('walk_in_wardrobe_type', 'open wardrobe area')}.")

    # Kitchen
    island = vis.get("kitchen_island") == "yes"
    if island:
        hob  = vis.get("hob_location",  "unclear")
        sink = vis.get("sink_location", "unclear")
        parts.append(f"Kitchen island present — hob on {hob}, sink on {sink}.")
    else:
        parts.append("No kitchen island — single countertop kitchen.")

    if cook_faces == "yes":
        parts.append(
            "Cook faces the dining and living area directly — "
            "suited to cooking while entertaining or supervising children."
        )
    elif cook_faces == "no":
        parts.append("Cook faces the wall, back to the living and dining area.")
    elif cook_faces == "partial":
        parts.append("Cook partially faces the living area depending on position at counter.")

    if ctx["open_plan"]:
        parts.append("No wall separates kitchen from dining and living — fully open plan.")
    else:
        parts.append("Kitchen is a separate enclosed room.")
        not_suitable.append("open plan preference")

    # Living arrangement
    arr = vis.get("living_arrangement", "")
    if arr:
        parts.append(f"Living area arrangement: {arr}.")

    # Dining table
    if vis.get("dining_table_visible") == "yes":
        chairs = vis.get("dining_chair_count", "unclear")
        parts.append(f"Dining table visible, approximately {chairs} seats.")

    # TV
    if vis.get("tv_visible") == "yes":
        tv_wall  = vis.get("tv_wall_relative_to_entry", "unclear")
        see_tv   = vis.get("cook_can_see_tv", "unclear")
        face_tv  = vis.get("diners_face_tv", "unclear")
        see_str  = "can" if see_tv  == "yes" else ("cannot" if see_tv  == "no" else "may")
        face_str = "face" if face_tv == "yes" else ("do not face" if face_tv == "no" else "unclear if facing")
        parts.append(
            f"TV on wall {tv_wall}. "
            f"Cook {see_str} see TV from cooking position. "
            f"Diners {face_str} the TV."
        )

    # Bathrooms — per type counts
    n_bathtub = int(vis.get("bathrooms_with_bathtub", 0) or 0)
    n_shower  = int(vis.get("bathrooms_with_shower_only", 0) or 0)
    n_wc      = int(vis.get("wc_only_rooms", 0) or 0)
    bath_notes = []
    if n_bathtub:
        bath_notes.append(f"{n_bathtub} bathroom(s) with bathtub")
    if n_shower:
        bath_notes.append(f"{n_shower} shower-only bathroom(s)")
    if n_wc:
        bath_notes.append(f"{n_wc} WC-only room(s) (toilet, no shower or bath)")
    if bath_notes:
        parts.append("Bathroom config: " + "; ".join(bath_notes) + ".")

    n_full_bath = n_bathtub + n_shower
    if n_full_bath >= 2 or (n_full_bath >= 1 and n_wc >= 1):
        parts.append("Parallel morning routines possible — separate shower and WC available.")
    elif n_full_bath == 1 and n_wc == 0:
        parts.append("Single bathroom — sequential morning routine.")

    # Largest bedroom position
    if ctx["space_type"] != "studio" and ctx["bedroom_count"] >= 1:
        prox_k = vis.get("entry_proximity_to_kitchen", "")
        suite_label = "master suite" if ctx["ensuite_from_json"] else "largest bedroom"
        if prox_k == "long corridor":
            parts.append(
                f"{suite_label.capitalize()} at far end of apartment from living area — "
                "maximum privacy and acoustic separation from household activity. "
                "Path to kitchen passes through full corridor length."
            )
        elif prox_k == "immediate":
            parts.append(
                f"{suite_label.capitalize()} close to entry and kitchen — "
                "convenient morning access, less acoustic separation from activity."
            )
        else:
            parts.append(f"{suite_label.capitalize()} accessed via corridor.")

    # Secondary bedrooms + configuration matrix
    n_single = ctx["secondary_count"]
    if n_single >= 1:
        d1 = vis.get("desk_secondary_1", "no")
        d2 = vis.get("desk_secondary_2", "no") if n_single >= 2 else "na"
        desk_count = sum(1 for d in [d1, d2] if d == "yes")
        parts.append(
            f"{desk_count} of {n_single} single bedroom(s) have a desk visible in plan. "
            f"{'Each single bedroom is' if n_single > 1 else 'The single bedroom is'} "
            f"large enough to accommodate a bunk bed for two children."
        )
        configs = ["(1) all as children's bedrooms"]
        if n_single >= 2:
            configs.append("(2) one children's bedroom and one home office or hobby room")
        configs.append(f"({'3' if n_single >= 2 else '2'}) all as home offices or hobby rooms")
        configs.append(f"({'4' if n_single >= 2 else '3'}) one or both as guest rooms")
        configs.append(f"({'5' if n_single >= 2 else '4'}) bunk bed arrangement extending household capacity")
        parts.append("Possible configurations — mutually exclusive: " + "; ".join(configs) + ".")
        if n_single >= 2:
            parts.append(
                "Cannot simultaneously provide two separate children's bedrooms and a dedicated home office "
                "without a bunk bed in one bedroom."
            )
            not_suitable.append(
                "household requiring two children's bedrooms and a dedicated home office simultaneously "
                "without bunk bed arrangement"
            )

    # Storage — zone-aware
    if ctx["has_storage_room"]:
        if ctx["storage_kitchen_zone"]:
            parts.append(
                "Storage room adjacent to kitchen — "
                "usable as kitchen pantry, laundry room or general storage."
            )
        else:
            parts.append(
                "Storage room in entry or private zone, not adjacent to kitchen — "
                "suitable for coats, shoes, bikes, laundry or utility storage, not as kitchen pantry."
            )
    if vis.get("entry_storage_visible") == "yes":
        parts.append("Entry area has space for coat and shoe storage.")

    # Entry proximity
    prox_k = vis.get("entry_proximity_to_kitchen", "")
    prox_l = vis.get("entry_proximity_to_living",  "")
    if prox_k or prox_l:
        parts.append(
            f"From entry: kitchen is {prox_k or 'unclear'}, "
            f"living area is {prox_l or 'unclear'}."
        )

    # Entry-to-living door (from JSON)
    if ctx["corridor_door_to_living"]:
        parts.append("Door separates entry corridor from living area.")
    else:
        parts.append(
            "No door between entry and living/kitchen — "
            "relevant where local regulations require separation."
        )
        not_suitable.append("jurisdictions requiring door separation between entry and kitchen")

    # Household fit
    fit = []
    if ctx["bedroom_count"] >= 3:
        fit.append("families with one or two children")
    elif ctx["bedroom_count"] == 2:
        fit.append("couples needing a spare room")
    elif ctx["bedroom_count"] <= 1:
        fit.append("singles or couples")
    if desk_count >= 1:
        fit.append("people working from home in a dedicated room")
    if cook_faces == "yes":
        fit.append("households prioritising communal cooking and dining")
    if n_full_bath >= 1 and n_wc >= 1:
        fit.append("households with parallel morning routines")
    if fit:
        parts.append("Suits: " + ", ".join(fit) + ".")

    # rooms_summary
    summary = []
    if ctx["bedroom_count"]:
        summary.append(f"{ctx['bedroom_count']} bedroom")
    if ctx["bathroom_count"]:
        summary.append(f"{ctx['bathroom_count']} bathroom")
    summary.append("1 living (open plan)" if ctx["open_plan"] else "1 living, 1 kitchen")
    if ctx["has_storage_room"]:
        summary.append("1 storage")

    return {
        "layoutId":         layout_id,
        "description":      " ".join(parts),
        "not_suitable_for": not_suitable,
        "rooms_summary":    ", ".join(summary),
    }

# ---------------------------------------------------------------------------
# Empty layout detection (same logic as GH serializer real_rooms check)
# ---------------------------------------------------------------------------
def is_empty_layout(layout: dict) -> bool:
    rooms = layout.get("rooms", [])
    real  = [r for r in rooms if r.get("attributes", {}).get("program", "") != "extra"]
    return len(real) == 0

def write_empty_marker(out_file: Path, layout_id: str) -> None:
    out_file.write_text(json.dumps({
        "layoutId":        layout_id,
        "description":     "empty",
        "not_suitable_for": ["all"],
        "rooms_summary":   "empty"
    }, indent=2), encoding="utf-8")

# ---------------------------------------------------------------------------
# Main batch loop
# ---------------------------------------------------------------------------
def main():
    json_files = sorted(JSONS_DIR.glob("*.json"))
    total = len(json_files)
    done = empty = skip_exists = skip_no_png = errors = 0

    print(f"Layouts:     {total} in {JSONS_DIR.name}")
    print(f"Screenshots: {SCREENS_DIR.name}")
    print(f"Output:      {OUTPUT_DIR.name}\n")

    for json_file in json_files:
        layout_id = json_file.stem
        png_file  = SCREENS_DIR / f"{layout_id}.png"
        out_file  = OUTPUT_DIR  / f"{layout_id}.json"

        if out_file.exists():
            skip_exists += 1
            continue

        layout = json.loads(json_file.read_text(encoding="utf-8"))

        # Empty layout — write marker, no API call
        if is_empty_layout(layout):
            write_empty_marker(out_file, layout_id)
            print(f"  EMPTY  {layout_id}")
            empty += 1
            continue

        if not png_file.exists():
            print(f"  SKIP (no PNG)  {layout_id}")
            skip_no_png += 1
            continue

        context = extract_context(layout)

        try:
            vision = call_vision_llm(png_file, context)
            result = assemble(context, vision, layout_id)
            out_file.write_text(json.dumps(result, indent=2), encoding="utf-8")
            print(f"  OK   {layout_id}")
            done += 1
            time.sleep(0.3)
        except Exception as e:
            print(f"  ERR  {layout_id}: {e}")
            errors += 1

    print(f"\nDone: {done} generated | {empty} empty | {skip_exists} already existed | "
          f"{skip_no_png} skipped (no PNG) | {errors} errors")

if __name__ == "__main__":
    import sys
    if "--regen" in sys.argv:
        # Reprocess only layouts that have a cropped PNG — overwrites existing descriptions
        targets = [p.stem for p in sorted(SCREENS_CROP_DIR.glob("*.png"))]
        print(f"Regenerating {len(targets)} layouts from pf_screenshots_cropped/")
        done = errors = 0
        for lid in targets:
            json_file = JSONS_DIR / f"{lid}.json"
            png_file  = SCREENS_CROP_DIR / f"{lid}.png"
            out_file  = OUTPUT_DIR / f"{lid}.json"
            if not json_file.exists():
                print(f"  SKIP (no JSON) {lid}"); continue
            layout = json.loads(json_file.read_text(encoding="utf-8"))
            if is_empty_layout(layout):
                write_empty_marker(out_file, lid)
                print(f"  EMPTY  {lid}"); continue
            context = extract_context(layout)
            try:
                vision = call_vision_llm(png_file, context)
                result = assemble(context, vision, lid)
                out_file.write_text(json.dumps(result, indent=2), encoding="utf-8")
                print(f"  OK   {lid}")
                done += 1
                time.sleep(0.3)
            except Exception as e:
                print(f"  ERR  {lid}: {e}")
                errors += 1
        print(f"\nDone: {done} regenerated | {errors} errors")
    elif "--test" in sys.argv:
        # Run on first layout that has a PNG but no description yet
        for jf in sorted(JSONS_DIR.glob("*.json")):
            lid = jf.stem
            if not (OUTPUT_DIR / f"{lid}.json").exists() and (SCREENS_DIR / f"{lid}.png").exists():
                layout  = json.loads(jf.read_text(encoding="utf-8"))
                if not is_empty_layout(layout):
                    print(f"Testing on: {lid}")
                    ctx    = extract_context(layout)
                    vis    = call_vision_llm(SCREENS_DIR / f"{lid}.png", ctx)
                    result = assemble(ctx, vis, lid)
                    print(json.dumps(result, indent=2))
                    break
    else:
        main()
