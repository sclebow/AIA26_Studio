"""
Generate semantic descriptions for Planfinder layouts using PNG + JSON.

Reads:   Planfinder_Dataset/pf_jsons/*.json
         Planfinder_Dataset/pf_screenshots/*.png
Writes:  Planfinder_Dataset/pf_descriptions/{layoutId}.json  (one file per layout)

Usage (from repo root):
    ".venv/Scripts/python.exe" team_06/layout_inputs/generate_pf_descriptions.py
    ".venv/Scripts/python.exe" team_06/layout_inputs/generate_pf_descriptions.py --regen
    ".venv/Scripts/python.exe" team_06/layout_inputs/generate_pf_descriptions.py --test

Skips layouts that already have a description — safe to re-run after crashes.
Delete pf_descriptions/ to regenerate everything from scratch.
"""

import json, time, os, io, base64, ssl
from pathlib import Path
from dotenv import load_dotenv
import httpx
import anthropic
from PIL import Image
import numpy as np

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
_SCRIPT_DIR  = Path(__file__).resolve().parent
REPO_ROOT    = _SCRIPT_DIR.parents[3]
DATASET_DIR  = _SCRIPT_DIR.parents[2] / "layout_inputs" / "Planfinder_Dataset"
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
API_KEY = os.environ.get("ANTHROPIC_API_KEY")
if not API_KEY:
    raise ValueError("ANTHROPIC_API_KEY not found in repo root .env")
# Use httpx client with SSL verification disabled — needed on machines with corporate CAs
_http_client = httpx.Client(verify=False)
client = anthropic.Anthropic(api_key=API_KEY, http_client=_http_client)
MODEL  = "claude-opus-4-8"

# ---------------------------------------------------------------------------
# Step 1 — deterministic extraction from JSON (no LLM, no cost)
# ---------------------------------------------------------------------------
def _extract_furniture_facts(furniture: list) -> dict:
    names = {f.get("name", "") for f in furniture}

    if "KitchenCounterUorLshape" in names:
        kitchen_counter = "L-shaped or U-shaped"
    elif "KitchenCounterLinear" in names:
        kitchen_counter = "single-wall"
    else:
        kitchen_counter = "unclear"

    has_dining_six  = "DiningTableSix"  in names
    has_dining_four = "DiningTableFour" in names
    has_dining      = has_dining_six or has_dining_four
    dining_seats    = 6 if has_dining_six else (4 if has_dining_four else 0)

    if "BedDouble" in names:
        bed_type = "double"
    elif "BedSingle" in names:
        bed_type = "single"
    else:
        bed_type = "unclear"

    return {
        "kitchen_counter_type": kitchen_counter,
        "has_dining_table":     has_dining,
        "dining_seats":         dining_seats,
        "has_tv":               "TV" in names,
        "studio_bed_type":      bed_type,
        "has_desk":             "DeskLaptop" in names,
    }


def extract_context(layout: dict) -> dict:
    rooms    = layout.get("rooms", [])
    doors    = layout.get("doors", [])
    programs = [r["attributes"]["program"] for r in rooms]

    bed_ids    = {r["id"] for r in rooms if r["attributes"]["program"] == "bed"}
    bath_ids   = {r["id"] for r in rooms if r["attributes"]["program"] == "bath"}
    extra_ids  = {r["id"] for r in rooms if r["attributes"]["program"] == "extra"}
    living_ids = {r["id"] for r in rooms if r["attributes"]["program"] == "living"}

    n_bed  = len(bed_ids)
    n_bath = programs.count("bath")
    has_store = bool(extra_ids)
    open_plan = "kitchen" not in programs

    layout_id = layout.get("layoutId", "")
    technical_id = layout.get("apartment", {}).get("id", layout_id)
    try:
        de = int(technical_id.split("_de")[1].split("_")[0])
    except (IndexError, ValueError):
        de = -1
    entry_side = {0: "bottom", 1: "right", 2: "top", 3: "left"}.get(de, "unknown")

    ensuite = any(
        set(d["attributes"]["connectsRooms"]) & bed_ids and
        set(d["attributes"]["connectsRooms"]) & bath_ids
        for d in doors
    )
    corridor_door_to_living = any(
        set(d["attributes"]["connectsRooms"]) & extra_ids and
        set(d["attributes"]["connectsRooms"]) & living_ids
        for d in doors
    )

    # Classify each bath room from area alone (no LLM needed for this).
    # Planfinder calibrated thresholds (from dataset median areas):
    #   WC:              < 5.0 m²  — toilet only
    #   shower-only:     5.0–8.0 m²
    #   shower+bathtub:  >= 8.0 m²
    bath_rooms_info = sorted(
        [
            {
                "area_m2": round(r["attributes"].get("area", 0), 1),
                "likely_type": (
                    "wc"              if r["attributes"].get("area", 0) <  5.0 else
                    "shower_only"     if r["attributes"].get("area", 0) <  8.0 else
                    "shower_bathtub"
                ),
            }
            for r in rooms if r["attributes"]["program"] == "bath"
        ],
        key=lambda x: x["area_m2"]
    )
    n_wc            = sum(1 for b in bath_rooms_info if b["likely_type"] == "wc")
    n_full_bathroom = sum(1 for b in bath_rooms_info if b["likely_type"] != "wc")
    n_has_bathtub   = sum(1 for b in bath_rooms_info if b["likely_type"] == "shower_bathtub")

    furn = _extract_furniture_facts(layout.get("furniture", []))

    return {
        "space_type":              "studio" if n_bed == 0 else f"{n_bed}-bedroom",
        "bedroom_count":           n_bed,
        "secondary_count":         max(0, n_bed - 1),
        "bathroom_count":          n_bath,
        "n_wc":                    n_wc,
        "n_full_bathroom":         n_full_bathroom,
        "n_has_bathtub":           n_has_bathtub,
        "bath_rooms_info":         bath_rooms_info,
        "open_plan":               open_plan,
        "has_storage_room":        has_store,
        "entry_side":              entry_side,
        "ensuite_from_json":       ensuite,
        "corridor_door_to_living": corridor_door_to_living,
        # Furniture-derived (no LLM needed)
        "kitchen_counter_type":    furn["kitchen_counter_type"],
        "has_dining_table":        furn["has_dining_table"],
        "dining_seats":            furn["dining_seats"],
        "has_tv":                  furn["has_tv"],
        "studio_bed_type":         furn["studio_bed_type"],
        "has_desk":                furn["has_desk"],
    }

# ---------------------------------------------------------------------------
# Crop PNG to floor plan bounding box before sending to LLM
# ---------------------------------------------------------------------------
def crop_to_plan(png_path: Path, padding: int = 30) -> bytes:
    img = Image.open(png_path).convert("RGB")
    arr = np.array(img)
    r, g, b = arr[:,:,0].astype(int), arr[:,:,1].astype(int), arr[:,:,2].astype(int)
    mask = (np.abs(r - g) > 15) | (np.abs(r - b) > 15) | (r < 180)
    rows = np.where(mask.any(axis=1))[0]
    cols = np.where(mask.any(axis=0))[0]
    if len(rows) == 0 or len(cols) == 0:
        return png_path.read_bytes()
    top    = max(0, int(rows[0])  - padding)
    bottom = min(img.height, int(rows[-1]) + padding)
    left   = max(0, int(cols[0])  - padding)
    right  = min(img.width,  int(cols[-1]) + padding)
    cropped = img.crop((left, top, right, bottom))
    buf = io.BytesIO()
    cropped.save(buf, format="PNG")
    return buf.getvalue()

def get_cropped_png(png_path: Path) -> bytes:
    cropped_path = SCREENS_CROP_DIR / png_path.name
    if not cropped_path.exists():
        img_bytes = crop_to_plan(png_path)
        cropped_path.write_bytes(img_bytes)
    return cropped_path.read_bytes()

# ---------------------------------------------------------------------------
# Step 2 — vision LLM questionnaire
# ---------------------------------------------------------------------------
QUESTIONNAIRE = """\
You are reading an architectural floor plan.
Answer all questions based only on what is visible in the image.
Return a single valid JSON object with exactly these keys. No prose, no explanation.
Use "na" for any field that does not apply to this layout.

Layout context: {context}
Spatial reference: the entry door is on the {entry_side} side of the image.
Use this to interpret cook orientation, TV position, sofa facing direction, and bedroom positions.

BEFORE ANSWERING — read these rules carefully:

CORRIDOR SHAPE: Physically trace the walking path from the front door to the living area step by step in the image. If the path turns at any point (even once), it is L-shaped. Only mark "straight" if you can walk a completely direct line from entry door to living area with zero direction changes. When in doubt, choose L-shaped.

DESKS: Examine each bedroom closely before answering. A desk is a small rectangular piece of furniture pushed against a wall, clearly narrower and shallower than a dining table. It may appear as a thin rectangle along a wall. Do not mark "no" until you have looked carefully at all four walls of the bedroom.

BATHROOMS — the layout context already classifies each sanitary room by area (wc / shower_only / shower_bathtub). You do not need to detect bathroom fixtures — that is already determined from the JSON and passed to you in the layout context.

KITCHEN LIGHT: Look at which wall the kitchen counter runs along. If that wall is an exterior wall (has a window symbol), kitchen has direct natural light. If the counter faces an interior wall but the living zone nearby has windows, it is partial.

{
  "spatial_character":                  "compact and efficient / spacious and generous / cellular and compartmentalised / open and flowing / narrow and elongated",
  "natural_light_impression":           "well-lit throughout / living bright bedrooms dim / uniformly moderate / predominantly dark",
  "visual_depth_from_entry":            "shallow — one room visible / deep — views through multiple spaces",
  "corridor_character":                 "none — fully open / minimal — short link / functional corridor / dominant corridor",

  "cook_faces_room":                    "yes / no / partial",
  "kitchen_natural_light":              "yes / partial / no",

  "living_zone_shape":                  "rectangular / L-shaped / open corner / irregular",
  "kitchen_position_in_living":         "end wall / side wall / centre island / separate room / na",
  "living_arrangement":                 "linear kitchen-dining-living / split seating-kitchen-dining / L-shaped / kitchen-dominant / living-dominant / other",
  "seating_arrangement":                "<short description of all sofa or seating positions and what each faces>",
  "tv_wall_relative_to_entry":          "same wall as entry / opposite wall to entry / left of entry / right of entry / unclear / na",
  "cook_can_see_tv":                    "yes / no / unclear / na",
  "diners_face_tv":                     "yes / no / unclear / na",

  "entry_zone_type":                    "direct into living / direct into kitchen / dedicated foyer / corridor entry / unclear",
  "entry_what_you_see_first":           "kitchen / living area / bedroom doors / storage / blank wall / unclear",
  "entry_storage_visible":              "yes / no",
  "entry_corridor_shape":               "none / straight (zero direction changes from door to living) / L-shaped (path turns once) / T-junction",
  "entry_corridor_length":              "short / medium / long / na",

  "sleeping_area_definition":           "none — fully open / partial partition / alcove / dedicated zone with door / na",
  "bed_visible_from_front_door":        "yes / no / partial / na",
  "bed_visible_from_kitchen":           "yes / no / partial / na",

  "master_access_via":                  "own door off corridor / through living / through another bedroom / through kitchen / na",
  "master_desk_visible":                "yes / no / na",
  "master_walk_in_wardrobe":            "yes / no / na",
  "master_walk_in_wardrobe_type":       "open two facing units / enclosed with door / none / na",

  "secondary_1_access_via":             "own door off corridor / through living / through another bedroom / through kitchen / na",
  "secondary_1_desk_visible":           "yes / no / na",
  "secondary_1_walk_in_wardrobe":       "yes / no / na",
  "secondary_1_walk_in_wardrobe_type":  "open two facing units / enclosed with door / none / na",

  "secondary_2_access_via":             "own door off corridor / through living / through another bedroom / through kitchen / na",
  "secondary_2_desk_visible":           "yes / no / na",
  "secondary_2_walk_in_wardrobe":       "yes / no / na",
  "secondary_2_walk_in_wardrobe_type":  "open two facing units / enclosed with door / none / na",

  "double_bedroom_position":            "front of apartment / rear of apartment / corner / middle / unclear / na",


  "extra_room_character":               "small dark utility only (no exterior wall, fully enclosed by other rooms) / windowless but spacious (no exterior wall but large enough for active use) / has natural light (shares an exterior wall) / na",
  "extra_room_best_use":                "pantry (directly accessible from kitchen without passing through other rooms) / laundry utility / storage / hobby room / home gym / music room / gaming room / meditation room / home office (only if it has natural light) / multiple options / na",

  "not_suitable_for":                   ["<list each household type or lifestyle that would find this specific layout unsuitable — be concrete and specific to what you see. Empty array [] if no clear unsuitabilities.>"]
}
"""

def call_vision_llm(png_path: Path, context: dict) -> dict:
    img_data = get_cropped_png(png_path)
    entry    = context.get("entry_side", "unknown")
    context_for_llm = {k: v for k, v in context.items() if k != "entry_side"}
    prompt = (
        QUESTIONNAIRE
        .replace("{context}", json.dumps(context_for_llm))
        .replace("{entry_side}", entry)
    )
    response = client.messages.create(
        model=MODEL,
        max_tokens=1500,
        messages=[{
            "role": "user",
            "content": [
                {
                    "type": "image",
                    "source": {
                        "type": "base64",
                        "media_type": "image/png",
                        "data": base64.b64encode(img_data).decode()
                    }
                },
                {"type": "text", "text": prompt}
            ]
        }]
    )
    raw = response.content[0].text.strip()
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
    return json.loads(raw.strip())

# ---------------------------------------------------------------------------
# Step 3 — assemble description from context + vision answers
# ---------------------------------------------------------------------------

_CORRIDOR_CHARACTER = {
    "none — fully open":   "No internal corridor — fully open layout.",
    "minimal — short link":"Short connecting link between entry and living area.",
    "functional corridor": "Clear functional corridor connecting zones.",
    "dominant corridor":   "Corridor is the dominant circulation element through the apartment.",
}

_CORRIDOR_LENGTH = {
    "short":  "short",
    "medium": "medium length",
    "long":   "running the full depth of the apartment",
}

_BEDROOM_POSITION = {
    "front of apartment": "closest to entry — lighter acoustic separation from the arrival zone",
    "rear of apartment":  "at the rear — maximum distance from entry, best acoustic separation from living activity",
    "corner":             "in a corner position — potential exposure on two sides",
    "middle":             "in a central position within the apartment",
}


def assemble(ctx: dict, vis: dict, layout_id: str) -> dict:
    parts    = []
    n_bed    = ctx["bedroom_count"]
    n_single = ctx["secondary_count"]
    n_bath   = ctx["bathroom_count"]
    ensuite  = ctx["ensuite_from_json"]
    is_studio = ctx["space_type"] == "studio"
    cook_f   = vis.get("cook_faces_room", "")

    # Pull LLM not_suitable_for — normalise to list of strings
    llm_ns = vis.get("not_suitable_for", [])
    if isinstance(llm_ns, list):
        not_suitable = [str(x).strip() for x in llm_ns if x and str(x).strip()]
    elif isinstance(llm_ns, str) and llm_ns not in ("na", ""):
        not_suitable = [llm_ns]
    else:
        not_suitable = []

    # 1 — Spatial character
    sc  = vis.get("spatial_character", "")
    nli = vis.get("natural_light_impression", "")
    vd  = vis.get("visual_depth_from_entry", "")
    cc  = vis.get("corridor_character", "")
    char_parts = [x for x in [sc, nli, vd] if x and x not in ("unclear", "na")]
    if char_parts:
        parts.append(". ".join(c.capitalize() for c in char_parts) + ".")
    if cc and cc not in ("unclear", "na"):
        cc_sentence = _CORRIDOR_CHARACTER.get(cc)
        if cc_sentence:
            parts.append(cc_sentence)

    # 2 — Kitchen (counter type from furniture data, light from vision)
    k_shape_clean = ctx.get("kitchen_counter_type", "unclear")

    knl = vis.get("kitchen_natural_light", "unclear")
    knl_note = ""
    if knl == "yes":
        knl_note = " with direct natural light"
    elif knl == "partial":
        knl_note = " with indirect natural light from the adjacent living area"
    elif knl == "no":
        knl_note = " — no direct natural light to the counter"

    parts.append(f"Kitchen: {k_shape_clean}, no island or peninsula{knl_note}.")

    if cook_f == "yes":
        parts.append("Cook faces the dining and living area — suited to cooking while entertaining or supervising children.")
    elif cook_f == "no":
        parts.append("Cook faces the wall, back to the living and dining area.")
    elif cook_f == "partial":
        parts.append("Cook partially faces the living area depending on position at the counter.")

    if ctx["open_plan"]:
        parts.append("Fully open plan — no wall separates kitchen from dining and living.")
    else:
        parts.append("Kitchen is a separate enclosed room.")

    # 3 — Living zone
    arr  = vis.get("living_arrangement", "")
    kpos = vis.get("kitchen_position_in_living", "")

    zone_parts = []
    if arr and arr not in ("unclear", "na", "other"):
        zone_parts.append(f"Living arrangement: {arr}")
    if kpos and kpos not in ("unclear", "na"):
        zone_parts.append(f"kitchen on {kpos}")
    if zone_parts:
        parts.append(", ".join(zone_parts) + ".")

    seating = vis.get("seating_arrangement", "")
    if seating and seating not in ("unclear", "na"):
        parts.append(f"Seating: {seating}.")

    if ctx["has_dining_table"]:
        seats = ctx["dining_seats"]
        parts.append(f"Dining table (rectangular), approximately {seats} seats.")

    if ctx["has_tv"]:
        tv_wall  = vis.get("tv_wall_relative_to_entry", "unclear")
        see_tv   = vis.get("cook_can_see_tv", "unclear")
        face_tv  = vis.get("diners_face_tv", "unclear")
        see_str  = "can" if see_tv == "yes" else ("cannot" if see_tv == "no" else "may")
        face_str = "face" if face_tv == "yes" else ("do not face" if face_tv == "no" else "unclear if facing")
        parts.append(
            f"TV on wall {tv_wall}. "
            f"Cook {see_str} see TV from cooking position. "
            f"Diners {face_str} the TV."
        )

    # 4 — Entry
    ez    = vis.get("entry_zone_type", "")
    ewysf = vis.get("entry_what_you_see_first", "")
    ecshp = vis.get("entry_corridor_shape", "")
    eclen = vis.get("entry_corridor_length", "")

    entry_parts = []
    if ez and ez not in ("unclear", "na"):
        entry_parts.append(f"Entry: {ez}")
    if ewysf and ewysf not in ("unclear", "na"):
        entry_parts.append(f"first thing visible on arrival is {ewysf}")
    if ecshp and ecshp not in ("none", "unclear", "na"):
        ecshp_clean = ecshp.split("(")[0].strip()
        corridor_desc = f"{ecshp_clean} corridor"
        eclen_str = _CORRIDOR_LENGTH.get(eclen, "")
        if eclen_str:
            corridor_desc += f", {eclen_str}"
        entry_parts.append(corridor_desc)
    if entry_parts:
        parts.append(", ".join(entry_parts) + ".")
    if vis.get("entry_storage_visible") == "yes":
        parts.append("Entry area has space for coat and shoe storage.")
    if ctx["corridor_door_to_living"]:
        parts.append("Door separates entry corridor from living area.")
    else:
        parts.append("No door between entry and living — relevant where local regulations require separation.")

    # 5 — Studio or bedrooms
    if is_studio:
        sep  = vis.get("sleeping_area_definition", "unclear")
        bfd  = vis.get("bed_visible_from_front_door", "unclear")
        bfk  = vis.get("bed_visible_from_kitchen", "unclear")
        btyp = ctx.get("studio_bed_type", "unclear")   # from furniture

        vis_fd = "visible" if bfd == "yes" else ("partially visible" if bfd == "partial" else "not visible")
        vis_k  = "visible" if bfk == "yes" else ("partially visible" if bfk == "partial" else "not visible")
        parts.append(
            f"Studio apartment. {btyp.capitalize()} bed. "
            f"Sleeping area separation from living: {sep}. "
            f"Bed {vis_fd} from front door, {vis_k} from kitchen."
        )
        if ctx.get("has_desk"):
            parts.append("Dedicated work zone visible in plan.")

    else:
        # Master bedroom
        m_access = vis.get("master_access_via", "na")
        m_desk   = vis.get("master_desk_visible", "na")
        m_wic    = vis.get("master_walk_in_wardrobe", "na")
        m_wic_t  = vis.get("master_walk_in_wardrobe_type", "na")

        suite_label = "Master suite (en-suite bathroom)" if ensuite else "Double bedroom"
        wic_note    = f"walk-in wardrobe ({m_wic_t})" if m_wic == "yes" else "no walk-in wardrobe"
        access_note = f"accessed via {m_access}" if m_access not in ("na", "unclear") else ""
        desk_note   = "desk visible" if m_desk == "yes" else ""
        m_notes     = [n for n in [access_note, wic_note, desk_note] if n]
        parts.append(f"{suite_label} — {', '.join(m_notes)}." if m_notes else f"{suite_label}.")
        if m_access == "through living":
            parts.append("Master bedroom is only accessible through the living room — no direct corridor access, least private position.")

        # Bedroom position
        dbpos = vis.get("double_bedroom_position", "na")
        if dbpos not in ("na", "unclear"):
            pos_text = _BEDROOM_POSITION.get(dbpos, f"at the {dbpos}")
            parts.append(f"{suite_label} {pos_text}.")

        # Secondary bedrooms
        desk_count = 0
        for i, prefix in enumerate(["secondary_1", "secondary_2"], 1):
            if i > n_single:
                break
            s_access = vis.get(f"{prefix}_access_via", "na")
            s_desk   = vis.get(f"{prefix}_desk_visible", "na")
            s_wic    = vis.get(f"{prefix}_walk_in_wardrobe", "na")
            s_wic_t  = vis.get(f"{prefix}_walk_in_wardrobe_type", "na")
            if s_desk == "yes":
                desk_count += 1
            s_notes = []
            if s_access not in ("na", "unclear"):
                s_notes.append(f"accessed via {s_access}")
            if s_wic == "yes":
                s_notes.append(f"walk-in wardrobe ({s_wic_t})")
            if s_desk == "yes":
                s_notes.append("desk visible")
            parts.append(f"Secondary bedroom {i} — {', '.join(s_notes)}." if s_notes else f"Secondary bedroom {i}.")
            if s_access == "through living":
                parts.append(f"Secondary bedroom {i} is only accessible through the living room — no direct corridor access.")

        if n_single >= 1:
            bed_label = "Each single bedroom" if n_single > 1 else "The single bedroom"
            parts.append(
                f"{bed_label} can function as a home office, hobby room, or guest room. "
                f"{desk_count} of {n_single} have a desk visible in plan."
            )
            configs = ["children's bedroom(s)", "dedicated home office", "hobby or creative room",
                       "guest room", "bunk bed arrangement for extended household capacity"]
            if n_single >= 2:
                configs.insert(2, "home office plus children's bedroom")
            parts.append("Possible configurations for single bedroom(s): " + " / ".join(configs) + ".")

    # 6 — Extra room
    if ctx["has_storage_room"]:
        ec   = vis.get("extra_room_character", "na")
        euse = vis.get("extra_room_best_use", "na")
        ec_clean = ec.split("(")[0].strip() if ec and ec != "na" else ""
        euse_clean = euse.split("(")[0].strip() if euse and euse != "na" else ""
        # Windowless rooms always include storage as a valid use
        windowless = ec_clean and any(x in ec_clean.lower() for x in ("dark", "windowless"))
        if windowless and euse_clean and "storage" not in euse_clean.lower():
            euse_clean = f"{euse_clean} / storage"
        elif windowless and not euse_clean:
            euse_clean = "storage"
        if ec_clean and euse_clean:
            parts.append(f"Extra room: {ec_clean}. Best suited as: {euse_clean}.")
        elif ec_clean:
            parts.append(f"Extra room: {ec_clean}.")

    # 7 — Bathroom routines (entirely from JSON area classification — no LLM)
    n_wc        = ctx["n_wc"]
    n_full_bath = ctx["n_full_bathroom"]
    n_bathtub   = ctx["n_has_bathtub"]
    bath_info   = ctx["bath_rooms_info"]

    def _bath_label(btype):
        if btype == "wc":
            return "WC (toilet only)"
        if btype == "shower_bathtub":
            return "bathroom (shower and bathtub, no toilet)"
        return "bathroom (shower, no toilet)"

    room_labels = [_bath_label(b["likely_type"]) for b in bath_info]

    if room_labels:
        if len(room_labels) == 1:
            parts.append(f"One {room_labels[0]}.")
        else:
            parts.append("Sanitary rooms: " + "; ".join(room_labels) + ".")

    if n_full_bath >= 2:
        parts.append(
            f"Two separate bathroom facilities — parallel showering possible. "
            f"{'One separate WC.' if n_wc == 1 else f'{n_wc} WCs.' if n_wc > 1 else 'No separate WC.'}"
        )
    elif n_full_bath == 1 and n_wc >= 1:
        parts.append(
            "One bathroom, one separate WC — one person can shower while another uses the toilet. "
            "Simultaneous showering not possible — only one shower/bathtub in the apartment."
        )
    elif n_full_bath == 1 and n_wc == 0:
        parts.append("Single bathroom — sequential morning routine for all household members.")
    elif n_full_bath == 0 and n_wc >= 1:
        parts.append(f"{n_wc} WC only — no shower or bathtub.")

    # 8 — Household fit
    fit = []
    if n_bed >= 3:
        fit.append("families with two or more children")
    elif n_bed == 2:
        fit.append("couples needing a spare room or home office")
        fit.append("small families with one child")
    elif n_bed == 1:
        fit.append("singles or couples")
    elif is_studio:
        fit.append("singles or couples comfortable with combined living and sleeping space")
    if cook_f == "yes":
        fit.append("households prioritising communal cooking and dining")
    if fit:
        parts.append("Suits: " + ", ".join(fit) + ".")
    if not_suitable:
        parts.append("Not suitable for: " + "; ".join(not_suitable) + ".")

    return {
        "layoutId":         layout_id,
        "description":      " ".join(parts),
        "not_suitable_for": not_suitable,
    }

# ---------------------------------------------------------------------------
# Empty layout / blank PNG detection
# ---------------------------------------------------------------------------
def is_blank_png(png_path: Path, threshold: int = 240) -> bool:
    arr = np.array(Image.open(png_path).convert("RGB"))
    return not np.any(arr < threshold)

def is_empty_layout(layout: dict) -> bool:
    rooms = layout.get("rooms", [])
    real  = [r for r in rooms if r.get("attributes", {}).get("program", "") != "extra"]
    return len(real) == 0

def write_empty_marker(out_file: Path, layout_id: str) -> None:
    out_file.write_text(json.dumps({
        "layoutId":         layout_id,
        "description":      "empty",
        "not_suitable_for": ["all"],
    }, indent=2), encoding="utf-8")

def write_blank_png_marker(out_file: Path, layout_id: str) -> None:
    out_file.write_text(json.dumps({
        "layoutId":         layout_id,
        "description":      "empty png",
        "not_suitable_for": ["all"],
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

        if is_empty_layout(layout):
            write_empty_marker(out_file, layout_id)
            print(f"  EMPTY      {layout_id}")
            empty += 1
            continue

        if not png_file.exists():
            print(f"  SKIP       {layout_id}  (no PNG)")
            skip_no_png += 1
            continue

        if is_blank_png(png_file):
            write_blank_png_marker(out_file, layout_id)
            print(f"  BLANK PNG  {layout_id}")
            continue

        context = extract_context(layout)

        try:
            vision = call_vision_llm(png_file, context)
            result = assemble(context, vision, layout_id)
            out_file.write_text(json.dumps(result, indent=2), encoding="utf-8")
            print(f"  OK         {layout_id}")
            done += 1
            time.sleep(0.3)
        except Exception as e:
            print(f"  ERR        {layout_id}: {e}")
            errors += 1

    print(f"\nDone: {done} generated | {empty} empty | {skip_exists} already existed | "
          f"{skip_no_png} skipped (no PNG) | {errors} errors")

if __name__ == "__main__":
    import sys
    if "--regen" in sys.argv:
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
                print(f"  EMPTY      {lid}"); continue
            if is_blank_png(png_file):
                write_blank_png_marker(out_file, lid)
                print(f"  BLANK PNG  {lid}"); continue
            context = extract_context(layout)
            try:
                vision = call_vision_llm(png_file, context)
                result = assemble(context, vision, lid)
                out_file.write_text(json.dumps(result, indent=2), encoding="utf-8")
                print(f"  OK         {lid}")
                done += 1
                time.sleep(0.3)
            except Exception as e:
                print(f"  ERR        {lid}: {e}")
                errors += 1
        print(f"\nDone: {done} regenerated | {errors} errors")
    elif "--test" in sys.argv:
        tested = 0
        for jf in sorted(JSONS_DIR.glob("*.json")):
            if tested >= 3:
                break
            lid = jf.stem
            png_file = SCREENS_DIR / f"{lid}.png"
            if not (OUTPUT_DIR / f"{lid}.json").exists() and png_file.exists():
                layout = json.loads(jf.read_text(encoding="utf-8"))
                if not is_empty_layout(layout) and not is_blank_png(png_file):
                    print(f"\n{'='*60}")
                    print(f"Testing on: {lid}")
                    ctx    = extract_context(layout)
                    vis    = call_vision_llm(png_file, ctx)
                    print("Vision answers:")
                    print(json.dumps(vis, indent=2))
                    print("\nAssembled description:")
                    result = assemble(ctx, vis, lid)
                    print(json.dumps(result, indent=2))
                    tested += 1
                    time.sleep(0.3)
    else:
        main()
