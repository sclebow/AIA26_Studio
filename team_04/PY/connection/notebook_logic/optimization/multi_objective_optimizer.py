"""Multi-objective optimizer — combines all scoring modules into one engine.

This does NOT replace the existing view optimization (view_optimizer wraps it).
It:
  * runs every scorer on a candidate -> {objective: {score, metrics, reason}}
  * blends them with the configurable weights -> weighted total
  * scores a POOL of candidates each optimised for a different priority and
    returns diverse, ranked, named strategy options (Daylight / View / Density /
    Open Space / Wind / Balanced / Cost Efficient / Landmark).

A "candidate" is {boundary, holes?, floors?, height_m?, + any precomputed view
scores}. "ctx" carries the site, setbacks, obstacles, roads, context scores, etc.
"""
from __future__ import annotations

from typing import Any, Callable

from . import (
    construction_efficiency_optimizer,
    context_response_optimizer,
    density_optimizer,
    emergency_access_optimizer,
    mixed_use_optimizer,
    noise_optimizer,
    open_space_optimizer,
    optimization_weights,
    privacy_optimizer,
    public_private_optimizer,
    road_access_optimizer,
    setback_optimizer,
    solar_optimizer,
    structural_optimizer,
    view_optimizer,
    walkability_optimizer,
    wind_optimizer,
)

# objective id -> scorer module (each exposes score(candidate, ctx)).
SCORERS: dict[str, Callable[[dict, dict], dict]] = {
    "solar": solar_optimizer.score,
    "view": view_optimizer.score,
    "open_space": open_space_optimizer.score,
    "road_access": road_access_optimizer.score,
    "density": density_optimizer.score,
    "setback": setback_optimizer.score,
    "walkability": walkability_optimizer.score,
    "wind": wind_optimizer.score,
    "privacy": privacy_optimizer.score,
    "noise": noise_optimizer.score,
    "structural": structural_optimizer.score,
    "construction_efficiency": construction_efficiency_optimizer.score,
    "context_response": context_response_optimizer.score,
    "emergency_access": emergency_access_optimizer.score,
    "mixed_use": mixed_use_optimizer.score,
    "public_private": public_private_optimizer.score,
}

# Named strategies → which objective they maximise (spec's option types A–H).
STRATEGIES: list[dict[str, str]] = [
    {"id": "daylight", "name": "Daylight Optimized", "objective": "solar"},
    {"id": "view", "name": "View Optimized", "objective": "view"},
    {"id": "density", "name": "Density Optimized", "objective": "density"},
    {"id": "open_space", "name": "Open Space Optimized", "objective": "open_space"},
    {"id": "wind", "name": "Wind Optimized", "objective": "wind"},
    {"id": "balanced", "name": "Balanced Solution", "objective": "__weighted__"},
    {"id": "cost", "name": "Cost Efficient", "objective": "construction_efficiency"},
    {"id": "landmark", "name": "Landmark Option", "objective": "structural"},
]


# CONTEXT-AVAILABILITY GATE: which ctx data each objective REQUIRES to be a real
# (non-fabricated) score. Objectives needing only the geometry + site are always
# available. The rest are dropped from the weighted blend (and reported as
# unavailable) when their data is absent — never scored from a default. This does
# NOT change any scorer's internal logic; it only gates the blend.
_OBJECTIVE_REQUIRES: dict[str, list[str]] = {
    "wind": [],                      # geometry-only (cross-vent from depth) -> always ok
    "noise": ["noise_sources_or_roads"],
    "road_access": ["roads"],
    "view": ["view_data"],           # precomputed view score or attractors
    "walkability": ["context_scores"],
    "context_response": ["context_scores"],
    "privacy": ["neighbours"],       # placed obstacles OR real OSM neighbour buildings
    # solar/density/open_space/setback/structural/construction_efficiency/mixed_use/
    # public_private/emergency_access need only geometry+site -> always available.
}


def available_objectives(ctx: dict[str, Any]) -> dict[str, bool]:
    """Return {objective: is_its_required_data_available}. Geometry-only objectives
    are always True."""
    has = {
        "roads": bool(ctx.get("roads")),
        "noise_sources_or_roads": bool(ctx.get("noise_sources") or ctx.get("roads")),
        "view_data": bool(ctx.get("view_attractors") or ctx.get("has_view_scores")),
        "context_scores": bool(ctx.get("context_scores")),
        "obstacles": bool(ctx.get("obstacles")),
        # Privacy is available with EITHER placed buildings OR real OSM neighbours.
        "neighbours": bool(ctx.get("obstacles") or ctx.get("neighbor_buildings")),
    }
    out: dict[str, bool] = {}
    for obj in SCORERS:
        reqs = _OBJECTIVE_REQUIRES.get(obj, [])
        out[obj] = all(has.get(r, True) for r in reqs)
    return out


def score_candidate(candidate: dict[str, Any], ctx: dict[str, Any],
                    weights: dict[str, float] | None = None) -> dict[str, Any]:
    """Run all scorers + the weighted blend on ONE candidate. Objectives whose
    REQUIRED context data is unavailable are excluded from the weighted blend (and
    flagged) rather than scored from a default — no fabricated scores."""
    weights = weights or optimization_weights.get_weights()
    avail = available_objectives(
        {**ctx, "has_view_scores": candidate.get("view_score") is not None}
    )
    per_obj: dict[str, dict[str, Any]] = {}
    for obj, fn in SCORERS.items():
        try:
            per_obj[obj] = fn(candidate, ctx)
        except Exception as exc:  # noqa: BLE001
            per_obj[obj] = {"score": 0.0, "metrics": {}, "reason": f"scorer error: {exc}"}
    # Weighted blend over AVAILABLE objectives only; renormalize so dropping an
    # unavailable metric doesn't deflate the total.
    eff_w = {o: w for o, w in weights.items() if w > 0 and o in per_obj and avail.get(o, True)}
    wsum = sum(eff_w.values()) or 1.0
    weighted = sum((w / wsum) * per_obj[o]["score"] for o, w in eff_w.items())
    used = sorted(o for o in per_obj if avail.get(o, True))
    unavailable = sorted(o for o in per_obj if not avail.get(o, True))
    return {
        "objective_scores": {o: round(v["score"], 1) for o, v in per_obj.items() if avail.get(o, True)},
        "objective_metrics": {o: v["metrics"] for o, v in per_obj.items() if avail.get(o, True)},
        "objective_reasons": {o: v["reason"] for o, v in per_obj.items() if avail.get(o, True)},
        "weighted_score": round(weighted, 1),
        "metrics_used": used,
        "metrics_unavailable": unavailable,
    }


def rank_strategies(candidates: list[dict[str, Any]], ctx: dict[str, Any],
                    weights: dict[str, float] | None = None,
                    max_options: int = 8) -> list[dict[str, Any]]:
    """Given a POOL of valid candidates, pick the best candidate per STRATEGY so the
    returned options each optimise a different priority (not duplicates). Returns up
    to `max_options` named, ranked options with their scores + headline metrics."""
    weights = weights or optimization_weights.get_weights()
    if not candidates:
        return []
    # Score every candidate once.
    scored = []
    for c in candidates:
        s = score_candidate(c, ctx, weights)
        scored.append({**c, **s})

    # CONTEXT-AVAILABILITY: skip strategies whose objective's data is unavailable —
    # don't offer e.g. a "Wind Optimized" option scored from no wind data.
    avail = available_objectives({**ctx, "has_view_scores": any(c.get("view_score") is not None for c in candidates)})

    options: list[dict[str, Any]] = []
    used_ids: set[int] = set()
    for strat in STRATEGIES:
        obj = strat["objective"]
        if obj != "__weighted__" and obj in avail and not avail[obj]:
            continue  # required data missing -> skip this strategy
        if obj == "__weighted__":
            best = max(scored, key=lambda c: c["weighted_score"])
        else:
            best = max(scored, key=lambda c: c["objective_scores"].get(obj, 0))
        # Avoid returning the SAME candidate for two strategies — prefer a distinct one.
        bid = id(best)
        if bid in used_ids:
            remaining = [c for c in scored if id(c) not in used_ids]
            if remaining:
                key = (lambda c: c["weighted_score"]) if obj == "__weighted__" else (lambda c: c["objective_scores"].get(obj, 0))
                best = max(remaining, key=key)
                bid = id(best)
        used_ids.add(bid)
        headline = _headline(best, obj)
        options.append({
            **best,
            # option_id keyed by STRATEGY so two strategies sharing a candidate still
            # get unique ids (the frontend keys cards on option_id).
            "option_id": strat["id"],
            "strategy_id": strat["id"],
            "strategy_name": strat["name"],
            "primary_objective": obj if obj != "__weighted__" else "balanced",
            "score": best["weighted_score"] if obj == "__weighted__" else best["objective_scores"].get(obj, 0),
            "headline_metrics": headline["metrics"],
            "reason": headline["reason"],
        })
    # Rank options by their own headline score, best first.
    options.sort(key=lambda o: o["score"], reverse=True)
    return options[:max_options]


def _headline(candidate: dict[str, Any], objective: str) -> dict[str, Any]:
    """Pick a few key metrics + a 'why selected' line for the option card."""
    if objective == "__weighted__":
        # Balanced: surface the top 3 contributing objectives.
        os = candidate.get("objective_scores", {})
        top = sorted(os.items(), key=lambda kv: kv[1], reverse=True)[:3]
        return {
            "metrics": {k: candidate["objective_scores"][k] for k, _ in top},
            "reason": "Highest combined weighted performance across all criteria.",
        }
    metrics = candidate.get("objective_metrics", {}).get(objective, {})
    reason = candidate.get("objective_reasons", {}).get(objective, "")
    # Pretty per-strategy reasons.
    nice = {
        "solar": "Best orientation for daylight, courtyard sun and reduced self-shading.",
        "view": "Best frontage toward parks, water and skyline views.",
        "density": "Best use of the allowed FAR and buildable volume.",
        "open_space": "Largest usable public and open space.",
        "wind": "Best cross-ventilation and wind comfort.",
        "construction_efficiency": "Simplest, most efficient geometry to build.",
        "structural": "Most iconic, structurally feasible massing.",
    }.get(objective, reason)
    return {"metrics": metrics, "reason": nice}
