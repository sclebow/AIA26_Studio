"""
compute_comfort_scores — 6-sense comfort scoring per room, persona-weighted.

Migrated verbatim from the Grasshopper cluster script. Logic is unchanged; only
the GH input variables (layout_json, persona, room_ids) became function
parameters and the GH output variable `a` became the return value.
"""

import json


def compute_comfort_scores(layout_json, persona=None, room_ids=None):
    """Return a JSON string of per-room comfort scores for the given persona.

    Args:
        layout_json: the layout as a JSON string.
        persona: persona label (e.g. "Elderly 65+"); defaults to "Neutral".
        room_ids: "all" or a comma-separated list of room ids; defaults to "all".

    Returns:
        JSON string: {"layoutId", "persona", "rooms": [...]}  (or {"error": ...}).
    """
    layout = None
    try:
        layout = json.loads(layout_json)
    except Exception:
        return json.dumps({"error": "Invalid layout_json"})

    rooms = layout.get("rooms", [])
    persona_str = str(persona).strip() if persona else "Neutral"
    room_ids_str = str(room_ids).strip() if room_ids else "all"
    target_ids = [r.get("id") for r in rooms] if room_ids_str.lower() == "all" else [x.strip() for x in room_ids_str.split(",")]

    BASELINES = {
        "bedroom":     {"thermal":0.75,"visual":0.65,"acoustic":0.70,"spatial":0.65,"olfactory":0.80,"tactile":0.70},
        "living":      {"thermal":0.70,"visual":0.80,"acoustic":0.55,"spatial":0.75,"olfactory":0.70,"tactile":0.65},
        "kitchen":     {"thermal":0.50,"visual":0.70,"acoustic":0.45,"spatial":0.60,"olfactory":0.35,"tactile":0.60},
        "bathroom":    {"thermal":0.60,"visual":0.55,"acoustic":0.70,"spatial":0.45,"olfactory":0.45,"tactile":0.65},
        "circulation": {"thermal":0.65,"visual":0.55,"acoustic":0.65,"spatial":0.50,"olfactory":0.70,"tactile":0.55},
        "dining":      {"thermal":0.65,"visual":0.75,"acoustic":0.55,"spatial":0.65,"olfactory":0.60,"tactile":0.60},
        "utility":     {"thermal":0.55,"visual":0.50,"acoustic":0.60,"spatial":0.50,"olfactory":0.55,"tactile":0.55},
    }

    # Volume norms = area_norm x standard 2.7m ceiling
    VOLUME_NORMS = {
        "bedroom":48.6,"living":81.0,"kitchen":32.4,
        "bathroom":13.5,"circulation":16.2,"dining":40.5,"utility":10.8
    }

    PERSONA_W = {
        "Elderly 65+":      {"thermal":1.2,"visual":1.1,"acoustic":1.3,"spatial":1.0,"olfactory":1.0,"tactile":1.1},
        "Child under 12":   {"thermal":1.0,"visual":1.0,"acoustic":1.1,"spatial":1.2,"olfactory":0.9,"tactile":1.2},
        "Sensory Sensitive":{"thermal":1.3,"visual":1.2,"acoustic":1.4,"spatial":1.1,"olfactory":1.3,"tactile":1.3},
        "Young Active":     {"thermal":0.9,"visual":1.0,"acoustic":0.9,"spatial":1.1,"olfactory":0.9,"tactile":0.9},
        "Neutral":          {"thermal":1.0,"visual":1.0,"acoustic":1.0,"spatial":1.0,"olfactory":1.0,"tactile":1.0},
    }

    # Tactile warmth by material (thermal effusivity-based, from Velt et al. 2012)
    MATERIAL_SCORE = {
        "metal":0.10,"glass":0.20,"concrete":0.25,"stone":0.30,
        "ceramic":0.35,"brick":0.50,"plaster":0.55,"cork":0.70,
        "wood":0.75,"fabric":0.80,"carpet":0.85,"natural":0.75
    }

    ORIENTATION_BONUS = {
        "S":0.05,"SE":0.04,"SW":0.04,
        "E":0.02,"W":0.02,
        "N":-0.03,"NE":-0.02,"NW":-0.02
    }

    weights = PERSONA_W.get(persona_str, PERSONA_W["Neutral"])

    # -- Build door adjacency map --
    adj = {}
    for d in layout.get("doors", []):
        conn = d.get("attributes", {}).get("connectsRooms", [])
        if len(conn) == 2:
            adj.setdefault(conn[0], []).append(conn[1])
            adj.setdefault(conn[1], []).append(conn[0])
    rtype = {r.get("id"): r.get("attributes", {}).get("roomType", "living") for r in rooms}

    # -- Build window map: roomId -> list of window attributes --
    window_map = {}
    for w in layout.get("windows", []):
        wrid = w.get("attributes", {}).get("roomId")
        if wrid:
            window_map.setdefault(wrid, []).append(w.get("attributes", {}))

    # -- Build furniture map: roomId -> list of furniture attribute dicts --
    SOFT_FURNITURE = {"sofa", "bed", "armchair", "rug", "cushion", "couch"}
    HARD_FURNITURE = {"table", "island", "desk", "shelf", "counter", "cabinet", "storage", "dresser"}
    furniture_by_room = {}
    for f in layout.get("furniture", []):
        frid = f.get("attributes", {}).get("roomId")
        if frid:
            furniture_by_room.setdefault(frid, []).append(f.get("attributes", {}))

    # -- Wall material: global average (walls have no roomId) --
    wall_mats = [w.get("attributes", {}).get("material", "plaster").lower() for w in layout.get("structure", [])]
    wall_mat_scores = [MATERIAL_SCORE.get(m, 0.55) for m in wall_mats if m]
    avg_wall_mat = (sum(wall_mat_scores) / len(wall_mat_scores)) if wall_mat_scores else 0.55

    results = []
    for room in rooms:
        rid = room.get("id")
        if rid not in target_ids:
            continue

        rt          = room.get("attributes", {}).get("roomType", "living")
        area        = float(room.get("attributes", {}).get("area", 10))
        height      = float(room.get("attributes", {}).get("height", 2.7))
        orientation = room.get("attributes", {}).get("orientation", "N")
        glaz_ratio  = float(room.get("attributes", {}).get("glazingRatio", 0.10))
        vent_type   = room.get("attributes", {}).get("ventilationType", "natural")

        sc = BASELINES.get(rt, BASELINES["living"]).copy()

        # -- SPATIAL: volume-based --
        sc["spatial"] = round(min(1.0, (area * height) / VOLUME_NORMS.get(rt, 40.5)), 2)

        # -- ACOUSTIC: adjacency penalty --
        noisy = sum(1 for x in adj.get(rid, []) if rtype.get(x) in ["kitchen", "living"])
        if noisy:
            sc["acoustic"] = round(max(0.1, sc["acoustic"] - 0.15 * noisy), 2)

        # -- THERMAL: orientation + glazing type --
        thermal_delta = ORIENTATION_BONUS.get(orientation, 0)
        for win in window_map.get(rid, []):
            gt = win.get("glazingType", "double")
            if gt == "single":
                thermal_delta -= 0.08
            elif gt == "triple":
                thermal_delta += 0.05
        sc["thermal"] = round(max(0.0, min(1.0, sc["thermal"] + thermal_delta)), 2)

        # -- VISUAL: glazing ratio --
        if glaz_ratio < 0.10:
            sc["visual"] = round(max(0.0, sc["visual"] - 0.15), 2)
        elif glaz_ratio >= 0.20:
            sc["visual"] = round(min(1.0, sc["visual"] + 0.08), 2)

        # -- OLFACTORY: ventilation type --
        vent_delta = {"natural":0.05, "mixed":0.0, "mechanical":-0.05}.get(vent_type, 0)
        sc["olfactory"] = round(max(0.0, min(1.0, sc["olfactory"] + vent_delta)), 2)

        # -- PLANTS: biophilic bonus on visual + olfactory --
        furn_in_room = furniture_by_room.get(rid, [])
        plant_count = sum(1 for f in furn_in_room if f.get("type", "").lower() == "plant")
        if plant_count:
            sc["olfactory"] = round(min(1.0, sc["olfactory"] + 0.08 * plant_count), 2)
            sc["visual"]    = round(min(1.0, sc["visual"]    + 0.05 * plant_count), 2)

        # -- TACTILE: material-based (furniture + wall blend) --
        mat_scores = []
        for fn in furn_in_room:
            mat   = fn.get("material", "").lower()
            ftype = fn.get("type", "").lower()
            if mat in MATERIAL_SCORE:
                mat_scores.append(MATERIAL_SCORE[mat])
            elif ftype in SOFT_FURNITURE:
                mat_scores.append(0.75)   # fallback: soft type ~ wood warmth
            elif ftype in HARD_FURNITURE:
                mat_scores.append(0.45)   # fallback: hard type ~ cooler
        if mat_scores:
            avg_furn_mat = sum(mat_scores) / len(mat_scores)
            # 50% baseline, 30% furniture material, 20% wall material
            sc["tactile"] = round(min(1.0, sc["tactile"]*0.5 + avg_furn_mat*0.3 + avg_wall_mat*0.2), 2)
        else:
            # No furniture -- wall material as minor nudge only
            sc["tactile"] = round(min(1.0, sc["tactile"]*0.8 + avg_wall_mat*0.2), 2)

        # -- PERSONA WEIGHTS --
        scores = {s: round(min(1.0, v * weights.get(s, 1.0)), 2) for s, v in sc.items()}
        overall = round(sum(scores.values()) / 6.0, 2)
        low = [s for s, v in scores.items() if v < 0.5]
        narrative = (
            "Room {} scores {:.2f} for {}. Low comfort in: {}.".format(room.get("name"), overall, persona_str, ", ".join(low))
            if low else
            "Room {} scores {:.2f} for {}. Comfort adequate.".format(room.get("name"), overall, persona_str)
        )
        results.append({
            "roomId":        rid,
            "roomName":      room.get("name"),
            "persona":       persona_str,
            "comfortScores": scores,
            "overallScore":  overall,
            "narrative":     narrative
        })

    return json.dumps({"layoutId": layout.get("layoutId", "?"), "persona": persona_str, "rooms": results})
