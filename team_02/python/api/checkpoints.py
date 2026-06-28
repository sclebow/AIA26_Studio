"""
checkpoints.py — the "Checkpoints" layer (Task 3), built ON TOP of the session.

Sensi edits a LIVE WORKING DRAFT (`session["layout_json_string"]`, mutated by the
apply_edits graph node). This module adds committed MILESTONES on top of that draft —
without touching the graph. A commit snapshots the cumulative working state since the
last checkpoint; checkpoint 0 is the initial (un-edited) layout.

The Vision (Act 3) renders the COMMITTED state: after = latest checkpoint, before =
checkpoint 0. So `vision_layout()` / `vision_scores()` return the committed snapshot,
never the uncommitted working draft.

All functions operate on the plain `session` dict (the same one run_agent round-trips).
Session keys owned here:
    checkpoints            list[dict]  full snapshots (see _new_checkpoint shape)
    committed_layout_json  str         = checkpoints[-1].layout_json
    committed_scores_json  str         = checkpoints[-1].scores_json
    pending_diffs          list[dict]  edit diffs accumulated since the last commit
"""

from __future__ import annotations
from datetime import datetime, timezone
import json

SENSES = ["thermal", "visual", "acoustic", "spatial", "olfactory", "tactile"]


# ── small helpers ──────────────────────────────────────────────────────────────

def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _canon(layout_json: str) -> str:
    """Canonical form for comparing layouts — whitespace/key-order independent. The
    on-disk file is pretty-printed while the working layout is compact json.dumps, so
    raw string compares give false 'uncommitted' positives; canonicalise both first."""
    try:
        return json.dumps(json.loads(layout_json), sort_keys=True)
    except Exception:
        return layout_json or ""


def _avg_score(scores_json: str):
    """Whole-home headline: 0.6*mean + 0.4*worst (mirrors the JS layoutScore)."""
    try:
        ovs = [float(r["overallScore"]) for r in json.loads(scores_json).get("rooms", [])
               if r.get("overallScore") is not None]
        if not ovs:
            return None
        return round(0.6 * (sum(ovs) / len(ovs)) + 0.4 * min(ovs), 4)
    except Exception:
        return None


def _conflict_count(conflicts_json: str) -> int:
    try:
        return len(json.loads(conflicts_json).get("flaggedRooms", []))
    except Exception:
        return 0


def _sense_means(scores_json: str) -> dict:
    """Per-sense mean across all rooms — a whole-home value per sense."""
    try:
        rooms = json.loads(scores_json).get("rooms", [])
    except Exception:
        return {}
    means = {}
    for s in SENSES:
        vals = [r.get("comfortScores", {}).get(s) for r in rooms]
        vals = [v for v in vals if v is not None]
        if vals:
            means[s] = sum(vals) / len(vals)
    return means


def _kind_label(d: dict) -> str:
    """One terse word for a single edit's kind."""
    attr = str(d.get("attribute", "")).lower()
    nv = str(d.get("new_value", "")).lower()
    if attr == "furniture":
        if "plant" in nv:
            return "Plants"
        for t in ("rug", "sofa", "couch", "chair", "table", "desk", "shelf", "cabinet", "bed", "cushion"):
            if t in nv:
                return t.capitalize()
        return "Furniture"
    if "glaz" in attr:
        return "Glazing"
    if "material" in attr:
        mat = d.get("new_value", "")
        return mat.capitalize() if isinstance(mat, str) and mat and " " not in mat else "Material"
    return "Edit"


def _label_from_diffs(diffs: list) -> str:
    """Terse auto-label (<= 2 words) when the user didn't name the checkpoint:
    one kind ('Plants', 'Glazing', 'Wood') or a count ('3 edits')."""
    diffs = [d for d in (diffs or []) if d]
    if not diffs:
        return "Edit"
    labels = list(dict.fromkeys(_kind_label(d) for d in diffs))
    return labels[0] if len(labels) == 1 else f"{len(diffs)} edits"


# ── queries ──────────────────────────────────────────────────────────────────

def has_uncommitted(session: dict) -> bool:
    """True when the working draft differs from the committed head (canonical compare)."""
    working = session.get("layout_json_string", "")
    return bool(working) and _canon(working) != _canon(session.get("committed_layout_json", ""))


def vision_layout(session: dict) -> str:
    """The layout the Report/Vision renders — the COMMITTED head (not the draft)."""
    return session.get("committed_layout_json") or session.get("layout_json_string", "")


def vision_scores(session: dict) -> str:
    return session.get("committed_scores_json") or session.get("last_scores_json", "")


def summaries(session: dict) -> list:
    """Lightweight wire list for the Checkpoints strip (no full layout/scores JSON)."""
    out = []
    for cp in session.get("checkpoints", []) or []:
        out.append({
            "id":             cp["id"],
            "label":          cp["label"],
            "avg_score":      _avg_score(cp.get("scores_json", "")),
            "sense_means":    _sense_means(cp.get("scores_json", "")),
            "conflict_count": _conflict_count(cp.get("conflicts_json", "")),
            "created_at":     cp.get("created_at"),
            "is_initial":     cp["id"] == 0,
        })
    return out


def uncommitted_delta(session: dict) -> dict:
    """Per-sense whole-home before→after for the uncommitted changes (committed head →
    working draft). Same shape SenseDeltaPills consumes: {sense: {before, after}}."""
    if not has_uncommitted(session):
        return {}
    before = _sense_means(session.get("committed_scores_json", ""))
    after = _sense_means(session.get("last_scores_json", ""))
    out = {}
    for s in SENSES:
        if s in before and s in after and abs(after[s] - before[s]) > 0.005:
            out[s] = {"before": round(before[s], 3), "after": round(after[s], 3)}
    return out


def live_head(session: dict) -> dict | None:
    """The uncommitted working draft as a plottable point for the checkpoint graph —
    full per-sense means + the whole-home headline. None when working == committed head
    (no dashed 'now' node to draw)."""
    if not has_uncommitted(session):
        return None
    sj = session.get("last_scores_json", "")
    return {"sense_means": _sense_means(sj), "avg_score": _avg_score(sj)}


# ── mutations ──────────────────────────────────────────────────────────────────

def _seed_initial(session: dict, original_layout_json: str) -> None:
    """Create checkpoint 0 from the pristine initial layout (never the edited draft)."""
    working = session.get("layout_json_string", "")
    init_layout = original_layout_json or working
    # If the on-disk initial still equals the working layout, no edits have happened
    # yet, so the current scores describe the initial layout — capture them.
    fresh = _canon(init_layout) == _canon(working)
    init_scores = session.get("last_scores_json", "") if fresh else ""
    cp0 = {
        "id": 0, "label": "Initial layout",
        "layout_json": init_layout,
        "scores_json": init_scores,
        "conflicts_json": session.get("last_conflicts_json", "") if fresh else "",
        "suggestions_json": "",
        "diffs": [], "created_at": _now(),
    }
    session["checkpoints"] = [cp0]
    session["committed_layout_json"] = init_layout
    session["committed_scores_json"] = init_scores
    session["pending_diffs"] = []


def sync(session: dict, original_layout_json: str, layout_updated: bool) -> None:
    """Maintain checkpoint state after a graph turn (call from /api/message).

    original_layout_json: the pristine on-disk layout, for seeding checkpoint 0.
    layout_updated:       this turn mutated the working layout (edit / biophilic auto-add).
    """
    if not session.get("layout_json_string"):
        return  # no layout loaded yet

    if not session.get("checkpoints"):
        _seed_initial(session, original_layout_json)

    # Accumulate this turn's diffs toward the next commit's changelog/label.
    if layout_updated:
        session.setdefault("pending_diffs", []).extend(session.get("layout_diffs", []) or [])

    # No uncommitted edits (working == committed) but a fresh (re)score happened →
    # keep the head checkpoint's scores current. This is how checkpoint 0 gets its
    # scores on the first analysis, and how re-analysis refreshes the committed head.
    if not has_uncommitted(session):
        cps = session.get("checkpoints", [])
        cur = session.get("last_scores_json", "")
        if cps and cur and cur != cps[-1].get("scores_json", ""):
            cps[-1]["scores_json"] = cur
            cps[-1]["conflicts_json"] = session.get("last_conflicts_json", "")
            session["committed_scores_json"] = cur


def commit(session: dict, label: str | None = None) -> dict | None:
    """Snapshot the working draft as a new checkpoint (cumulative since the last one)."""
    if not has_uncommitted(session):
        return None
    working = session.get("layout_json_string", "")
    cps = session.setdefault("checkpoints", [])
    diffs = session.get("pending_diffs", []) or []
    cp = {
        "id": (cps[-1]["id"] + 1) if cps else 0,
        "label": (label or "").strip() or _label_from_diffs(diffs),
        "layout_json": working,
        "scores_json": session.get("last_scores_json", ""),
        "conflicts_json": session.get("last_conflicts_json", ""),
        "suggestions_json": session.get("last_suggestions_json", ""),
        "diffs": diffs,
        "created_at": _now(),
    }
    cps.append(cp)
    session["committed_layout_json"] = working
    session["committed_scores_json"] = session.get("last_scores_json", "")
    session["pending_diffs"] = []
    return cp


def view(session: dict, checkpoint_id: int) -> dict | None:
    """Read a checkpoint's scored state for review (NON-destructive — does not touch
    the working draft). Powers clicking a checkpoint to see its scores in the panel."""
    cp = next((c for c in session.get("checkpoints", []) if c["id"] == checkpoint_id), None)
    if cp is None:
        return None
    return {
        "id": cp["id"],
        "label": cp["label"],
        "scores_json": cp.get("scores_json", ""),
        "conflicts_json": cp.get("conflicts_json", ""),
        "suggestions_json": cp.get("suggestions_json", ""),
    }


def restore(session: dict, checkpoint_id: int) -> dict | None:
    """Roll the working draft back to a checkpoint (discards uncommitted edits). The
    committed head is left unchanged — has_uncommitted then reflects working vs head."""
    cp = next((c for c in session.get("checkpoints", []) if c["id"] == checkpoint_id), None)
    if cp is None:
        return None
    session["layout_json_string"]   = cp["layout_json"]
    session["last_scores_json"]     = cp.get("scores_json", "")
    session["last_conflicts_json"]  = cp.get("conflicts_json", "")
    session["last_suggestions_json"] = cp.get("suggestions_json", "")
    session["pending_diffs"] = []
    return cp


def reset(session: dict) -> None:
    """Drop all checkpoint state — call when the session switches to a new layout."""
    for k in ("checkpoints", "committed_layout_json", "committed_scores_json", "pending_diffs"):
        session.pop(k, None)
