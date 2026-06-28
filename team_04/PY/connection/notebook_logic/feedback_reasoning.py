"""Architectural-feedback reasoning — the AI layer ABOVE the manual move/rotate/
scale tools.

It does NOT reimplement any geometry. It (1) gathers the design metrics the
existing analysis tools already compute (setback, 3D view score, density,
courtyard ratio, proportions, floors/height), (2) asks the LLM to translate a
natural-language design critique ("I want more daylight") into a small set of
abstract manipulation actions, and (3) parses each action into the SAME concrete
transform payload the manual tools use — {dx,dy} | {rotation} | {scale} | {floors}.

The route then executes those transforms through the EXISTING manipulation
backend (modify_building_boundary via tool_dev_runtime), so both workflows share
one geometry engine. This module never mutates a building; it only reasons and
parses.

Output contract (what the route returns to the frontend):
    {
      "reason": "Increase daylight penetration",
      "observations": ["Daylight is limited by deep floor plates", ...],
      "actions": [
        {"text": "rotate 12 degrees south", "transform": {"rotation": 12}, "op": "rotate"},
        {"text": "reduce depth 8%",          "transform": {"scale": 0.92}, "op": "scale"},
        ...
      ],
      "metrics": {...},          # the analysis the reasoning was based on
    }
"""
from __future__ import annotations

import json
import math
import re
from typing import Any

DEFAULT_FLOOR_HEIGHT_M = 3.0


# --------------------------------------------------------------------------- #
# 1. Metric gathering — reuse the existing analysis tools, never recompute.
# --------------------------------------------------------------------------- #
def _poly_area(boundary: list[list[float]] | None) -> float:
    pts = [(float(p[0]), float(p[1])) for p in (boundary or []) if len(p) >= 2]
    if len(pts) < 3:
        return 0.0
    a = 0.0
    n = len(pts)
    for i in range(n):
        j = (i + 1) % n
        a += pts[i][0] * pts[j][1] - pts[j][0] * pts[i][1]
    return abs(a) / 2.0


def _bbox_proportions(boundary: list[list[float]] | None) -> dict[str, float]:
    pts = [(float(p[0]), float(p[1])) for p in (boundary or []) if len(p) >= 2]
    if len(pts) < 3:
        return {"width": 0.0, "depth": 0.0, "aspect_ratio": 1.0}
    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]
    width = max(xs) - min(xs)
    depth = max(ys) - min(ys)
    long_side = max(width, depth) or 1.0
    short_side = min(width, depth) or 1.0
    return {
        "width": round(width, 2),
        "depth": round(depth, 2),
        "aspect_ratio": round(long_side / short_side, 3),
    }


def gather_metrics(
    building: dict[str, Any],
    *,
    site_boundary: list[list[float]] | None,
    others: list[list[list[float]]] | None = None,
    floor_height_m: float = DEFAULT_FLOOR_HEIGHT_M,
) -> dict[str, Any]:
    """Collect the design metrics the reasoning layer reasons over. Every number
    comes from the EXISTING analysis tools (site_setback, view_3d) or simple
    footprint geometry — nothing new is modelled here. All checks are best-effort:
    a failing tool yields a null field, never an exception."""
    boundary = building.get("boundary") or building.get("building_boundary") or []
    floors = building.get("floors")
    height_m = building.get("height_m")
    if height_m is None and floors:
        height_m = float(floors) * floor_height_m
    eval_height = float(height_m) if height_m else 12.0

    footprint_area = _poly_area(boundary)
    site_area = _poly_area(site_boundary)
    proportions = _bbox_proportions(boundary)

    # Density / open-space / courtyard ratios from areas we already have.
    site_coverage = round(footprint_area / site_area, 3) if site_area else None
    open_space_ratio = round(1.0 - site_coverage, 3) if site_coverage is not None else None
    # Courtyard ratio: void enclosed by the footprint's convex hull vs the footprint.
    courtyard_ratio = _courtyard_ratio(boundary)

    # 3D view score (height-aware) — other buildings act as obstacles. Same call
    # run_design_checks uses.
    view_score_3d = None
    try:
        from agent.tools.view_3d import evaluate_building_views_3d

        obstacles = [{"boundary": ob, "height": float("inf")} for ob in (others or []) if ob]
        if boundary and len(boundary) >= 3:
            view = evaluate_building_views_3d(
                boundary, eval_height, obstacles,
                floor_height=floor_height_m, return_ray_detail=False,
            )
            view_score_3d = (view or {}).get("view_score_3d")
    except Exception:  # noqa: BLE001 — analysis is advisory, never fatal
        view_score_3d = None

    # Setback clearances against the confirmed site.
    setback = None
    try:
        from agent.tools.site_setback import setback_summary

        if site_boundary and len(site_boundary) >= 3:
            setback = setback_summary(site_boundary)
    except Exception:  # noqa: BLE001
        setback = None

    return {
        "footprint_area_sqm": round(footprint_area, 1),
        "site_area_sqm": round(site_area, 1) if site_area else None,
        "site_coverage": site_coverage,
        "open_space_ratio": open_space_ratio,
        "courtyard_ratio": courtyard_ratio,
        "proportions": proportions,
        "floors": floors,
        "height_m": round(eval_height, 1),
        "view_score_3d": view_score_3d,
        "setback_summary": setback,
        "shape_type": building.get("shape_type"),
    }


def _courtyard_ratio(boundary: list[list[float]] | None) -> float | None:
    """How much of the footprint's convex hull is void (a proxy for courtyard /
    spread). 0 ~ solid/compact, higher ~ a U/H/O with an enclosed court."""
    pts = [(float(p[0]), float(p[1])) for p in (boundary or []) if len(p) >= 2]
    if len(pts) < 3:
        return None
    footprint = _poly_area(boundary)
    hull = _convex_hull_area(pts)
    if hull <= 0:
        return None
    return round(max(0.0, (hull - footprint) / hull), 3)


def _convex_hull_area(pts: list[tuple[float, float]]) -> float:
    uniq = sorted(set(pts))
    if len(uniq) < 3:
        return 0.0

    def cross(o, a, b):
        return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])

    lower: list[tuple[float, float]] = []
    for p in uniq:
        while len(lower) >= 2 and cross(lower[-2], lower[-1], p) <= 0:
            lower.pop()
        lower.append(p)
    upper: list[tuple[float, float]] = []
    for p in reversed(uniq):
        while len(upper) >= 2 and cross(upper[-2], upper[-1], p) <= 0:
            upper.pop()
        upper.append(p)
    hull = lower[:-1] + upper[:-1]
    return _poly_area([list(p) for p in hull])


# --------------------------------------------------------------------------- #
# 2. LLM reasoning — translate critique → abstract actions.
# --------------------------------------------------------------------------- #
_SYSTEM_PROMPT = """You are an architectural design critic for TerraPilot, a \
massing tool. The user gives you free-form design FEEDBACK about a single placed \
building (not an explicit move/rotate/scale command). Your job is to translate \
that intent into a SMALL set (1-4) of concrete massing actions, using the metrics \
provided.

You may ONLY use these action verbs. Directions are TRUE GEOGRAPHIC \
(north/south/east/west/northeast/...), never screen-relative.
  - "move <N>m <north|south|east|west>"        (slide the footprint)
  - "rotate <N> degrees [clockwise]"           (reorient; bare = counter-clockwise, toward sun = south)
  - "scale <F>x"  OR  "increase|reduce <width|size> <P>%"          (resize footprint)
  - "add courtyard"                            (carve a CENTRAL VOID — real opening for daylight to the core)
  - "create patio on the <direction> side"     (carve an EDGE VOID toward that true side)
  - "reduce depth"                             (shallower floor plate along the short axis — more daylight)
  - "lengthen the <direction> facade"          (extend the footprint outward on that true side)
  - "make the <direction> wing bigger|smaller"  (resize the WING on that true side; use for "<dir> wing"/"right wing"=east/"left wing"=west)
  - "add|remove <N> floors"  OR  "increase|reduce height <P>%"     (vertical only, preserves footprint)

Rules:
- For "make the X wing bigger/larger/longer" or "right/left wing", use the WING verb (not lengthen facade).
- Prefer the SMALLEST set that addresses the feedback (1-4 actions).
- "more daylight" => prefer "add courtyard" and/or "reduce depth" (NOT just a scale).
- "too compact" => "add courtyard" / "create patio" / "reduce size".
- "Keep this option / preserve footprint" => emit ONLY height/floor actions.
- Honor explicit directions: "patio on the south", "long facade on north" => use that true side.
- Ground actions in the metrics (low view_score_3d => daylight problem; high \
site_coverage => too compact; small courtyard_ratio => add courtyard).
- Respond with STRICT JSON only, no prose:
{"reason": "<short goal>", "observations": ["<metric-grounded note>", ...], \
"actions": ["<action string>", ...]}"""


def reason_about_feedback(
    feedback: str,
    metrics: dict[str, Any],
    *,
    llm: Any | None = None,
) -> dict[str, Any]:
    """Ask the LLM for {reason, observations, actions[]}. Falls back to a
    deterministic heuristic if no LLM is configured or the call fails, so the
    feature degrades gracefully instead of erroring."""
    if llm is None:
        llm = _get_llm()

    if llm is not None:
        try:
            user = (
                f"FEEDBACK: {feedback}\n\nMETRICS:\n{json.dumps(metrics, indent=2)}\n\n"
                "Return the JSON object now."
            )
            resp = llm.invoke(
                [{"role": "system", "content": _SYSTEM_PROMPT},
                 {"role": "user", "content": user}]
            )
            content = getattr(resp, "content", resp)
            if isinstance(content, list):  # some providers return content parts
                content = "".join(part.get("text", "") if isinstance(part, dict) else str(part)
                                  for part in content)
            parsed = _extract_json(str(content))
            if parsed and isinstance(parsed.get("actions"), list) and parsed["actions"]:
                parsed.setdefault("reason", "Apply architectural feedback")
                parsed.setdefault("observations", [])
                parsed["source"] = "llm"
                return parsed
        except Exception:  # noqa: BLE001 — fall back to heuristic
            pass

    fallback = _heuristic_reasoning(feedback, metrics)
    fallback["source"] = "heuristic"
    return fallback


class _FallbackLLM:
    """Two-tier LLM with automatic provider fallback. Tries the PRIMARY provider
    (from LLM_PROVIDER, e.g. Gemini); if its call raises (rate limit 429 / 503 / any
    error), transparently retries on a SECONDARY provider (e.g. Cloudflare) so a
    per-minute limit or transient outage on one provider doesn't drop the LLM. If both
    fail it raises, and the caller's existing try/except falls back to keyword matching.

    Exposes .invoke(messages) so it's a drop-in for ChatOpenAI everywhere _get_llm()
    is used."""

    def __init__(self, primary, secondary=None):
        self._primary = primary
        self._secondary = secondary
        self.last_provider = None

    def invoke(self, messages, **kwargs):
        try:
            r = self._primary.invoke(messages, **kwargs)
            self.last_provider = "primary"
            return r
        except Exception as primary_exc:  # noqa: BLE001
            if self._secondary is None:
                raise
            try:
                r = self._secondary.invoke(messages, **kwargs)
                self.last_provider = "secondary"
                return r
            except Exception:  # noqa: BLE001 — both failed → let caller keyword-fallback
                raise primary_exc


def _build_chat(provider: str, settings) -> Any | None:
    """Build a ChatOpenAI for an explicit provider name using the same .env values
    agent.config reads. Returns None if that provider isn't configured."""
    import os

    from langchain_openai import ChatOpenAI

    p = (provider or "").strip().lower()
    try:
        if p == "google":
            key = os.environ.get("GOOGLE_API_KEY")
            model = os.environ.get("GOOGLE_MODEL")
            base = "https://generativelanguage.googleapis.com/v1beta/openai"
        elif p == "cloudflare":
            key = os.environ.get("CF_API_TOKEN")
            acct = os.environ.get("CF_ACCOUNT_ID")
            model = os.environ.get("CF_MODEL")
            base = f"https://api.cloudflare.com/client/v4/accounts/{acct}/ai/v1" if acct else None
        elif p == "openai":
            key = os.environ.get("OPENAI_API_KEY"); model = os.environ.get("OPENAI_MODEL")
            base = "https://api.openai.com/v1"
        else:
            return None
        if not (key and model and base):
            return None
        return ChatOpenAI(api_key=key, base_url=base, model=model,
                          timeout=settings.request_timeout_seconds, temperature=0.2)
    except Exception:  # noqa: BLE001
        return None


def _get_llm() -> Any | None:
    """Return a two-tier LLM: the configured PRIMARY provider with an automatic
    SECONDARY fallback. The secondary defaults to Cloudflare when the primary is
    Google (and vice-versa) if its credentials are present in .env — so hitting
    Gemini's per-minute limit auto-switches to the Cloudflare account instead of
    dropping straight to keyword matching. Override the secondary with the env var
    FALLBACK_LLM_PROVIDER. Returns None only if no provider is configured."""
    try:
        import os

        from agent.config import load_settings

        # .env may have changed since import — make sure it's loaded.
        try:
            from dotenv import load_dotenv
            from pathlib import Path
            root = Path(__file__).resolve().parents[2]  # team_04/
            load_dotenv(root / ".env", override=True)
        except Exception:  # noqa: BLE001
            pass

        s = load_settings()
        primary = _build_chat(s.llm_provider, s)
        if primary is None:
            return None

        # Pick a secondary: explicit env override, else the "other" provider whose
        # credentials exist (Gemini<->Cloudflare), so the fallback is automatic.
        sec_name = (os.environ.get("FALLBACK_LLM_PROVIDER") or "").strip().lower()
        if not sec_name:
            if s.llm_provider == "google" and os.environ.get("CF_API_TOKEN"):
                sec_name = "cloudflare"
            elif s.llm_provider == "cloudflare" and os.environ.get("GOOGLE_API_KEY"):
                sec_name = "google"
        secondary = _build_chat(sec_name, s) if sec_name and sec_name != s.llm_provider else None
        return _FallbackLLM(primary, secondary)
    except Exception:  # noqa: BLE001
        return None


def _extract_json(text: str) -> dict[str, Any] | None:
    text = text.strip()
    # Strip ``` fences if the model wrapped the JSON.
    fence = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if fence:
        text = fence.group(1)
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1:
        return None
    try:
        return json.loads(text[start : end + 1])
    except json.JSONDecodeError:
        return None


def _heuristic_reasoning(feedback: str, metrics: dict[str, Any]) -> dict[str, Any]:
    """Deterministic keyword fallback covering the documented scenarios so the
    feature still works (and tests are stable) without a live LLM."""
    low = feedback.lower()
    obs: list[str] = []
    actions: list[str] = []
    reason = "Apply architectural feedback"

    cov = metrics.get("site_coverage")
    court = metrics.get("courtyard_ratio")
    view = metrics.get("view_score_3d")

    if re.search(r"tall|height|floor|stor(e|y)|capacity", low) and re.search(
        r"keep|preserve|same footprint|this option", low
    ):
        reason = "Increase capacity while preserving footprint"
        obs.append("Preserving footprint and orientation; changing vertical parameters only.")
        actions.append("add 3 floors")
    elif re.search(r"tall|more floor|add floor|height|capacity", low):
        reason = "Increase capacity"
        actions.append("add 3 floors")
    elif re.search(r"patio|recess", low):
        d = re.search(r"(north(?:east|west)?|south(?:east|west)?|east|west)", low)
        side = d.group(1) if d else "south"
        reason = f"Open a {side} patio"
        actions.append(f"create a patio on the {side} side")
    elif re.search(r"courtyard|atrium", low):
        reason = "Carve a courtyard for daylight"
        if court is not None:
            obs.append(f"Courtyard ratio is small ({court}).")
        actions.append("add courtyard")
    elif re.search(r"daylight|sunlight|sun|bright|light", low):
        reason = "Increase daylight penetration"
        if view is not None and view < 0.6:
            obs.append(f"3D view/daylight score is low ({view}).")
        obs.append("Deep floor plates limit daylight to the core.")
        # Reduce depth FIRST — shallower plates let daylight reach deeper WITHOUT adding
        # solar-exposed facade (so it doesn't raise the overheating penalty in a hot
        # climate, unlike a courtyard). Courtyard is the secondary daylight move.
        actions += ["reduce depth", "add courtyard"]
    elif re.search(r"compact|cramp|dense|tight|crowded", low):
        reason = "Reduce perceived compactness"
        if cov is not None and cov > 0.4:
            obs.append(f"Site coverage is high ({cov}).")
        actions += ["add courtyard", "reduce size 12%"]
    elif re.search(r"(lengthen|extend|longer|long facade).*?(north(?:east|west)?|south(?:east|west)?|east|west)", low):
        d = re.search(r"(north(?:east|west)?|south(?:east|west)?|east|west)", low)
        side = d.group(1) if d else "north"
        reason = f"Lengthen the {side} facade"
        actions.append(f"lengthen the {side} facade")
    elif re.search(r"open space|breathing|spacious|airy", low):
        reason = "Create more open space"
        actions += ["reduce size 12%"]
    elif re.search(r"view|park|vista|outlook", low):
        reason = "Improve views"
        actions += ["rotate 20 degrees"]
    else:
        reason = "Adjust massing per feedback"
        obs.append("No strong keyword match; applied a conservative reorientation.")
        actions += ["rotate 10 degrees"]

    return {"reason": reason, "observations": obs, "actions": actions}


# --------------------------------------------------------------------------- #
# 3. Action parsing — abstract action string -> concrete transform payload.
# --------------------------------------------------------------------------- #
_DIRS = {
    "north": (0, 1), "south": (0, -1), "east": (1, 0), "west": (-1, 0),
    "up": (0, 1), "down": (0, -1), "right": (1, 0), "left": (-1, 0),
}

# Compass unit vectors in the local metric frame (+y = true north), for floor-plate
# moves. "close to the north edge" pushes the selected floors toward +y.
DIRECTION_VECTORS = {
    "north": (0.0, 1.0), "south": (0.0, -1.0), "east": (1.0, 0.0), "west": (-1.0, 0.0),
    "northeast": (0.707, 0.707), "northwest": (-0.707, 0.707),
    "southeast": (0.707, -0.707), "southwest": (-0.707, -0.707),
}


def _move_distance(text: str) -> float:
    """Pull a metre distance out of the phrase, defaulting to a sensible nudge when
    the user says 'close to the edge' without a number."""
    import re as _re
    m = _re.search(r"(\d+(?:\.\d+)?)\s*m\b", text)
    return float(m.group(1)) if m else 8.0


def parse_action(action: str) -> dict[str, Any] | None:
    """Parse ONE action string into {op, transform, text}. transform mirrors the
    manual tools' payloads so the route can feed it straight to the existing
    backend: {dx,dy} | {rotation} | {scale} | {floors} | {height_pct}."""
    if not isinstance(action, str):
        return None
    low = action.lower().strip()

    _DIR_RE_FP = r"(north(?:east|west)?|south(?:east|west)?|east|west|front|back|forward|backward|left|right)"

    # --- Corner placement: "place towards the northeast corner", "move to the top
    # left corner", "put it in the south-west corner". Snaps the whole building to
    # that SITE corner (inset by a setback). Checked BEFORE the generic move so a
    # "corner" request doesn't degrade into a tiny nudge. ---
    if "corner" in low:
        # normalize compound names: "north east"->"northeast", "top left"->"top left"
        norm = re.sub(r"\b(north|south)\s+(east|west)\b", r"\1\2", low)
        corner = None
        for name in ("northeast", "northwest", "southeast", "southwest",
                     "top right", "top left", "bottom right", "bottom left"):
            if name in norm:
                corner = name
                break
        # Single compass + "corner" (e.g. "north corner") → nearest diagonal default.
        if not corner:
            if re.search(r"\bnorth\b", norm) and re.search(r"\beast\b", norm):
                corner = "northeast"
            elif re.search(r"\bnorth\b", norm):
                corner = "northwest" if re.search(r"\bleft\b|\bwest\b", norm) else "northeast"
            elif re.search(r"\bsouth\b", norm):
                corner = "southwest" if re.search(r"\bleft\b|\bwest\b", norm) else "southeast"
        if corner:
            return {"op": "place_corner", "transform": {"corner": corner}, "text": action}

    # --- Edge placement: "place against the north edge", "move to the east side",
    # "hug the west edge". Snaps the building to that SITE edge (inset). ---
    if re.search(r"\b(place|move|put|shift|push|hug|against|along|near)\b", low) and \
       re.search(r"\b(edge|side|wall)\b", low) and \
       re.search(r"\b(north|south|east|west|top|bottom|left|right)\b", low) and \
       "floor" not in low:
        d = re.search(r"\b(north|south|east|west|top|bottom|left|right)\b", low)
        return {"op": "place_edge", "transform": {"direction": d.group(1)}, "text": action}

    # --- BARE-DIRECTION placement: "move building towards southwest", "move it south",
    # "push toward the north". No 'corner'/'edge'/'side' word — but a clear move verb +
    # a compass direction, so DEFAULT to: a DIAGONAL (NE/NW/SE/SW) → that site corner;
    # a CARDINAL (N/S/E/W) → that site edge. Without this a bare direction fell through
    # to the context path and failed ("Unable to act on 'that feature'"). Floor moves are
    # already handled above, so exclude "floor". ---
    if re.search(r"\b(move|put|shift|push|pull|slide|relocate|reposition|drag|send)\b", low) and \
       "floor" not in low and "wing" not in low:
        norm = re.sub(r"\b(north|south)\s+(east|west)\b", r"\1\2", low)  # "south west"→"southwest"
        diag = next((c for c in ("northeast", "northwest", "southeast", "southwest") if c in norm), None)
        if diag:
            return {"op": "place_corner", "transform": {"corner": diag}, "text": action}
        card = re.search(r"\b(north|south|east|west)\b", norm)
        if card:
            return {"op": "place_edge", "transform": {"direction": card.group(1)}, "text": action}

    # --- FLOOR-PLATE ops (per-floor geometry: move a level range, target a wing) ---
    # "move the bottom 5 floors toward/close to the north edge", "move top 2 floors
    # front by 3m" — only those plates shift, not the whole building. Parsed BEFORE
    # the generic move so it wins. front/back/left/right map to true compass below.
    mvf = re.search(
        r"(?:move|shift|slide|push|pull)\s+(?:the\s+)?(bottom|top|lower|upper)?\s*(\d+)?\s*floors?.*?"
        rf"(?:toward|towards|close to|to(?:ward)?|near|by|on the)?\s*(?:the\s+)?{_DIR_RE_FP}",
        low,
    )
    if mvf:
        which = mvf.group(1) or "bottom"
        count = int(mvf.group(2)) if mvf.group(2) else None
        raw_dir = mvf.group(3)
        # Map screen-relative words to true compass (north-up viewer default).
        direction = {"front": "south", "forward": "south", "back": "north",
                     "backward": "north", "left": "west", "right": "east"}.get(raw_dir, raw_dir)
        # Distance: "by 3m" / "3 meters", else a default nudge.
        dm = re.search(r"by\s+(\d+(?:\.\d+)?)\s*m|(\d+(?:\.\d+)?)\s*m\b", low)
        distance = float(dm.group(1) or dm.group(2)) if dm else 8.0
        sel = {}
        if which in ("bottom", "lower"):
            sel["bottom"] = count
        else:
            sel["top"] = count
        return {
            "op": "floor_move",
            "transform": {"select": sel, "direction": direction, "distance_m": distance},
            "text": action,
        }

    # "add 2 floors on/to the right wing" — raise ONLY that wing's plates.
    # Tolerant of EXTRA words between "floors" and the wing (e.g. "add 2 floors of a
    # terrace party hall on the right wing"): `.*?` lets descriptive phrases sit in the
    # middle so the per-wing op still fires instead of falling back to a whole-building
    # add. We still require the trailing "<direction> wing" to anchor it to a wing.
    awf = re.search(
        r"(add|remove)\s+(\d+)\s*(?:floors?|stor(?:eys?|ies)|levels?)\b.*?"
        r"(?:on|to|onto|in|over|atop)\s+(?:the\s+)?"
        r"(right|left|north|south|east|west|main|front|back)\s+wing",
        low,
    )
    if awf:
        n = int(awf.group(2))
        delta = n if awf.group(1) == "add" else -n
        return {
            "op": "floor_add_wing",
            "transform": {"floors": delta, "wing": awf.group(3)},
            "text": action,
        }

    # Absolute floor count: "make it 20 floors", "set to 20 floors", "20 storeys",
    # "i want 20 floors". The route resolves it against the building's current count
    # (parse_action can't know it here). Checked BEFORE the relative add/remove form.
    m = re.search(r"(?:make it|set(?:\s+it)?(?:\s+to)?|want|have|change to|build)\s+(?:.*?\b)?(\d+)\s*(?:floors?|stor(?:eys?|ies)|levels?)", low)
    if not m:
        # Bare "20 floors" with no verb still means an absolute target.
        m2 = re.search(r"^\s*(\d+)\s*(?:floors?|stor(?:eys?|ies)|levels?)\s*$", low)
        if m2:
            m = m2
    if m and not re.search(r"\b(add|remove|increase|reduce|decrease|more|extra|another)\b", low):
        return {"op": "set_floors", "transform": {"floors": int(m.group(1))}, "text": action}

    # Floors / height (vertical only — preserves footprint).
    m = re.search(r"(add|remove|increase|reduce|decrease)\s+(\d+)\s*floors?", low)
    if m:
        n = int(m.group(2))
        delta = n if m.group(1) in ("add", "increase") else -n
        return {"op": "floors", "transform": {"floors": delta}, "text": action}
    m = re.search(r"(increase|reduce|decrease)\s+height\s+(?:by\s+)?(\d+(?:\.\d+)?)\s*%", low)
    if m:
        pct = float(m.group(2)) / 100.0
        factor = 1 + pct if m.group(1) == "increase" else 1 - pct
        return {"op": "height", "transform": {"height_factor": round(factor, 3)}, "text": action}
    # Absolute metre height: "set to 45m", "make it 60 meters" → convert to a floor
    # target (rounded) so it flows through the same plate-stack rebuild.
    m = re.search(r"(?:set(?:\s+(?:it|the height))?(?:\s+to)?|make it|height)\s+(\d+(?:\.\d+)?)\s*m(?:eters?)?\b", low)
    if m:
        target_floors = max(1, round(float(m.group(1)) / DEFAULT_FLOOR_HEIGHT_M))
        return {"op": "set_floors", "transform": {"floors": target_floors}, "text": action}

    # Move to the CENTRE of the site: "move to the centre of the site", "centre the
    # building", "move it to the middle". The route resolves the site centroid (the
    # parser can't see the site here) and translates the footprint there.
    if re.search(r"\b(cent(er|re)|middle)\b", low) and \
       re.search(r"\b(move|put|place|shift|centre|center)\b", low) and \
       not re.search(r"\bcorner\b", low):
        return {"op": "place_center", "transform": {"center": True}, "text": action}

    # Move.
    if re.search(r"\b(move|shift|slide|nudge|translate|separate|spread)\b", low):
        m = re.search(r"(\d+(?:\.\d+)?)\s*m", low)
        dist = float(m.group(1)) if m else 5.0
        dx = dy = 0.0
        for word, (ux, uy) in _DIRS.items():
            if re.search(rf"\b{word}\b", low):
                dx, dy = ux * dist, uy * dist
                break
        if dx or dy:
            return {"op": "move", "transform": {"dx": dx, "dy": dy}, "text": action}

    # --- Architectural-intent ops (REAL footprint mutations, true directions) ---
    _DIR_RE = r"(north(?:east|west)?|south(?:east|west)?|east|west)"

    # Courtyard: a central void. "add courtyard", "open the courtyard", "create
    # courtyard". Tolerates common misspellings (courdyard/courtyrd/coutyard/cordyard).
    if re.search(r"cou?r?[td]y?ard|courtyrd|atrium|central (void|opening)", low) \
       and not re.search(r"reduce|close|remove", low):
        frac = 0.3
        mm = re.search(r"(\d+(?:\.\d+)?)\s*%", low)
        if mm:
            frac = max(0.1, min(0.55, float(mm.group(1)) / 100.0))
        return {"op": "courtyard", "transform": {"fraction": frac}, "text": action}

    # Patio: an edge void toward a true side. "create a patio on the south side".
    if re.search(r"patio|recess|open (void|space) on", low):
        d = re.search(_DIR_RE, low)
        return {"op": "patio", "transform": {"direction": (d.group(1) if d else "south"), "fraction": 0.2},
                "text": action}

    # WING resize on a true geographic side. "make the east wing bigger",
    # "enlarge the north wing", "shrink the west wing". right→east, left→west
    # (north-up assumption) so common phrasing still works.
    if re.search(r"\bwing\b", low):
        # resolve the target side: geographic dir, else right/left → east/west
        d = re.search(_DIR_RE, low)
        side = d.group(1) if d else ("east" if re.search(r"\bright\b", low)
                                     else "west" if re.search(r"\bleft\b", low) else None)
        if side:
            shrink = bool(re.search(r"\b(smaller|shrink|reduce|less)\b", low))
            factor = 0.75 if shrink else 1.3
            mm = re.search(r"(\d+(?:\.\d+)?)\s*%", low)
            if mm:
                pct = float(mm.group(1)) / 100.0
                factor = (1 - pct) if shrink else (1 + pct)
            return {"op": "wing", "transform": {"direction": side, "factor": round(factor, 3)},
                    "text": action}

    # Facade ALIGNMENT / orientation (a ROTATION, not a growth): "align long facade
    # to north", "make the long facade face the top", "orient the building south",
    # "face the frontage toward the park". Checked BEFORE lengthen so an "align facade"
    # request rotates the mass instead of extending it. Screen words top/bottom/front/
    # back map to true compass north/south (the viewer is north-up by default).
    #
    # BUT: an EXPLICIT growth verb wins. "lengthen/extend/make longer the facade facing
    # the road" must LENGTHEN, not rotate — the incidental word "facing" must not hijack
    # the user's stated verb. So skip alignment when a lengthen/extend verb is present.
    # ALSO skip when the prompt's real GOAL is environmental (ventilation/airflow/daylight)
    # — "orient for natural ventilation" must improve airflow (courtyard / reduce depth),
    # not do a no-op facade rotation. Those fall through to the environmental intent.
    _wants_lengthen = bool(re.search(r"\b(lengthen|extend|elongate|make (it |the )?\w* ?longer|longer|stretch)\b", low))
    _is_environmental = bool(re.search(r"\b(ventilation|ventilate|airflow|air flow|breeze|cross.?vent|natural light|daylight|sunlight|solar gain)\b", low))
    if (not _wants_lengthen) and (not _is_environmental) and \
       re.search(r"\b(align|face|facing|orient|orientation)\b", low) and \
       re.search(r"\b(facade|frontage|long side|front|building|mass)\b", low):
        # Resolve the target direction, accepting screen-relative words.
        d = re.search(_DIR_RE, low)
        if d:
            direction = d.group(1)
        elif re.search(r"\btop\b|\bback\b", low):
            direction = "north"
        elif re.search(r"\bbottom\b|\bfront\b|\bfwd\b|\bforward\b", low):
            direction = "south"
        elif re.search(r"\bright\b", low):
            direction = "east"
        elif re.search(r"\bleft\b", low):
            direction = "west"
        else:
            direction = "north"
        return {"op": "align_facade", "transform": {"direction": direction}, "text": action}

    # Lengthen / extend a facade on a true side. "lengthen the north facade",
    # "long facade on north".
    if re.search(r"(lengthen|extend|longer|long facade|stretch).*" + _DIR_RE, low) or \
       re.search(_DIR_RE + r".*(facade|side).*(longer|long|extend)", low):
        d = re.search(_DIR_RE, low)
        return {"op": "lengthen", "transform": {"direction": (d.group(1) if d else "north"), "amount_pct": 0.2},
                "text": action}

    # Reduce depth (shallower floor plate). "reduce depth", "reduce building depth".
    if re.search(r"reduce (the )?(building )?depth|shallow(er)? (floor|plate)|less depth", low):
        pct = 0.15
        mm = re.search(r"(\d+(?:\.\d+)?)\s*%", low)
        if mm:
            pct = max(0.05, min(0.4, float(mm.group(1)) / 100.0))
        return {"op": "reduce_depth", "transform": {"amount_pct": pct}, "text": action}

    # Rotate (bare/"south"/"toward sun" => CCW positive; "clockwise"/"cw" => negative).
    if re.search(r"\b(rotate|turn|spin|reorient|orient)\b", low):
        m = re.search(r"(\d+(?:\.\d+)?)\s*(?:deg|degree|°)", low) or re.search(r"\b(\d+(?:\.\d+)?)\b", low)
        deg = float(m.group(1)) if m else 15.0
        if re.search(r"\b(clockwise|cw)\b", low):
            deg = -deg
        return {"op": "rotate", "transform": {"rotation": deg}, "text": action}

    # Natural-language scale (no number): "make it bigger", "building is too small",
    # "scale up the building", "increase the massing size". Defaults: scale up 1.25,
    # generic bigger/too-small 1.2, smaller/too-large 0.8. Excludes floor/corner/wing.
    if not re.search(r"\bfloors?\b|\bcorner\b|\bwing\b", low):
        bigger = re.search(r"\b(bigger|larger|too small|very small|scale up|increase (the )?(size|mass|massing|foot\s?print|scale|area|coverage)|enlarge|expand|more (mass|massing|area|coverage)|grow)\b", low)
        smaller = re.search(r"\b(smaller|too (large|big)|scale down|shrink|reduce (the )?(size|mass|massing|foot\s?print|scale|area|coverage)|less (mass|massing|area))\b", low)
        if bigger or smaller:
            pct = re.search(r"(\d+(?:\.\d+)?)\s*%", low)
            if pct:
                f = float(pct.group(1)) / 100.0
                factor = (1 - f) if smaller else (1 + f)
            else:
                factor = 0.8 if smaller else (1.25 if re.search(r"\bscale up\b", low) else 1.2)
            return {"op": "scale", "transform": {"scale": round(factor, 3)}, "text": action}

    # Scale family: explicit factor, percent resize, courtyard, depth/width.
    m = re.search(r"scale\s+(\d+(?:\.\d+)?)\s*x?", low)
    if m:
        return {"op": "scale", "transform": {"scale": round(float(m.group(1)), 3)}, "text": action}

    m = re.search(
        r"(increase|expand|grow|enlarge|reduce|decrease|shrink|narrow)\s+"
        r"(width|depth|size|footprint|courtyard|mass|spacing|void)?\s*(?:by\s+)?(\d+(?:\.\d+)?)\s*%",
        low,
    )
    if m:
        verb, _target, pct = m.group(1), m.group(2), float(m.group(3)) / 100.0
        grow = verb in ("increase", "expand", "grow", "enlarge")
        # "reduce courtyard" means a SMALLER void => grow the footprint, and vice
        # versa, because courtyard is the void inside the footprint hull.
        if (_target or "") == "courtyard":
            factor = (1 - pct) if grow else (1 + pct)
        else:
            factor = (1 + pct) if grow else (1 - pct)
        return {"op": "scale", "transform": {"scale": round(factor, 3)}, "text": action}

    return None


def parse_actions(actions: list[str]) -> list[dict[str, Any]]:
    """Parse every action string; drop the unparseable ones (kept in the result
    as op='unsupported' so the UI can show what was ignored)."""
    out: list[dict[str, Any]] = []
    for a in actions or []:
        parsed = parse_action(a)
        out.append(parsed or {"op": "unsupported", "transform": None, "text": a})
    return out
