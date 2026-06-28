"""Pareto-front diversity selector.

Fixes the "all optimization options look the same" problem. The old flow scored a
VIEW-clustered candidate pool and picked per-strategy winners by re-weighting — so
every option sat at nearly the same placement. This module instead:

  1. Builds a GENUINELY DIVERSE candidate pool — placement (grid × rotation, already
     site-validated) crossed with MASSING variants (footprint depth + courtyard), so
     candidates differ in both WHERE they sit and WHAT shape they are.
  2. Scores every candidate across ALL objectives (solar, view, noise, wind, density,
     open_space, privacy, road_access, structural) using the real enriched ctx.
  3. Computes the non-dominated PARETO FRONT over those objectives.
  4. Selects REPRESENTATIVE candidates — one per objective extreme + balanced +
     landmark — and ENFORCES geometric diversity: if a representative is near-identical
     to an already-selected one, it's discarded and replaced by the next-best DISTINCT
     Pareto candidate.

It does not rewrite any scorer or the view optimizer — it composes the existing
score_candidate() over a better pool and selects from it.
"""
from __future__ import annotations

import math
from typing import Any, Callable

from . import multi_objective_optimizer as moo
from . import _geom


# The representative selections the spec asks for: (label, objective, higher_is_better).
# "balanced" uses the weighted blend; "landmark" maximises structural slenderness/
# iconicity. Each becomes ONE option, in this order.
REPRESENTATIVES: list[dict[str, Any]] = [
    {"id": "solar", "name": "Highest Solar", "objective": "solar", "maximize": True},
    {"id": "view", "name": "Highest View", "objective": "view", "maximize": True},
    {"id": "noise", "name": "Lowest Noise", "objective": "noise", "maximize": True},   # score=quiet, higher=better
    {"id": "open_space", "name": "Highest Open Space", "objective": "open_space", "maximize": True},
    {"id": "density", "name": "Highest Density", "objective": "density", "maximize": True},
    {"id": "wind", "name": "Highest Wind Performance", "objective": "wind", "maximize": True},
    {"id": "balanced", "name": "Best Balanced Solution", "objective": "__weighted__", "maximize": True},
    {"id": "landmark", "name": "Landmark Option", "objective": "structural", "maximize": True},
]

# Objectives compared for Pareto dominance (the 9 the spec lists).
PARETO_OBJECTIVES = ["solar", "view", "noise", "wind", "density", "open_space",
                     "privacy", "road_access", "structural"]


# ---------------------------------------------------------------------------
# Massing variants — vary the SHAPE so density/open-space/solar/wind differ, not
# just placement. Each variant is a footprint transform of the base ring.
# ---------------------------------------------------------------------------

def _scale_ring(ring, sx, sy):
    cx, cy = _geom.centroid(ring)
    return [[cx + (p[0] - cx) * sx, cy + (p[1] - cy) * sy] for p in ring]


def _carve_courtyard(ring, frac=0.35):
    """Return a hole ring ~frac of the footprint, centered — a simple courtyard void."""
    cx, cy = _geom.centroid(ring)
    xs = [p[0] for p in ring]; ys = [p[1] for p in ring]
    w = (max(xs) - min(xs)) * frac * 0.5
    h = (max(ys) - min(ys)) * frac * 0.5
    if w < 2 or h < 2:
        return None
    return [[cx - w, cy - h], [cx + w, cy - h], [cx + w, cy + h], [cx - w, cy + h]]


def massing_variants(base_ring: list[list[float]]) -> list[dict[str, Any]]:
    """A small set of massing options of the SAME area family but different shape:
       compact (square-ish), slab (deep one way), slender (thin), courtyard (carved).
    Each is {boundary, holes, massing} for the scorers."""
    variants = [
        {"massing": "as_drawn", "boundary": base_ring, "holes": []},
        {"massing": "slab", "boundary": _scale_ring(base_ring, 1.4, 0.72), "holes": []},
        {"massing": "slender", "boundary": _scale_ring(base_ring, 0.72, 1.4), "holes": []},
    ]
    court = _carve_courtyard(base_ring)
    if court:
        variants.append({"massing": "courtyard", "boundary": _scale_ring(base_ring, 1.12, 1.12),
                         "holes": [court]})
    return variants


# ---------------------------------------------------------------------------
# Pareto dominance
# ---------------------------------------------------------------------------

def _dominates(a: dict[str, float], b: dict[str, float], objs: list[str]) -> bool:
    """a dominates b iff a >= b on every objective and strictly > on at least one
    (all objectives are higher-is-better as scored)."""
    ge_all = True
    gt_any = False
    for o in objs:
        av, bv = a.get(o, 0.0), b.get(o, 0.0)
        if av < bv - 1e-9:
            ge_all = False
            break
        if av > bv + 1e-9:
            gt_any = True
    return ge_all and gt_any


def pareto_front(scored: list[dict[str, Any]], objs: list[str]) -> list[dict[str, Any]]:
    """Non-dominated subset of `scored` over the given objectives."""
    front: list[dict[str, Any]] = []
    for i, c in enumerate(scored):
        ci = c["objective_scores"]
        dominated = False
        for j, other in enumerate(scored):
            if i == j:
                continue
            if _dominates(other["objective_scores"], ci, objs):
                dominated = True
                break
        if not dominated:
            front.append(c)
    return front


# ---------------------------------------------------------------------------
# Geometric diversity (discard near-identical, replace with next distinct)
# ---------------------------------------------------------------------------

def _geom_signature(c: dict[str, Any]) -> tuple:
    cx, cy = _geom.centroid(c.get("boundary") or [])
    rot = round(float(c.get("rotation_degrees", 0) or 0) / 15.0)  # 15° buckets
    massing = c.get("massing", "as_drawn")
    holes = len(c.get("holes") or [])
    return (round(cx / 12.0), round(cy / 12.0), rot, massing, holes)  # ~12 m position buckets


def _is_distinct(c: dict[str, Any], chosen: list[dict[str, Any]],
                 *, pos_tol: float = 12.0, rot_tol: float = 15.0,
                 same_pos_tol: float = 6.0) -> bool:
    """A candidate is distinct from all chosen if its placement OR massing differs
    meaningfully. Two rules make a candidate NON-distinct:
      (a) same massing AND close position AND close rotation, or
      (b) VERY close position regardless of massing (two options stacked on the same
          spot read as duplicates even if the shape differs) — spec: 'nearly identical
          placements → discard one'."""
    cx, cy = _geom.centroid(c.get("boundary") or [])
    for k in chosen:
        kx, ky = _geom.centroid(k.get("boundary") or [])
        dpos = math.hypot(cx - kx, cy - ky)
        # (b) essentially the same spot → not distinct, whatever the massing.
        if dpos <= same_pos_tol:
            return False
        if (k.get("massing", "as_drawn") != c.get("massing", "as_drawn")
                or (len(k.get("holes") or []) != len(c.get("holes") or []))):
            continue  # different massing + not stacked → distinct from this one
        drot = abs((float(c.get("rotation_degrees", 0) or 0) - float(k.get("rotation_degrees", 0) or 0)) % 360)
        drot = min(drot, 360 - drot)
        if dpos <= pos_tol and drot <= rot_tol:
            return False  # (a) near-identical to an already-chosen option
    return True


# ---------------------------------------------------------------------------
# Main entry
# ---------------------------------------------------------------------------

def select_representatives(
    candidate_pool: list[dict[str, Any]],
    ctx: dict[str, Any],
    *,
    weights: dict[str, float] | None = None,
) -> dict[str, Any]:
    """Score the pool across all objectives, compute the Pareto front, and pick the
    8 representative options with enforced geometric diversity.

    Returns {options, pareto_count, scored_count, unavailable_objectives, backfilled}.
    """
    if not candidate_pool:
        return {"options": [], "pareto_count": 0, "scored_count": 0,
                "unavailable_objectives": [], "backfilled": []}

    weights = weights or moo.optimization_weights.get_weights()
    avail = moo.available_objectives(
        {**ctx, "has_view_scores": any(c.get("view_score") is not None for c in candidate_pool)}
    )

    # Score every candidate across all objectives once.
    scored: list[dict[str, Any]] = []
    for c in candidate_pool:
        s = moo.score_candidate(c, ctx, weights)
        scored.append({**c, **s})

    # Pareto front over the objectives whose data is AVAILABLE (so an unavailable
    # objective can't fabricate dominance). Always include geometry-only objectives.
    objs = [o for o in PARETO_OBJECTIVES if avail.get(o, True)]
    front = pareto_front(scored, objs) if objs else scored
    front_ids = {id(c) for c in front}

    unavailable = sorted(o for o in PARETO_OBJECTIVES if not avail.get(o, True))
    backfilled: list[str] = []

    chosen: list[dict[str, Any]] = []
    options: list[dict[str, Any]] = []

    def _best_distinct(key: Callable[[dict], float], from_list: list[dict[str, Any]]):
        for cand in sorted(from_list, key=key, reverse=True):
            if _is_distinct(cand, chosen):
                return cand
        return None

    for rep in REPRESENTATIVES:
        obj = rep["objective"]
        # Skip a representative whose objective has no real data → backfill later with
        # the most geometrically-diverse remaining Pareto candidate (honest: we don't
        # offer a "Lowest Noise" option computed from no noise data).
        data_missing = obj != "__weighted__" and obj in avail and not avail[obj]

        if data_missing:
            backfilled.append(rep["id"])
            # Pick the Pareto candidate most DIFFERENT from what we've chosen so far.
            cand = _most_diverse(front or scored, chosen)
            chosen_objective = "balanced"
        else:
            pool = front or scored
            if obj == "__weighted__":
                cand = _best_distinct(lambda c: c["weighted_score"], pool)
            else:
                cand = _best_distinct(lambda c: c["objective_scores"].get(obj, 0.0), pool)
            chosen_objective = obj if obj != "__weighted__" else "balanced"

        if cand is None:
            # Nothing distinct left on the front — top up from the whole scored set.
            cand = _most_diverse(scored, chosen)
        if cand is None:
            continue

        chosen.append(cand)
        options.append(_frame_option(cand, rep, chosen_objective,
                                     on_front=id(cand) in front_ids,
                                     backfilled=data_missing))

    return {
        "options": options,
        "pareto_count": len(front),
        "scored_count": len(scored),
        "unavailable_objectives": unavailable,
        "backfilled": backfilled,
    }


def _most_diverse(pool: list[dict[str, Any]], chosen: list[dict[str, Any]]) -> dict[str, Any] | None:
    """The pool candidate whose geometry is FARTHEST (placement + massing) from every
    already-chosen option — used to backfill a slot with a genuinely different option."""
    best, best_score = None, -1.0
    for c in pool:
        if not _is_distinct(c, chosen):
            continue
        cx, cy = _geom.centroid(c.get("boundary") or [])
        if not chosen:
            return c
        mind = min(
            math.hypot(cx - _geom.centroid(k.get("boundary") or [])[0],
                       cy - _geom.centroid(k.get("boundary") or [])[1])
            for k in chosen
        )
        # Bonus for a different massing family.
        massing_bonus = 30.0 if all(k.get("massing") != c.get("massing") for k in chosen) else 0.0
        s = mind + massing_bonus
        if s > best_score:
            best, best_score = c, s
    return best


def _frame_option(cand: dict[str, Any], rep: dict[str, Any], objective: str,
                  *, on_front: bool, backfilled: bool) -> dict[str, Any]:
    os = cand.get("objective_scores", {})
    score = (cand.get("weighted_score", 0.0) if rep["objective"] == "__weighted__"
             else os.get(rep["objective"], 0.0))
    reason = _reason_for(rep, cand, backfilled)
    return {
        **cand,
        "option_id": rep["id"],
        "strategy_id": rep["id"],
        "strategy_name": rep["name"],
        "primary_objective": objective,
        "score": round(float(score), 1),
        "objective_scores": os,
        "on_pareto_front": on_front,
        "backfilled_from_diverse": backfilled,
        "massing": cand.get("massing", "as_drawn"),
        "headline_metrics": _headline_metrics(cand, rep["objective"]),
        "reason": reason,
    }


def _headline_metrics(cand: dict[str, Any], objective: str) -> dict[str, Any]:
    os = cand.get("objective_scores", {})
    if objective == "__weighted__":
        top = sorted(os.items(), key=lambda kv: kv[1], reverse=True)[:3]
        return {k: v for k, v in top}
    m = cand.get("objective_metrics", {}).get(objective, {})
    return m or {objective: os.get(objective, 0)}


def _reason_for(rep: dict[str, Any], cand: dict[str, Any], backfilled: bool) -> str:
    if backfilled:
        return (f"No data to optimise {rep['objective']} for this site — showing a "
                "genuinely different placement/massing instead.")
    os = cand.get("objective_scores", {})
    nice = {
        "solar": f"Best solar/daylight on the front (solar {os.get('solar', 0):.0f}).",
        "view": f"Best view exposure (view {os.get('view', 0):.0f}).",
        "noise": f"Quietest placement, farthest from noise sources (quiet {os.get('noise', 0):.0f}).",
        "open_space": f"Most usable open space (open space {os.get('open_space', 0):.0f}).",
        "density": f"Best use of buildable FAR/volume (density {os.get('density', 0):.0f}).",
        "wind": f"Best cross-ventilation / wind comfort (wind {os.get('wind', 0):.0f}).",
        "structural": f"Most iconic, structurally feasible massing (structural {os.get('structural', 0):.0f}).",
        "__weighted__": f"Best balance across all objectives (overall {cand.get('weighted_score', 0):.0f}).",
    }
    return nice.get(rep["objective"], rep["name"])
