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
    "RCC":       {"beam_depth_mm": 300, "beam_width_mm": 200, "col_dims": "200x200"},
    "RCC_M":     {"beam_depth_mm": 450, "beam_width_mm": 250, "col_dims": "250x250"},
    "RCC_L":     {"beam_depth_mm": 600, "beam_width_mm": 300, "col_dims": "300x300"},
    "RCC_XL":    {"beam_depth_mm": 700, "beam_width_mm": 350, "col_dims": "350x350"},
    "RCC_XXL":   {"beam_depth_mm": 800, "beam_width_mm": 400, "col_dims": "400x400"},
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
    "150x200": ("200x300", 300, 200),
    "200x300": ("250x450", 450, 250),
    "250x450": ("300x600", 600, 300),
    "300x600": ("350x700", 700, 350),
    "350x700": ("400x800", 800, 400),
    "75x150":  ("100x240", 240, 100),
    "100x240": ("120x300", 300, 120),
    "120x300": ("150x360", 360, 150),
    "150x360": ("200x480", 480, 200),
    "200x480": ("250x600", 600, 250),
}

COL_DIM_UPGRADE: dict[str, str] = {
    "75x75":   "100x100",
    "100x100": "120x120",
    "120x120": "150x150",
    "150x150": "200x200",
    "200x200": "250x250",
    "250x250": "300x300",
    "300x300": "350x350",
    "350x350": "400x400",
}

BASE_MATERIALS = ["RCC", "STEEL", "TIMBER"]


# ── Layout mutation functions ─────────────────────────────────────────────────

def apply_material_override(layout_json_string: str, material: str) -> str:
    """Patch all structure elements with the given material and its default sections."""
    layout = json.loads(layout_json_string)
    sec = DEFAULT_SECTIONS.get(material, DEFAULT_SECTIONS["RCC"])
    is_steel = "STEEL" in material.upper()
    for el in layout.get("structure", []):
        attrs = el.setdefault("attributes", {})
        attrs["material"] = material
        if len(el.get("geometry", [])) == 2:
            attrs["depth"] = str(sec["beam_depth_mm"])
            attrs["width"] = str(sec["beam_width_mm"])
            if is_steel and "beam_section" in sec:
                attrs["section"] = sec["beam_section"]
            else:
                attrs.pop("section", None)
        else:
            attrs["dimensions"] = sec["col_dims"]
            if is_steel and "col_section" in sec:
                attrs["section"] = sec["col_section"]
            else:
                attrs.pop("section", None)
    return json.dumps(layout)


def upgrade_element_section(layout_str: str, element_id: str, new_section: str) -> str:
    """Update a single structural element's section in the layout JSON."""
    _BEAM_DIMS = {
        "IPE120": (120,  64), "IPE160": (160,  82), "IPE200": (200, 100),
        "IPE240": (240, 120), "IPE300": (300, 150), "IPE360": (360, 170),
    }
    _COL_DIMS = {
        "HSS80x80x5": "80x80", "HSS100x100x6": "100x100", "HSS120x120x6": "120x120",
        "HSS150x150x6": "150x150", "HSS180x180x8": "180x180", "HSS200x200x8": "200x200",
    }
    layout = json.loads(layout_str)
    for el in layout.get("structure", []):
        if el["id"] == element_id:
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
            break
    return json.dumps(layout)


def add_midspan_column(layout_str: str, beam_id: str, material: str) -> str:
    """Split a beam at its midpoint and insert a new column there."""
    sec = DEFAULT_SECTIONS.get(material, DEFAULT_SECTIONS["RCC"])
    layout = json.loads(layout_str)
    structure = layout.get("structure", [])
    beam = next((e for e in structure if e["id"] == beam_id and len(e.get("geometry", [])) == 2), None)
    if not beam:
        return layout_str
    p1, p2 = beam["geometry"]
    mid = [round((p1[0] + p2[0]) / 2, 3), round((p1[1] + p2[1]) / 2, 3)]
    bat = beam.get("attributes", {})
    new_col = {
        "id": f"{beam_id}_M", "name": f"Column_{beam_id}_M",
        "geometry": [mid],
        "attributes": {
            "type": "interior", "dimensions": sec["col_dims"],
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
    layout["structure"] = new_structure
    return json.dumps(layout)


def apply_minimum_sections(layout_str: str, base_material: str) -> str:
    """Apply XS tier sections for base_material to all elements, keeping base material name."""
    xs_key = f"{base_material}_XS"
    sec = DEFAULT_SECTIONS.get(xs_key, DEFAULT_SECTIONS[base_material])
    is_steel = "STEEL" in base_material.upper()
    layout = json.loads(layout_str)
    for el in layout.get("structure", []):
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
            print(f"  Min {b['id']}: {cur} → {nxt}")
        elif cur in BEAM_DIM_UPGRADE:
            nxt, _, _ = BEAM_DIM_UPGRADE[cur]
            layout_str = upgrade_element_section(layout_str, b["id"], nxt)
            print(f"  Min {b['id']}: {cur} → {nxt}")
    for c in evaluation_result.get("columns", []):
        if c["stress_PASS"] and c["buckling_PASS"]:
            continue
        cur = c.get("section_mm", "")
        if cur in COL_SECTION_UPGRADE:
            nxt, _ = COL_SECTION_UPGRADE[cur]
            layout_str = upgrade_element_section(layout_str, c["id"], nxt)
            print(f"  Min {c['id']}: {cur} → {nxt}")
        elif cur in COL_DIM_UPGRADE:
            nxt = COL_DIM_UPGRADE[cur]
            layout_str = upgrade_element_section(layout_str, c["id"], nxt)
            print(f"  Min {c['id']}: {cur} → {nxt}")
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


def remove_element(layout_json_string: str, element_id: str) -> str:
    """Remove a structural element. For columns: merge collinear beams through the removed point."""
    import math
    data      = json.loads(layout_json_string)
    structure = data.get("structure", [])

    target = next((e for e in structure if e["id"] == element_id), None)
    if target is None:
        return layout_json_string

    is_column = len(target.get("geometry", [])) == 1

    if is_column:
        col_pos = target["geometry"][0]

        # All beams that touch this column
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

            # Find a collinear partner: vectors from col to far1 and col to far2 must be anti-parallel
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
                if cross < 0.15 and dot < 0:   # collinear and opposite directions
                    partner  = b2
                    far2_pt  = far2
                    break

            if partner:
                merged_beams.append({
                    "id":         b1["id"],
                    "name":       b1.get("name", b1["id"]),
                    "geometry":   [far1, far2_pt],
                    "attributes": dict(b1.get("attributes", {})),
                })
                used.add(b1["id"])
                used.add(partner["id"])
                print(f"    Merged {b1['id']} + {partner['id']} → {b1['id']} (span {round(math.dist(far1, far2_pt), 2)}m)")
            else:
                # Dead-end beam — remove with the column
                used.add(b1["id"])
                print(f"    Removed dead-end beam {b1['id']}")

        ids_to_remove = {element_id} | used
        new_structure  = [e for e in structure if e["id"] not in ids_to_remove]
        new_structure.extend(merged_beams)
        data["structure"] = new_structure
        print(f"  Removed column {element_id} — {len(merged_beams)} beam(s) merged, {len(used)-len(merged_beams)} removed")
    else:
        # Just remove a beam
        data["structure"] = [e for e in structure if e["id"] != element_id]
        print(f"  Removed beam {element_id}")

    return json.dumps(data, indent=2, ensure_ascii=False)


# ── Modify node ───────────────────────────────────────────────────────────────

def build_modify_node(mcp_client, allowed_tools, edited_layout_path, evaluate_fn=None):

    allowed_names = {t["name"] for t in allowed_tools if t.get("name")}

    def modify_node(state: dict) -> dict:
        print(f"\n{'='*50}")
        print(f"  NODE: MODIFY")
        print(f"{'='*50}")

        if not state.get("original_layout_json_string"):
            state["original_layout_json_string"] = state["layout_json_string"]

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
                print(f"  Added midspan column under {change['beam_id']} → {change['beam_id']}a / {change['beam_id']}b")

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
                                print(f"    {b['id']}: {cur} → {nxt}")
                                upgraded = True
                            elif cur in BEAM_DIM_UPGRADE:
                                nxt, _, _ = BEAM_DIM_UPGRADE[cur]
                                layout_str = upgrade_element_section(layout_str, b["id"], nxt)
                                print(f"    {b['id']}: {cur} → {nxt}")
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
                            print(f"    {b['id']}: {cur} → {nxt}")
                        elif cur in BEAM_DIM_UPGRADE:
                            nxt, _, _ = BEAM_DIM_UPGRADE[cur]
                            layout_str = upgrade_element_section(layout_str, b["id"], nxt)
                            print(f"    {b['id']}: {cur} → {nxt}")

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
                                print(f"    {c['id']}: {cur} → {nxt}")
                                upgraded = True
                            elif cur in COL_DIM_UPGRADE:
                                nxt = COL_DIM_UPGRADE[cur]
                                layout_str = upgrade_element_section(layout_str, c["id"], nxt)
                                print(f"    {c['id']}: {cur} → {nxt}")
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
                            print(f"    {c['id']}: {cur} → {nxt}")
                        elif cur in COL_DIM_UPGRADE:
                            nxt = COL_DIM_UPGRADE[cur]
                            layout_str = upgrade_element_section(layout_str, c["id"], nxt)
                            print(f"    {c['id']}: {cur} → {nxt}")

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
                layout_str = remove_element(layout_str, change["element_id"])

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

            print(f"Calling tool: {tool_name} with arguments: {call['arguments']}")
            tool_args = {k: v for k, v in call["arguments"].items() if v is not None}
            if "layout_json" in tool_args:
                tool_args["layout_json"] = state["layout_json_string"]

            try:
                tool_output = mcp_client.call_tool(tool_name, tool_args)
            except Exception as e:
                print(f"[modify] MCP call failed ({type(e).__name__}) — treating as empty output.")
                tool_output = ""

            if not tool_output or not tool_output.strip():
                if tool_name == "tag_and_audit":
                    spacing = float(tool_args.get("grid_spacing", 4.0))
                    tool_output = _generate_column_grid(state["layout_json_string"], spacing)
                    print(f"[modify] GH unavailable — generated column grid in Python (spacing={spacing}m)")
                else:
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
        state["came_from"] = "tag_and_audit" if last_tool == "tag_and_audit" else "modify"
        return state

    return modify_node
