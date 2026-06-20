"""
compute_comfort_scores — 6-sense comfort scoring per room, persona-weighted.
Fixed: accepts weights_override dict so onboarding-derived custom weights are used.
"""

import json

# Canonical coupling model is the single source of truth for aggregation + couplings.
try:
    from comfort.sense_model import aggregate_comfort, apply_cross_modal, apply_personality, apply_context
except ImportError:  # when loaded as a same-dir module rather than the comfort package
    from sense_model import aggregate_comfort, apply_cross_modal, apply_personality, apply_context


def compute_comfort_scores(layout_json, persona=None, room_ids=None, weights_override=None,
                           personality=0.0, context=None):
    layout = None
    try:
        layout = json.loads(layout_json)
    except Exception:
        return json.dumps({"error": "Invalid layout_json"})

    # Household-context flags (elderly / children / pets) — who actually lives here.
    # Parsed once; apply_context() is a no-op when empty, so a neutral persona is
    # scored exactly as before.
    ctx = {}
    if context:
        try:
            ctx = json.loads(context) if isinstance(context, str) else dict(context)
        except Exception:
            ctx = {}

    rooms = layout.get("rooms", [])
    persona_str   = str(persona).strip() if persona else "Neutral"
    room_ids_str  = str(room_ids).strip() if room_ids else "all"
    target_ids    = ([r.get("id") for r in rooms]
                     if room_ids_str.lower() == "all"
                     else [x.strip() for x in room_ids_str.split(",")])

    BASELINES = {
        "bedroom":     {"thermal":0.75,"visual":0.65,"acoustic":0.70,"spatial":0.65,"olfactory":0.80,"tactile":0.70},
        "living":      {"thermal":0.70,"visual":0.80,"acoustic":0.55,"spatial":0.75,"olfactory":0.70,"tactile":0.65},
        "kitchen":     {"thermal":0.50,"visual":0.70,"acoustic":0.45,"spatial":0.60,"olfactory":0.35,"tactile":0.60},
        "bathroom":    {"thermal":0.60,"visual":0.55,"acoustic":0.70,"spatial":0.45,"olfactory":0.45,"tactile":0.65},
        "circulation": {"thermal":0.65,"visual":0.55,"acoustic":0.65,"spatial":0.50,"olfactory":0.70,"tactile":0.55},
        "dining":      {"thermal":0.65,"visual":0.75,"acoustic":0.55,"spatial":0.65,"olfactory":0.60,"tactile":0.60},
        "utility":     {"thermal":0.55,"visual":0.50,"acoustic":0.60,"spatial":0.50,"olfactory":0.55,"tactile":0.55},
        "study":       {"thermal":0.70,"visual":0.65,"acoustic":0.65,"spatial":0.60,"olfactory":0.70,"tactile":0.60},
        "office":      {"thermal":0.70,"visual":0.65,"acoustic":0.65,"spatial":0.60,"olfactory":0.70,"tactile":0.60},
    }

    VOLUME_NORMS = {
        "bedroom":48.6,"living":81.0,"kitchen":32.4,"bathroom":13.5,
        "circulation":16.2,"dining":40.5,"utility":10.8,"study":32.4,"office":40.5
    }

    MATERIAL_SCORE = {
        "metal":0.10,"glass":0.20,"concrete":0.25,"stone":0.30,
        "ceramic":0.35,"brick":0.50,"plaster":0.55,"cork":0.70,
        "wood":0.75,"fabric":0.80,"carpet":0.85,"natural":0.75
    }

    ORIENTATION_BONUS = {
        "S":0.05,"SE":0.04,"SW":0.04,"E":0.02,"W":0.02,
        "N":-0.03,"NE":-0.02,"NW":-0.02
    }

    # Contribution weights = the REAL onboarding comfort_weights. No persona
    # categories: the only fallback is a uniform 0.5 baseline ("no preferences
    # expressed yet"), used before onboarding produces a profile.
    senses = ("thermal", "visual", "acoustic", "spatial", "olfactory", "tactile")
    weights = {s: 0.5 for s in senses}
    if weights_override:
        try:
            raw_w = json.loads(weights_override) if isinstance(weights_override, str) else weights_override
            if all(s in raw_w for s in senses):
                weights = {s: float(raw_w[s]) for s in senses}
        except Exception:
            pass

    # Door adjacency map
    adj = {}
    for d in layout.get("doors", []):
        conn = d.get("attributes", {}).get("connectsRooms", [])
        if len(conn) == 2:
            adj.setdefault(conn[0], []).append(conn[1])
            adj.setdefault(conn[1], []).append(conn[0])
    rtype = {r.get("id"): r.get("attributes", {}).get("roomType", "living") for r in rooms}

    # Window map
    window_map = {}
    for w in layout.get("windows", []):
        wrid = w.get("attributes", {}).get("roomId")
        if wrid:
            window_map.setdefault(wrid, []).append(w.get("attributes", {}))

    # Furniture map (top-level furniture[], keyed by roomId)
    SOFT_FURNITURE = {"sofa", "bed", "armchair", "rug", "cushion", "couch"}
    HARD_FURNITURE = {"table", "island", "desk", "shelf", "counter", "cabinet", "storage", "dresser"}
    # Soft, sound-absorbing furnishings: the acoustic-absorption credit behind the
    # "add rugs and curtains to absorb sound" suggestion (curtains/blinds are new tools).
    SOFT_ABSORBERS = {"rug", "carpet", "curtain", "curtains", "blind", "blinds",
                      "drape", "drapes", "shade", "cushion", "sofa", "couch", "armchair"}
    furniture_by_room = {}
    for f in layout.get("furniture", []):
        frid = f.get("attributes", {}).get("roomId")
        if frid:
            furniture_by_room.setdefault(frid, []).append(f.get("attributes", {}))

    # Global wall material average
    wall_mats = [w.get("attributes", {}).get("material", "plaster").lower()
                 for w in layout.get("structure", [])]
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
        floor_mat   = room.get("attributes", {}).get("floorMaterial", "")
        wall_mat    = room.get("attributes", {}).get("wallMaterial", "")
        # Room-SCOPED wall finish (falls back to the global structure average). This is
        # what makes "change the bedroom walls to cork" actually move that room's score —
        # the old code only ever read one global wall-material average for every room.
        wall_mat_score = MATERIAL_SCORE.get(wall_mat.lower(), avg_wall_mat) if wall_mat else avg_wall_mat

        sc = BASELINES.get(rt, BASELINES["living"]).copy()

        # SPATIAL: volume-based
        vol_norm = VOLUME_NORMS.get(rt, 40.5)
        sc["spatial"] = round(min(1.0, (area * height) / vol_norm), 2)

        # ACOUSTIC: adjacency penalty from noisy neighbours
        noisy = sum(1 for x in adj.get(rid, []) if rtype.get(x) in ["kitchen", "living"])
        if noisy:
            sc["acoustic"] = round(max(0.1, sc["acoustic"] - 0.15 * noisy), 2)
        # ACOUSTIC: reverberation — larger volume with hard (less absorptive) surfaces
        # raises RT60 (Sabine: RT60 = 0.161·V/A). Couples spatial(volume)+tactile(material)→acoustic.
        vol = area * height
        reverb_risk = max(0.0, (vol / VOLUME_NORMS.get(rt, 40.5)) - 1.0)
        soft_items = sum(1 for f in furniture_by_room.get(rid, [])
                         if f.get("type", "").lower() in SOFT_ABSORBERS)
        # Effective absorption blends FLOOR (base, as before) + WALL finish + soft
        # furnishings, so harder/softer walls and added rugs/curtains change reverb.
        # With a default floor + plaster wall + no soft items this equals the old value.
        floor_abs  = MATERIAL_SCORE.get(floor_mat.lower(), 0.5) if floor_mat else 0.5
        absorption = floor_abs + 0.15 * (wall_mat_score - 0.55) + min(0.20, 0.06 * soft_items)
        absorption = max(0.05, min(0.95, absorption))
        if reverb_risk > 0:
            sc["acoustic"] = round(max(0.1, sc["acoustic"] - 0.12 * reverb_risk * (1.0 - absorption)), 2)
        # Soft furnishings also damp sound directly (not only in large rooms) — this is
        # the mechanism the "add rugs and curtains to absorb sound" suggestion promises.
        if soft_items:
            sc["acoustic"] = round(min(1.0, sc["acoustic"] + min(0.10, 0.04 * soft_items)), 2)

        # THERMAL: orientation + glazing type
        thermal_delta = ORIENTATION_BONUS.get(orientation, 0)
        for win in window_map.get(rid, []):
            gt = win.get("glazingType", "double")
            if gt == "single":
                thermal_delta -= 0.08
            elif gt == "triple":
                thermal_delta += 0.05
            # Each window's own facing nudges thermal (a south window warms, a north one
            # cools) — so "move the window to the south wall" actually improves thermal.
            thermal_delta += 0.5 * ORIENTATION_BONUS.get(win.get("orientation"), 0)
        sc["thermal"] = round(max(0.0, min(1.0, sc["thermal"] + thermal_delta)), 2)
        # THERMAL: glazing ratio also drives thermal (solar gain / winter heat loss).
        # Larger glazing → bigger thermal swing. Mirrors glazing→visual so the lever
        # feeds BOTH senses (the visual↔thermal coupling via glazing).
        if glaz_ratio >= 0.25:
            sc["thermal"] = round(max(0.0, sc["thermal"] - 0.06), 2)
        elif glaz_ratio >= 0.15:
            sc["thermal"] = round(max(0.0, sc["thermal"] - 0.03), 2)

        # VISUAL: glazing ratio
        if glaz_ratio < 0.10:
            sc["visual"] = round(max(0.0, sc["visual"] - 0.15), 2)
        elif glaz_ratio >= 0.20:
            sc["visual"] = round(min(1.0, sc["visual"] + 0.08), 2)

        # OLFACTORY: ventilation type
        vent_delta = {"natural":0.05,"mixed":0.0,"mechanical":-0.05}.get(vent_type, 0)
        sc["olfactory"] = round(max(0.0, min(1.0, sc["olfactory"] + vent_delta)), 2)
        # OLFACTORY: odor/contaminant migration from adjacent kitchens/bathrooms (transmissive)
        wet_neighbours = sum(1 for x in adj.get(rid, []) if rtype.get(x) in ["kitchen", "bathroom"])
        if wet_neighbours:
            sc["olfactory"] = round(max(0.1, sc["olfactory"] - 0.10 * wet_neighbours), 2)

        # PLANTS: biophilic bonus
        furn_in_room = furniture_by_room.get(rid, [])
        plant_count = sum(1 for f in furn_in_room
                          if f.get("type", "").lower() == "plant"
                          or f.get("material", "").lower() == "natural")
        if plant_count:
            sc["olfactory"] = round(min(1.0, sc["olfactory"] + 0.08 * plant_count), 2)
            sc["visual"]    = round(min(1.0, sc["visual"]    + 0.05 * plant_count), 2)

        # TACTILE: furniture + floor + wall material blend
        mat_scores = []
        for fn in furn_in_room:
            mat   = fn.get("material", "").lower()
            ftype = fn.get("type", "").lower()
            if mat in MATERIAL_SCORE:
                mat_scores.append(MATERIAL_SCORE[mat])
            elif ftype in SOFT_FURNITURE:
                mat_scores.append(0.75)
            elif ftype in HARD_FURNITURE:
                mat_scores.append(0.45)

        # Floor material (room-level attribute) contributes to tactile
        floor_score = MATERIAL_SCORE.get(floor_mat.lower(), None) if floor_mat else None

        # Wall contribution to tactile uses the ROOM's own wall finish (wall_mat_score),
        # not the global average — so a room-scoped wall edit moves this room's tactile.
        if mat_scores:
            avg_furn_mat = sum(mat_scores) / len(mat_scores)
            if floor_score is not None:
                # 40% baseline, 25% furniture, 20% floor, 15% wall
                sc["tactile"] = round(min(1.0,
                    sc["tactile"]*0.40 + avg_furn_mat*0.25 + floor_score*0.20 + wall_mat_score*0.15), 2)
            else:
                sc["tactile"] = round(min(1.0,
                    sc["tactile"]*0.50 + avg_furn_mat*0.30 + wall_mat_score*0.20), 2)
        else:
            if floor_score is not None:
                sc["tactile"] = round(min(1.0, sc["tactile"]*0.60 + floor_score*0.25 + wall_mat_score*0.15), 2)
            else:
                sc["tactile"] = round(min(1.0, sc["tactile"]*0.80 + wall_mat_score*0.20), 2)

        # Per-sense scores stay OBJECTIVE (no persona inflation). Persona/preference
        # weights apply at aggregation instead — and overall comfort is NON-ADDITIVE
        # (one-vote veto + negativity bias), so we blend the weighted mean with the
        # worst sense via aggregate_comfort() rather than averaging. (sense_model.py)
        base = {s: round(min(1.0, max(0.0, v)), 2) for s, v in sc.items()}
        # Cross-modal moderation (both tiers, each adjustment tagged research/physics),
        # then the personality/arousal fit. comfortScores = the EFFECTIVE (felt) scores;
        # baseScores keep the design-only values; adjustments explain every delta.
        eff, cm_adj = apply_cross_modal(base)
        eff, p_adj  = apply_personality(eff, personality)
        # Household-context sensitivity (elderly / children / pets) — amplifies deficits
        # for vulnerable occupants. No-op when ctx is empty. Labelled like the others.
        eff, ctx_adj = apply_context(eff, ctx)
        adjustments = cm_adj + p_adj + ctx_adj
        overall = aggregate_comfort(eff, weights)
        low     = [s for s, v in eff.items() if v < 0.5]
        narrative = (
            f"Room {room.get('name')} scores {overall:.2f}. Low comfort in: {', '.join(low)}."
            if low else
            f"Room {room.get('name')} scores {overall:.2f}. Comfort adequate."
        )
        results.append({
            "roomId":        rid,
            "roomName":      room.get("name"),
            "persona":       persona_str,
            "comfortScores": eff,           # effective / felt scores (after cross-modal + personality)
            "baseScores":    base,          # design-only scores, before moderation
            "adjustments":   adjustments,   # labelled deltas: {sense, delta, from, mechanism, basis}
            "overallScore":  overall,
            "narrative":     narrative,
        })

    return json.dumps({"layoutId": layout.get("layoutId", "?"), "persona": persona_str, "rooms": results})
