from __future__ import annotations
import json
from _runtime.llm import write_tool_result

# ── Section / material constants (used by both modify and evaluate) ───────────

STEEL_BEAM_PROPS: dict[str, dict] = {
    "IPE120": {"A_mm2": 1_321, "I_mm4": 3.18e6,   "Wy_mm3":  53_000},
    "IPE160": {"A_mm2": 2_009, "I_mm4": 8.69e6,   "Wy_mm3": 108_700},
    "IPE200": {"A_mm2": 2_848, "I_mm4": 19.43e6,  "Wy_mm3": 194_300},
    "IPE240": {"A_mm2": 3_912, "I_mm4": 38.92e6,  "Wy_mm3": 324_300},
    "IPE300": {"A_mm2": 5_381, "I_mm4": 83.56e6,  "Wy_mm3": 557_000},
    "IPE360": {"A_mm2": 7_273, "I_mm4": 162.7e6,  "Wy_mm3": 904_000},
}

STEEL_COL_PROPS: dict[str, dict] = {
    "HSS80x80x5":   {"A_mm2": 1_480, "I_mm4": 1.38e6,  "r_min_mm": 30.5},
    "HSS100x100x6": {"A_mm2": 2_256, "I_mm4": 3.61e6,  "r_min_mm": 40.0},
    "HSS120x120x6": {"A_mm2": 2_736, "I_mm4": 6.39e6,  "r_min_mm": 48.3},
    "HSS150x150x6": {"A_mm2": 3_456, "I_mm4": 12.69e6, "r_min_mm": 60.6},
    "HSS180x180x8": {"A_mm2": 5_536, "I_mm4": 29.2e6,  "r_min_mm": 72.6},
    "HSS200x200x8": {"A_mm2": 6_176, "I_mm4": 40.1e6,  "r_min_mm": 80.6},
}

DEFAULT_SECTIONS: dict[str, dict] = {
    "RCC_XS":    {"beam_depth_mm": 200, "beam_width_mm": 150, "col_dims": "150x150"},
    "RCC":       {"beam_depth_mm": 250, "beam_width_mm": 175, "col_dims": "175x175"},
    "RCC_M":     {"beam_depth_mm": 300, "beam_width_mm": 200, "col_dims": "200x200"},
    "RCC_L":     {"beam_depth_mm": 350, "beam_width_mm": 225, "col_dims": "225x225"},
    "RCC_XL":    {"beam_depth_mm": 400, "beam_width_mm": 250, "col_dims": "250x250"},
    "RCC_XXL":   {"beam_depth_mm": 450, "beam_width_mm": 275, "col_dims": "275x275"},
    "STEEL_XS":  {"beam_depth_mm": 120, "beam_width_mm": 64,  "col_dims": "80x80",   "beam_section": "IPE120", "col_section": "HSS80x80x5"},
    "STEEL":     {"beam_depth_mm": 160, "beam_width_mm": 82,  "col_dims": "100x100", "beam_section": "IPE160", "col_section": "HSS100x100x6"},
    "STEEL_M":   {"beam_depth_mm": 200, "beam_width_mm": 100, "col_dims": "120x120", "beam_section": "IPE200", "col_section": "HSS120x120x6"},
    "STEEL_L":   {"beam_depth_mm": 240, "beam_width_mm": 120, "col_dims": "150x150", "beam_section": "IPE240", "col_section": "HSS150x150x6"},
    "STEEL_XL":  {"beam_depth_mm": 300, "beam_width_mm": 150, "col_dims": "180x180", "beam_section": "IPE300", "col_section": "HSS180x180x8"},
    "STEEL_XXL": {"beam_depth_mm": 360, "beam_width_mm": 170, "col_dims": "200x200", "beam_section": "IPE360", "col_section": "HSS200x200x8"},
    "TIMBER_XS":  {"beam_depth_mm": 150, "beam_width_mm": 75,  "col_dims": "75x75"},
    "TIMBER":     {"beam_depth_mm": 240, "beam_width_mm": 100, "col_dims": "100x100"},
    "TIMBER_M":   {"beam_depth_mm": 300, "beam_width_mm": 120, "col_dims": "120x120"},
    "TIMBER_L":   {"beam_depth_mm": 360, "beam_width_mm": 150, "col_dims": "150x150"},
    "TIMBER_XL":  {"beam_depth_mm": 480, "beam_width_mm": 200, "col_dims": "200x200"},
    "TIMBER_XXL": {"beam_depth_mm": 600, "beam_width_mm": 250, "col_dims": "250x250"},
}

SECTION_UPGRADE_MAP: dict[str, str] = {
    "RCC_XS": "RCC",       "RCC": "RCC_M",       "RCC_M": "RCC_L",       "RCC_L": "RCC_XL",     "RCC_XL": "RCC_XXL",
    "STEEL_XS": "STEEL",   "STEEL": "STEEL_M",   "STEEL_M": "STEEL_L",   "STEEL_L": "STEEL_XL", "STEEL_XL": "STEEL_XXL",
    "TIMBER_XS": "TIMBER", "TIMBER": "TIMBER_M", "TIMBER_M": "TIMBER_L", "TIMBER_L": "TIMBER_XL", "TIMBER_XL": "TIMBER_XXL",
}

BEAM_SECTION_UPGRADE: dict[str, tuple] = {
    "IPE120": ("IPE160", 160,  82),
    "IPE160": ("IPE200", 200, 100),
    "IPE200": ("IPE240", 240, 120),
    "IPE240": ("IPE300", 300, 150),
    "IPE300": ("IPE360", 360, 170),
}

COL_SECTION_UPGRADE: dict[str, tuple] = {
    "HSS80x80x5":   ("HSS100x100x6", "100x100"),
    "HSS100x100x6": ("HSS120x120x6", "120x120"),
    "HSS120x120x6": ("HSS150x150x6", "150x150"),
    "HSS150x150x6": ("HSS180x180x8", "180x180"),
    "HSS180x180x8": ("HSS200x200x8", "200x200"),
}

BEAM_DIM_UPGRADE: dict[str, tuple] = {
    # RCC chain — 25mm width / 50mm depth increments
    "150x200": ("175x250", 250, 175),
    "175x250": ("200x300", 300, 200),
    "200x300": ("225x350", 350, 225),
    "225x350": ("250x400", 400, 250),
    "250x400": ("275x450", 450, 275),
    # Timber chain
    "75x150":  ("100x240", 240, 100),
    "100x240": ("120x300", 300, 120),
    "120x300": ("150x360", 360, 150),
    "150x360": ("200x480", 480, 200),
    "200x480": ("250x600", 600, 250),
}

COL_DIM_UPGRADE: dict[str, str] = {
    "75x75":   "90x90",
    "90x90":   "100x100",
    "100x100": "120x120",
    "120x120": "150x150",
    "150x150": "175x175",
    "175x175": "200x200",
    "200x200": "225x225",
    "225x225": "250x250",
    "250x250": "275x275",
}

BASE_MATERIALS = ["RCC", "STEEL", "TIMBER"]


# ── Layout mutation functions ─────────────────────────────────────────────────

# Tier chains (small→large) + a depth/span factor per material. Timber & steel start
# auto-failing at their base tier on typical spans, so we pick a span-appropriate
# starting section for them; RCC keeps its existing fixed base (behaviour unchanged).
_TIER_CHAINS = {
    "RCC":    ["RCC_XS", "RCC", "RCC_M", "RCC_L", "RCC_XL", "RCC_XXL"],
    "STEEL":  ["STEEL_XS", "STEEL", "STEEL_M", "STEEL_L", "STEEL_XL", "STEEL_XXL"],
    "TIMBER": ["TIMBER_XS", "TIMBER", "TIMBER_M", "TIMBER_L", "TIMBER_XL", "TIMBER_XXL"],
}
_SPAN_DEPTH_DIVISOR = {"STEEL": 20.0, "TIMBER": 12.0}   # required beam depth ≈ span/divisor


def _span_aware_tier(base_mat: str, span_m: float, default_key: str) -> str:
    """Pick the smallest tier (>= the material's base) whose beam depth suits the span.
    Only used for STEEL/TIMBER; RCC returns its default."""
    chain = _TIER_CHAINS.get(base_mat)
    div = _SPAN_DEPTH_DIVISOR.get(base_mat)
    if not chain or not div or span_m <= 0:
        return default_key
    need_depth = span_m * 1000.0 / div
    base_i = chain.index(default_key) if default_key in chain else 1
    for key in chain[base_i:]:
        if DEFAULT_SECTIONS[key]["beam_depth_mm"] >= need_depth:
            return key
    return chain[-1]


def apply_material_override(layout_json_string: str, material: str,
                            level: str | None = None,
                            element_type: str | None = None) -> str:
    """Patch structure elements with the given material and its default sections.
    For STEEL/TIMBER, beams get a span-appropriate starting section so a freshly
    generated grid is evaluable instead of failing every beam at the base tier.

    Optional scope (used by the agent for requests like "change all beams of level 2
    to timber"): `level` limits to one level key; `element_type` is "column"/"beam"."""
    import math as _m
    from nodes._layout import is_multilevel, get_level_keys
    layout = json.loads(layout_json_string)
    sec = DEFAULT_SECTIONS.get(material, DEFAULT_SECTIONS["RCC"])
    is_steel = "STEEL" in material.upper()
    base_mat = next((mm for mm in BASE_MATERIALS if material.upper().startswith(mm)), material)
    default_key = base_mat if base_mat in DEFAULT_SECTIONS else "RCC"
    _et = (element_type or "").lower().rstrip("s")   # "columns"->"column"

    def _type_ok(el):
        if _et not in ("column", "beam"):
            return True
        is_beam = len(el.get("geometry", [])) == 2
        return (_et == "beam") == is_beam

    def _patch(el):
        if not _type_ok(el):
            return
        attrs = el.setdefault("attributes", {})
        attrs["material"] = base_mat
        if len(el.get("geometry", [])) == 2:
            geo = el.get("geometry", [])
            _span = _m.dist(geo[0], geo[1]) if len(geo) >= 2 else 0.0
            _key = _span_aware_tier(base_mat, _span, default_key)
            _bsec = DEFAULT_SECTIONS.get(_key, sec)
            attrs["depth"] = str(_bsec["beam_depth_mm"])
            attrs["width"] = str(_bsec["beam_width_mm"])
            if is_steel and "beam_section" in _bsec:
                attrs["section"] = _bsec["beam_section"]
            else:
                attrs.pop("section", None)
        else:
            attrs["dimensions"] = sec["col_dims"]
            if is_steel and "col_section" in sec:
                attrs["section"] = sec["col_section"]
            else:
                attrs.pop("section", None)

    if is_multilevel(layout):
        for lk in get_level_keys(layout):
            if level and level != "__ALL__" and lk != level:
                continue
            for el in layout["levels"][lk].get("structure", []):
                _patch(el)
    else:
        if not level or level in ("level_01", "__ALL__"):
            for el in layout.get("structure", []):
                _patch(el)
    return json.dumps(layout)


def upgrade_element_section(layout_str: str, element_id: str, new_section: str) -> str:
    """Update a structural element's section. For multilevel layouts updates ALL levels."""
    from nodes._layout import is_multilevel, get_level_keys
    _BEAM_DIMS = {
        "IPE120": (120,  64), "IPE160": (160,  82), "IPE200": (200, 100),
        "IPE240": (240, 120), "IPE300": (300, 150), "IPE360": (360, 170),
    }
    _COL_DIMS = {
        "HSS80x80x5": "80x80", "HSS100x100x6": "100x100", "HSS120x120x6": "120x120",
        "HSS150x150x6": "150x150", "HSS180x180x8": "180x180", "HSS200x200x8": "200x200",
    }
    layout = json.loads(layout_str)

    def _apply(el):
        attrs = el.setdefault("attributes", {})
        is_beam = len(el.get("geometry", [])) == 2
        if new_section in _BEAM_DIMS:
            attrs["section"] = new_section
            d, w = _BEAM_DIMS[new_section]
            attrs["depth"] = str(d)
            attrs["width"] = str(w)
        elif new_section in _COL_DIMS:
            attrs["section"] = new_section
            attrs["dimensions"] = _COL_DIMS[new_section]
        elif is_beam and "x" in new_section:
            w_str, d_str = new_section.split("x", 1)
            attrs["depth"] = d_str
            attrs["width"] = w_str
        elif not is_beam and "x" in new_section:
            attrs["dimensions"] = new_section

    if is_multilevel(layout):
        for lk in get_level_keys(layout):
            for el in layout["levels"][lk].get("structure", []):
                if el["id"] == element_id:
                    _apply(el)
    else:
        for el in layout.get("structure", []):
            if el["id"] == element_id:
                _apply(el)
                break
    return json.dumps(layout)


def add_midspan_column(layout_str: str, beam_id: str, material: str) -> str:
    """Split a beam at its midpoint and insert a new column there."""
    from nodes._layout import is_multilevel, get_level_keys
    sec = DEFAULT_SECTIONS.get(material, DEFAULT_SECTIONS["RCC"])
    layout = json.loads(layout_str)

    def _build_midspan(structure):
        beam = next((e for e in structure if e["id"] == beam_id and len(e.get("geometry", [])) == 2), None)
        if not beam:
            return None
        p1, p2 = beam["geometry"]
        mid = [round((p1[0] + p2[0]) / 2, 3), round((p1[1] + p2[1]) / 2, 3)]
        bat = beam.get("attributes", {})
        new_col = {
            "id": f"{beam_id}_M", "name": f"Column_{beam_id}_M",
            "geometry": [mid],
            "attributes": {
                "type": "internal", "dimensions": sec["col_dims"],
                "height": bat.get("height", "3.5"), "isWallAligned": "false",
                "structuralRole": "primary", "material": material, "conflict": "None",
            },
        }
        new_a = {"id": f"{beam_id}a", "name": f"Beam_{beam_id}a", "geometry": [p1, mid], "attributes": dict(bat)}
        new_b = {"id": f"{beam_id}b", "name": f"Beam_{beam_id}b", "geometry": [mid, p2], "attributes": dict(bat)}
        new_structure = []
        for el in structure:
            if el["id"] == beam_id:
                new_structure += [new_a, new_b]
            else:
                new_structure.append(el)
        new_structure.append(new_col)
        return new_structure

    if is_multilevel(layout):
        for lk in get_level_keys(layout):
            result = _build_midspan(layout["levels"][lk].get("structure", []))
            if result is not None:
                layout["levels"][lk]["structure"] = result
                print(f"  Added midspan column under {beam_id} at {lk}")
                return json.dumps(layout)
        return layout_str
    else:
        result = _build_midspan(layout.get("structure", []))
        if result is None:
            return layout_str
        layout["structure"] = result
        return json.dumps(layout)


def apply_minimum_sections(layout_str: str, base_material: str) -> str:
    """Apply XS tier sections for base_material to all elements, keeping base material name."""
    from nodes._layout import is_multilevel, get_level_keys
    xs_key = f"{base_material}_XS"
    sec = DEFAULT_SECTIONS.get(xs_key, DEFAULT_SECTIONS[base_material])
    is_steel = "STEEL" in base_material.upper()
    layout = json.loads(layout_str)

    def _patch(el):
        attrs = el.setdefault("attributes", {})
        attrs["material"] = base_material
        attrs.pop("section", None)
        if len(el.get("geometry", [])) == 2:
            attrs["depth"] = str(sec["beam_depth_mm"])
            attrs["width"] = str(sec["beam_width_mm"])
            if is_steel and "beam_section" in sec:
                attrs["section"] = sec["beam_section"]
        else:
            attrs["dimensions"] = sec["col_dims"]
            if is_steel and "col_section" in sec:
                attrs["section"] = sec["col_section"]

    if is_multilevel(layout):
        for lk in get_level_keys(layout):
            for el in layout["levels"][lk].get("structure", []):
                _patch(el)
    else:
        for el in layout.get("structure", []):
            _patch(el)
    return json.dumps(layout)


def _upgrade_one_pass(layout_str: str, evaluation_result: dict) -> str:
    """Upgrade each failing beam and column by one step in the section chain."""
    for b in evaluation_result.get("beams", []):
        if b["bend_PASS"] and b["shear_PASS"] and b["defl_TL_PASS"] and b["defl_LL_PASS"]:
            continue
        cur = b.get("section_mm", "")
        if cur in BEAM_SECTION_UPGRADE:
            nxt, _, _ = BEAM_SECTION_UPGRADE[cur]
            layout_str = upgrade_element_section(layout_str, b["id"], nxt)
            print(f"  Min {b['id']}: {cur} -> {nxt}")
        elif cur in BEAM_DIM_UPGRADE:
            nxt, _, _ = BEAM_DIM_UPGRADE[cur]
            layout_str = upgrade_element_section(layout_str, b["id"], nxt)
            print(f"  Min {b['id']}: {cur} -> {nxt}")
    for c in evaluation_result.get("columns", []):
        if c["stress_PASS"] and c["buckling_PASS"]:
            continue
        cur = c.get("section_mm", "")
        if cur in COL_SECTION_UPGRADE:
            nxt, _ = COL_SECTION_UPGRADE[cur]
            layout_str = upgrade_element_section(layout_str, c["id"], nxt)
            print(f"  Min {c['id']}: {cur} -> {nxt}")
        elif cur in COL_DIM_UPGRADE:
            nxt = COL_DIM_UPGRADE[cur]
            layout_str = upgrade_element_section(layout_str, c["id"], nxt)
            print(f"  Min {c['id']}: {cur} -> {nxt}")
    return layout_str


# ── Column grid generator (Python fallback when GH returns empty) ─────────────

def _generate_column_grid(layout_json_str: str, grid_spacing: float) -> str:
    layout = json.loads(layout_json_str)
    outline = layout.get("outline", [])
    if not outline:
        return layout_json_str

    xs = [p[0] for p in outline if len(p) >= 2]
    ys = [p[1] for p in outline if len(p) >= 2]
    xmin, xmax = min(xs), max(xs)
    ymin, ymax = min(ys), max(ys)

    def grid_pts(lo, hi, spacing):
        pts = [lo]
        cur = lo + spacing
        while cur < hi - spacing * 0.3:
            pts.append(round(cur, 3))
            cur += spacing
        if pts[-1] != hi:
            pts.append(hi)
        return pts

    x_pos = grid_pts(xmin, xmax, grid_spacing)
    y_pos = grid_pts(ymin, ymax, grid_spacing)
    letters = [chr(65 + i) for i in range(len(x_pos))]
    nums = list(range(1, len(y_pos) + 1))
    structure = []

    for xi, x in enumerate(x_pos):
        L = letters[xi]
        for yi, y in enumerate(y_pos):
            n = nums[yi]
            exterior = (x == xmin or x == xmax or y == ymin or y == ymax)
            structure.append({
                "id": f"{L}_{n}", "name": f"Column_{L}_{n}",
                "geometry": [[x, y]],
                "attributes": {
                    "type": "exterior" if exterior else "internal",
                    "dimensions": "200x200", "height": "3.5",
                    "isWallAligned": "true", "structuralRole": "primary",
                    "material": "RCC", "conflict": "None",
                },
            })

    for yi, y in enumerate(y_pos):
        n = nums[yi]
        for xi in range(len(x_pos) - 1):
            La, Lb = letters[xi], letters[xi + 1]
            x1, x2 = x_pos[xi], x_pos[xi + 1]
            structure.append({
                "id": f"{La}{Lb}_{n}", "name": f"Beam_{La}{Lb}_{n}",
                "geometry": [[x1, y], [x2, y]],
                "attributes": {
                    "type": "perimeter", "length": str(round(x2 - x1, 3)),
                    "depth": "300", "width": "200",
                    "isWallAligned": "True", "structuralRole": "primary",
                    "material": "RCC", "conflict": "None",
                },
            })

    for xi, x in enumerate(x_pos):
        L = letters[xi]
        for yi in range(len(y_pos) - 1):
            na, nb = nums[yi], nums[yi + 1]
            y1, y2 = y_pos[yi], y_pos[yi + 1]
            structure.append({
                "id": f"{L}_{na}{nb}", "name": f"Beam_{L}_{na}{nb}",
                "geometry": [[x, y1], [x, y2]],
                "attributes": {
                    "type": "perimeter", "length": str(round(y2 - y1, 3)),
                    "depth": "300", "width": "200",
                    "isWallAligned": "True", "structuralRole": "primary",
                    "material": "RCC", "conflict": "None",
                },
            })

    layout["structure"] = structure
    return json.dumps(layout)


def _pt_eq(a: list, b: list, tol: float = 0.05) -> bool:
    return all(abs(float(a[i]) - float(b[i])) < tol for i in range(min(len(a), len(b))))


def _remove_element_from_structure(element_id: str, structure: list) -> list:
    """Core removal logic operating on a flat structure list. Returns the updated list."""
    import math
    target = next((e for e in structure if e["id"] == element_id), None)
    if target is None:
        return structure

    is_column = len(target.get("geometry", [])) == 1

    if not is_column:
        print(f"  Removed beam {element_id}")
        return [e for e in structure if e["id"] != element_id]

    col_pos = target["geometry"][0]
    connected = [
        e for e in structure
        if len(e.get("geometry", [])) == 2
        and (_pt_eq(e["geometry"][0], col_pos) or _pt_eq(e["geometry"][1], col_pos))
    ]

    used: set = set()
    merged_beams: list = []

    for b1 in connected:
        if b1["id"] in used:
            continue
        far1 = b1["geometry"][1] if _pt_eq(b1["geometry"][0], col_pos) else b1["geometry"][0]
        partner = None
        far2_pt = None
        for b2 in connected:
            if b2["id"] == b1["id"] or b2["id"] in used:
                continue
            far2 = b2["geometry"][1] if _pt_eq(b2["geometry"][0], col_pos) else b2["geometry"][0]
            if _pt_eq(far1, far2):
                continue
            dx1 = float(far1[0]) - float(col_pos[0])
            dy1 = float(far1[1]) - float(col_pos[1])
            dx2 = float(far2[0]) - float(col_pos[0])
            dy2 = float(far2[1]) - float(col_pos[1])
            L1  = math.hypot(dx1, dy1)
            L2  = math.hypot(dx2, dy2)
            if L1 < 1e-6 or L2 < 1e-6:
                continue
            cross = abs(dx1 * dy2 - dy1 * dx2) / (L1 * L2)
            dot   = (dx1 * dx2 + dy1 * dy2) / (L1 * L2)
            if cross < 0.15 and dot < 0:
                partner  = b2
                far2_pt  = far2
                break
        if partner:
            merged_attrs = dict(b1.get("attributes", {}))
            merged_attrs["length"] = round(math.dist(far1, far2_pt), 3)
            merged_beams.append({
                "id":         b1["id"],
                "name":       b1.get("name", b1["id"]),
                "geometry":   [far1, far2_pt],
                "attributes": merged_attrs,
            })
            used.add(b1["id"])
            used.add(partner["id"])
            print(f"    Merged {b1['id']} + {partner['id']} -> {b1['id']} (span {round(math.dist(far1, far2_pt), 2)}m)")
        else:
            used.add(b1["id"])
            print(f"    Removed dead-end beam {b1['id']}")

    ids_to_remove = {element_id} | used
    new_structure = [e for e in structure if e["id"] not in ids_to_remove]
    new_structure.extend(merged_beams)
    print(f"  Removed column {element_id} — {len(merged_beams)} beam(s) merged, {len(used)-len(merged_beams)} removed")
    return new_structure


def remove_element(layout_json_string: str, element_id: str, force: bool = False,
                   level_key: str | None = None) -> str:
    """Remove a structural element. For columns: merge collinear beams through the removed point.
    For multilevel: also blocks removal if a column exists directly above (load path broken).
    Perimeter elements are locked by default; pass force=True to remove them anyway.
    `level_key` pins the removal to one floor (ids repeat across floors); omit to search all."""
    from nodes._layout import is_multilevel, find_element_in_layout, has_column_above
    data = json.loads(layout_json_string)

    if is_multilevel(data):
        if level_key and level_key in data.get("levels", {}):
            target = next((e for e in data["levels"][level_key].get("structure", [])
                           if e.get("id") == element_id), None)
        else:
            level_key, target = find_element_in_layout(data, element_id)
        if target is None:
            return layout_json_string
        is_column = len(target.get("geometry", [])) == 1
        el_type = (target.get("attributes") or {}).get("type", "")
        if el_type == "perimeter" and not force:
            kind = "column" if is_column else "beam"
            print(f"  Cannot remove {element_id}: perimeter {kind} defines the building envelope — locked.")
            return layout_json_string
        if is_column:
            if has_column_above(data, target["geometry"][0], level_key):
                print(f"  Note: {element_id} at {level_key} has a column above — the spanning beam will become a transfer beam carrying that upper column as a point load.")
        structure = data["levels"][level_key].get("structure", [])
        data["levels"][level_key]["structure"] = _remove_element_from_structure(element_id, structure)
        return json.dumps(data, indent=2, ensure_ascii=False)

    _sl_target = next((e for e in data.get("structure", []) if e.get("id") == element_id), None)
    if _sl_target is not None and ((_sl_target.get("attributes") or {}).get("type") == "perimeter") and not force:
        kind = "column" if len(_sl_target.get("geometry", [])) == 1 else "beam"
        print(f"  Cannot remove {element_id}: perimeter {kind} defines the building envelope — locked.")
        return layout_json_string
    data["structure"] = _remove_element_from_structure(element_id, data.get("structure", []))
    return json.dumps(data, indent=2, ensure_ascii=False)


def move_element(layout_json_string: str, element_id: str,
                 dx: float = 0.0, dy: float = 0.0,
                 x: float | None = None, y: float | None = None) -> str:
    """Move a structural element and reconnect everything joined to it.

    Columns (1-pt geometry): translate the point by (dx, dy) metres, or place it
    at absolute (x, y). Every beam endpoint sitting on the old column point follows
    it, so beams stay connected. Keep the move axis-aligned (only dx OR only dy) to
    preserve an orthogonal grid — this is the precise way to clear a window/door
    clash or fine-tune column spacing.

    Beams (2-pt geometry): the whole beam is translated by (dx, dy).

    Returns the updated layout JSON (unchanged if the id is not found)."""
    from nodes._layout import is_multilevel, find_element_in_layout
    data = json.loads(layout_json_string)
    dx = float(dx or 0.0)
    dy = float(dy or 0.0)

    if is_multilevel(data):
        level_key, target = find_element_in_layout(data, element_id)
        if target is None:
            return layout_json_string
        struct = data["levels"][level_key].get("structure", [])
    else:
        struct = data.get("structure", [])
        target = next((e for e in struct if e.get("id") == element_id), None)
        if target is None:
            return layout_json_string

    g = target.get("geometry", [])
    if len(g) == 1:
        old = [g[0][0], g[0][1]]
        nx = round(float(x) if x is not None else old[0] + dx, 3)
        ny = round(float(y) if y is not None else old[1] + dy, 3)
        target["geometry"][0] = [nx, ny]
        # reconnect any beam endpoint that sat on the old column point
        for b in struct:
            bg = b.get("geometry", [])
            if len(bg) == 2:
                for i in (0, 1):
                    if abs(bg[i][0] - old[0]) < 0.02 and abs(bg[i][1] - old[1]) < 0.02:
                        bg[i] = [nx, ny]
    elif len(g) == 2:
        ddx = (float(x) - g[0][0]) if x is not None else dx
        ddy = (float(y) - g[0][1]) if y is not None else dy
        target["geometry"][0] = [round(g[0][0] + ddx, 3), round(g[0][1] + ddy, 3)]
        target["geometry"][1] = [round(g[1][0] + ddx, 3), round(g[1][1] + ddy, 3)]
    else:
        return layout_json_string

    return json.dumps(data, indent=2, ensure_ascii=False)


def _next_id(all_ids: set, prefix: str) -> str:
    n = 1
    while f"{prefix}{n}" in all_ids:
        n += 1
    return f"{prefix}{n}"


def _level_struct_for(data: dict, element_id: str, level_key):
    """Return (level_key, structure_list) where element_id lives (level-aware)."""
    from nodes._layout import is_multilevel, get_level_keys
    if not is_multilevel(data):
        return None, data.get("structure", [])
    if level_key and level_key in data.get("levels", {}):
        s = data["levels"][level_key].get("structure", [])
        if any(e.get("id") == element_id for e in s):
            return level_key, s
    for lk in get_level_keys(data):
        s = data["levels"][lk].get("structure", [])
        if any(e.get("id") == element_id for e in s):
            return lk, s
    return None, None


def add_column_at_offset(layout_json_string: str, reference_id: str,
                         dx: float = 0.0, dy: float = 0.0,
                         level_key: str | None = None,
                         material: str | None = None) -> str:
    """Add a new internal column offset (dx, dy) metres from a REFERENCE column, measured
    along the axes from that column (dx → X, dy → Y). A column is a point, so this is
    orthogonal by construction. Returns updated layout JSON (unchanged if ref not found)."""
    data = json.loads(layout_json_string)
    dx = float(dx or 0.0); dy = float(dy or 0.0)
    lk, struct = _level_struct_for(data, reference_id, level_key)
    if struct is None:
        return layout_json_string
    ref = next((e for e in struct if e.get("id") == reference_id
                and len(e.get("geometry", [])) == 1), None)
    if ref is None:
        return layout_json_string
    rx, ry = ref["geometry"][0]
    nx, ny = round(rx + dx, 3), round(ry + dy, 3)
    new_id = _next_id({e.get("id") for e in struct}, "NC")
    mat = material or (ref.get("attributes") or {}).get("material")
    struct.append({
        "id": new_id,
        "name": f"Col_{new_id}",
        "geometry": [[nx, ny]],
        "attributes": {"type": "internal", **({"material": mat} if mat else {})},
    })
    return json.dumps(data, indent=2, ensure_ascii=False)


def add_beam(layout_json_string: str, col_a_id: str, col_b_id: str,
             level_key: str | None = None, material: str | None = None,
             tol: float = 0.05) -> str:
    """Add an ORTHOGONAL beam between two existing columns. The columns must share an X
    (vertical beam) or a Y (horizontal beam); the beam is snapped to be perfectly
    orthogonal. Diagonal pairs are REJECTED — returns the layout unchanged (so the caller
    can detect the no-op). Both columns must be on the same level."""
    from nodes._layout import is_multilevel, get_level_keys

    def _find(struct, cid):
        return next((e for e in struct if e.get("id") == cid
                     and len(e.get("geometry", [])) == 1), None)

    data = json.loads(layout_json_string)
    if is_multilevel(data):
        struct = None
        for lk in ([level_key] if level_key else get_level_keys(data)):
            s = data["levels"].get(lk, {}).get("structure", [])
            if _find(s, col_a_id) and _find(s, col_b_id):
                struct = s; break
        if struct is None:
            return layout_json_string
    else:
        struct = data.get("structure", [])
        if not (_find(struct, col_a_id) and _find(struct, col_b_id)):
            return layout_json_string

    a = _find(struct, col_a_id)["geometry"][0]
    b = _find(struct, col_b_id)["geometry"][0]
    _dx, _dy = abs(a[0] - b[0]), abs(a[1] - b[1])
    if _dx <= tol and _dy <= tol:
        return layout_json_string           # same point
    if _dx > tol and _dy > tol:
        return layout_json_string           # diagonal — never allowed
    if _dx <= tol:                          # vertical beam — share averaged x
        x = round((a[0] + b[0]) / 2, 3)
        geom = [[x, a[1]], [x, b[1]]]
    else:                                   # horizontal beam — share averaged y
        y = round((a[1] + b[1]) / 2, 3)
        geom = [[a[0], y], [b[0], y]]
    new_id = _next_id({e.get("id") for e in struct}, "NB")
    mat = material or (_find(struct, col_a_id).get("attributes") or {}).get("material")
    struct.append({
        "id": new_id,
        "name": f"Beam_{col_a_id}_{col_b_id}",
        "geometry": geom,
        "attributes": {"type": "internal", **({"material": mat} if mat else {})},
    })
    return json.dumps(data, indent=2, ensure_ascii=False)


# ── Opening-aware grid (orthogonal clash resolution) ──────────────────────────

def _seg_pt_dist(p, a, b) -> float:
    """Distance from point p to segment a-b."""
    ax, ay = a; bx, by = b; px, py = p
    dx, dy = bx - ax, by - ay
    if dx == 0 and dy == 0:
        return ((px - ax) ** 2 + (py - ay) ** 2) ** 0.5
    t = max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / (dx * dx + dy * dy)))
    qx, qy = ax + t * dx, ay + t * dy
    return ((px - qx) ** 2 + (py - qy) ** 2) ** 0.5


def _level_openings(layout: dict, level_key) -> list:
    """Door/window segments [(p0, p1), …] for a level (or single-level layout)."""
    from nodes._layout import is_multilevel
    lvl = layout["levels"].get(level_key, {}) if (is_multilevel(layout) and level_key) else layout
    segs = []
    for o in (lvl.get("doors", []) or []) + (lvl.get("windows", []) or []):
        g = o.get("geometry", [])
        if len(g) >= 2:
            segs.append((g[0], g[1]))
    return segs


def _clashing_columns(struct: list, openings: list, tol: float) -> list:
    return [el for el in struct
            if len(el.get("geometry", [])) == 1
            and any(_seg_pt_dist(el["geometry"][0], a, b) < tol for a, b in openings)]


def resolve_clashes_orthogonal(layout_json_string: str, level_key: str | None = None,
                               tol: float = 0.3, margin: float = 0.25,
                               max_shift: float = 1.5) -> tuple[str, int]:
    """Slide WHOLE grid-lines so columns/beams clear door/window openings while staying
    perfectly orthogonal (never a diagonal single-column nudge).

    A horizontal opening is cleared by shifting the clashing column's VERTICAL grid-line
    in x (the column slides along its wall, past the opening); a vertical opening by
    shifting the HORIZONTAL grid-line in y. Shifting a whole line moves every point at
    that coordinate (columns + beam endpoints) across ALL levels, so beams stay
    orthogonal (they just change length) and columns stay vertically stacked.

    Returns (layout_json, n_lines_moved). A move is kept only if it lowers the total
    clash count; otherwise it is reverted and the column is marked unresolvable."""
    from nodes._layout import is_multilevel, get_level_keys
    data = json.loads(layout_json_string)

    if is_multilevel(data):
        lks = [level_key] if level_key else get_level_keys(data)
        structs = {lk: data["levels"][lk].get("structure", []) for lk in lks}
        openings = {lk: _level_openings(data, lk) for lk in lks}
    else:
        structs = {None: data.get("structure", [])}
        openings = {None: _level_openings(data, None)}

    if not any(openings.values()):
        return json.dumps(data, indent=2, ensure_ascii=False), 0

    def total_clashes() -> int:
        return sum(len(_clashing_columns(s, openings[lk], tol)) for lk, s in structs.items())

    def shift_all(axis: str, coord: float, d: float) -> None:
        i = 0 if axis == "x" else 1
        for s in structs.values():
            for el in s:
                for pt in el.get("geometry", []):
                    if abs(pt[i] - coord) < 0.02:
                        pt[i] = round(pt[i] + d, 3)

    def _is_perim(el: dict) -> bool:
        return (el.get("attributes") or {}).get("type") == "perimeter"

    def line_has_perimeter(axis: str, coord: float) -> bool:
        """True if a perimeter column sits on this grid-line — shifting it would pull
        the building envelope off the outline, so such lines are never moved."""
        i = 0 if axis == "x" else 1
        for s in structs.values():
            for el in s:
                g = el.get("geometry", [])
                if len(g) == 1 and _is_perim(el) and abs(g[0][i] - coord) < 0.02:
                    return True
        return False

    stuck: set = set()
    moved = 0
    for _ in range(80):
        if total_clashes() == 0:
            break
        # next clashing INTERNAL column not already given up on (perimeter cols are
        # envelope-locked — they define the outline and are never moved).
        target = None
        for lk, s in structs.items():
            for c in _clashing_columns(s, openings[lk], tol):
                if _is_perim(c):
                    continue
                if (lk, c.get("id")) not in stuck:
                    target = (lk, c); break
            if target:
                break
        if target is None:
            break
        lk, c = target
        cx, cy = c["geometry"][0]
        before = total_clashes()

        cands = []
        for (a, b) in openings[lk]:
            if _seg_pt_dist([cx, cy], a, b) >= tol:
                continue
            if abs(a[1] - b[1]) < 1e-6:          # horizontal opening → slide column in x
                lo = min(a[0], b[0]) - tol - margin
                hi = max(a[0], b[0]) + tol + margin
                cands += [("x", cx, lo - cx), ("x", cx, hi - cx)]
            elif abs(a[0] - b[0]) < 1e-6:        # vertical opening → slide column in y
                lo = min(a[1], b[1]) - tol - margin
                hi = max(a[1], b[1]) + tol + margin
                cands += [("y", cy, lo - cy), ("y", cy, hi - cy)]
        # never shift a line that carries a perimeter column (would break the outline)
        cands = [t for t in cands
                 if 1e-6 < abs(t[2]) <= max_shift and not line_has_perimeter(t[0], t[1])]
        cands.sort(key=lambda t: abs(t[2]))

        applied = False
        for axis, coord, d in cands:
            shift_all(axis, coord, d)
            if total_clashes() < before:
                moved += 1; applied = True; break
            shift_all(axis, coord + d, -d)       # revert
        if not applied:
            stuck.add((lk, c.get("id")))

    return json.dumps(data, indent=2, ensure_ascii=False), moved


# ── Modify node ───────────────────────────────────────────────────────────────

def build_modify_node(mcp_client, allowed_tools, edited_layout_path, evaluate_fn=None):

    allowed_names = {t["name"] for t in allowed_tools if t.get("name")}

    def modify_node(state: dict) -> dict:
        print(f"\n{'='*50}")
        print(f"  NODE: MODIFY")
        print(f"{'='*50}")

        if not state.get("original_layout_json_string"):
            state["original_layout_json_string"] = state["layout_json_string"]

        # Save before-snapshot of current layout before applying any change
        before_path = edited_layout_path.with_stem(edited_layout_path.stem + "_before")
        before_path.write_text(state["layout_json_string"], encoding="utf-8")

        # ── Structural change from evaluate failure menu ───────────────────────
        change = state.get("pending_structural_change")
        if change:
            layout_str = state["layout_json_string"]
            t = change["type"]
            print(f"  Applying structural change: {t}")

            if t == "tier_upgrade":
                layout_str = apply_material_override(layout_str, change["tier"])
                state["material_override"] = change["tier"]

            elif t == "material_switch":
                layout_str = apply_material_override(layout_str, change["material"])
                state["material_override"] = change["material"]

            elif t == "upgrade_element":
                layout_str = upgrade_element_section(layout_str, change["element_id"], change["new_section"])

            elif t == "midspan_column":
                layout_str = add_midspan_column(layout_str, change["beam_id"], change["material"])
                print(f"  Added midspan column under {change['beam_id']} -> {change['beam_id']}a / {change['beam_id']}b")

            elif t == "auto_upgrade_beams":
                ll  = state.get("live_load_kNm2", 2.0)
                sdl = state.get("sdl_kNm2", 3.5)
                result = json.loads(state.get("evaluation_result", "{}"))
                print("  Upgrading failing beams through section sizes until PASS...")
                if evaluate_fn:
                    for _ in range(6):
                        beam_fails = [
                            b for b in result.get("beams", [])
                            if not (b["bend_PASS"] and b["shear_PASS"] and b["defl_TL_PASS"] and b["defl_LL_PASS"])
                        ]
                        if not beam_fails:
                            break
                        upgraded = False
                        for b in beam_fails:
                            cur = b.get("section_mm", "")
                            if cur in BEAM_SECTION_UPGRADE:
                                nxt, _, _ = BEAM_SECTION_UPGRADE[cur]
                                layout_str = upgrade_element_section(layout_str, b["id"], nxt)
                                print(f"    {b['id']}: {cur} -> {nxt}")
                                upgraded = True
                            elif cur in BEAM_DIM_UPGRADE:
                                nxt, _, _ = BEAM_DIM_UPGRADE[cur]
                                layout_str = upgrade_element_section(layout_str, b["id"], nxt)
                                print(f"    {b['id']}: {cur} -> {nxt}")
                                upgraded = True
                        if not upgraded:
                            break
                        result = evaluate_fn(layout_str, ll, sdl)
                else:
                    for b in result.get("beams", []):
                        if b["bend_PASS"] and b["shear_PASS"] and b["defl_TL_PASS"] and b["defl_LL_PASS"]:
                            continue
                        cur = b.get("section_mm", "")
                        if cur in BEAM_SECTION_UPGRADE:
                            nxt, _, _ = BEAM_SECTION_UPGRADE[cur]
                            layout_str = upgrade_element_section(layout_str, b["id"], nxt)
                            print(f"    {b['id']}: {cur} -> {nxt}")
                        elif cur in BEAM_DIM_UPGRADE:
                            nxt, _, _ = BEAM_DIM_UPGRADE[cur]
                            layout_str = upgrade_element_section(layout_str, b["id"], nxt)
                            print(f"    {b['id']}: {cur} -> {nxt}")

            elif t == "auto_upgrade_columns":
                ll  = state.get("live_load_kNm2", 2.0)
                sdl = state.get("sdl_kNm2", 3.5)
                result = json.loads(state.get("evaluation_result", "{}"))
                print("  Upgrading failing columns through section sizes until PASS...")
                if evaluate_fn:
                    for _ in range(6):
                        col_fails = [
                            c for c in result.get("columns", [])
                            if not (c["stress_PASS"] and c["buckling_PASS"])
                        ]
                        if not col_fails:
                            break
                        upgraded = False
                        for c in col_fails:
                            cur = c.get("section_mm", "")
                            if cur in COL_SECTION_UPGRADE:
                                nxt, _ = COL_SECTION_UPGRADE[cur]
                                layout_str = upgrade_element_section(layout_str, c["id"], nxt)
                                print(f"    {c['id']}: {cur} -> {nxt}")
                                upgraded = True
                            elif cur in COL_DIM_UPGRADE:
                                nxt = COL_DIM_UPGRADE[cur]
                                layout_str = upgrade_element_section(layout_str, c["id"], nxt)
                                print(f"    {c['id']}: {cur} -> {nxt}")
                                upgraded = True
                        if not upgraded:
                            break
                        result = evaluate_fn(layout_str, ll, sdl)
                else:
                    for c in result.get("columns", []):
                        if c["stress_PASS"] and c["buckling_PASS"]:
                            continue
                        cur = c.get("section_mm", "")
                        if cur in COL_SECTION_UPGRADE:
                            nxt, _ = COL_SECTION_UPGRADE[cur]
                            layout_str = upgrade_element_section(layout_str, c["id"], nxt)
                            print(f"    {c['id']}: {cur} -> {nxt}")
                        elif cur in COL_DIM_UPGRADE:
                            nxt = COL_DIM_UPGRADE[cur]
                            layout_str = upgrade_element_section(layout_str, c["id"], nxt)
                            print(f"    {c['id']}: {cur} -> {nxt}")

            elif t == "find_minimum":
                ll  = state.get("live_load_kNm2", 2.0)
                sdl = state.get("sdl_kNm2", 3.5)
                mat = change["material"]
                print(f"  Applying XS sections for {mat}, finding minimum...")
                layout_str = apply_minimum_sections(layout_str, mat)
                state["material_override"] = mat
                state["find_minimum_done"] = True
                if evaluate_fn:
                    result = evaluate_fn(layout_str, ll, sdl)
                    for _ in range(12):
                        if result["summary"]["overall_PASS"]:
                            break
                        prev = layout_str
                        layout_str = _upgrade_one_pass(layout_str, result)
                        if layout_str == prev:
                            break
                        result = evaluate_fn(layout_str, ll, sdl)

            elif t == "remove_element":
                eid = change["element_id"]
                _before_str = layout_str
                layout_str = remove_element(layout_str, eid)
                if layout_str != _before_str:
                    from nodes._layout import find_element_in_layout as _feil
                    _lk_check, _el_check = _feil(json.loads(layout_str), eid)
                    if _el_check is not None:
                        print(f"  WARNING: {eid} still present at {_lk_check} after removal — check remove_element logic")

            elif t == "remove_elements":
                for eid in change.get("element_ids", []):
                    layout_str = remove_element(layout_str, eid)
                print(f"  Removed {len(change.get('element_ids', []))} elements.")

            state["layout_json_string"] = layout_str
            state["pending_structural_change"] = None
            state["came_from"] = "structural_change"
            write_tool_result(layout_str, edited_layout_path)
            return state

        # ── GH MCP tool calls from reason node ───────────────────────────────
        last_tool = None
        for call in state["pending_tool_calls"]:
            state["iteration"] += 1
            if state["iteration"] > state["max_iterations"]:
                raise RuntimeError("Max iterations exceeded")

            tool_name = call["name"]
            last_tool = tool_name
            if tool_name not in allowed_names:
                raise RuntimeError(f"Tool '{tool_name}' is not in the allowed tools list")

            print(f"Running: {tool_name}")
            tool_args = {k: v for k, v in call["arguments"].items() if v is not None}
            if "layout_json" in tool_args:
                tool_args["layout_json"] = state["layout_json_string"]

            try:
                tool_output = mcp_client.call_tool(tool_name, tool_args)
            except Exception as e:
                print(f"[modify] MCP call failed ({type(e).__name__}) — treating as empty output.")
                tool_output = ""

            if not tool_output or not tool_output.strip():
                print(f"[modify] WARNING: {tool_name} returned empty output — layout unchanged.")

            try:
                _parsed = json.loads(tool_output.strip())
                if isinstance(_parsed, dict) and ("layoutId" in _parsed or "rooms" in _parsed):
                    write_tool_result(tool_output, edited_layout_path)
            except (json.JSONDecodeError, AttributeError):
                pass

            try:
                updated = json.loads(tool_output.strip())
                if isinstance(updated, dict):
                    state["layout_json_string"] = json.dumps(updated)
            except (json.JSONDecodeError, AttributeError):
                pass

            state["messages"].append({
                "role": "assistant",
                "content": json.dumps({
                    "action": "tool", "final_response": "",
                    "tool_calls": [{"name": tool_name, "arguments": tool_args}],
                }),
            })
            state["messages"].append({
                "role": "user",
                "content": f"Tool result: {tool_output}",
            })
            print(f"Tool result: {tool_output[:200]}..." if len(tool_output) > 200 else f"Tool result: {tool_output}")

        state["pending_tool_calls"] = None
        state["came_from"] = "modify"
        return state

    return modify_node
