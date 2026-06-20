"""
Session-6 validation — persona fidelity + context-scoring.

Run from anywhere:  python team_02/python/tests/validate_session6.py
Proves:
  1. apply_context is a no-op for an empty/neutral household (demo persona unchanged).
  2. The 4 demo layouts score IDENTICALLY with vs without the new context path
     (context is only ever populated for elderly/children/pets).
  3. An elderly + pet persona produces small, capped, downward nudges on exactly the
     right senses (thermal/acoustic/visual/olfactory/tactile), never inflation.
  4. Capture: a stated "grandma and a cat" lands in household_members and derives the
     elderly + pets context flags.
  5. persona_comparison derives a real archetype label and a contrasting comparison.
"""
import json
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_PYROOT = os.path.normpath(os.path.join(_HERE, ".."))
_LAYOUTS = os.path.normpath(os.path.join(_PYROOT, "..", "randomized_layouts"))
if _PYROOT not in sys.path:
    sys.path.insert(0, _PYROOT)

from comfort.sense_model import apply_context, CONTEXT_K
from comfort.compute_comfort_scores import compute_comfort_scores
from nodes._shared.persona_context import (
    derive_context, persona_scoring_args, format_persona_for_prompt,
)
from nodes.onboarding.persona_compiler import (
    _extract_household_members, _apply_quiz_fallback_patch, _merge_household_members,
    _MINIMAL_PROFILE,
)
from nodes.insights.persona_comparison import _derive_primary_label, _pick_comparison_persona

SENSES = ["thermal", "visual", "acoustic", "spatial", "olfactory", "tactile"]
_fails = []


def check(name, cond, detail=""):
    print(f"  [{'PASS' if cond else 'FAIL'}] {name}" + (f" — {detail}" if detail else ""))
    if not cond:
        _fails.append(name)


def _load(n):
    with open(os.path.join(_LAYOUTS, f"layout_{n}.json"), encoding="utf-8") as f:
        return f.read()


def _overall(scores_json):
    return {r["roomName"]: r["overallScore"] for r in json.loads(scores_json)["rooms"]}


# A neutral demo persona (no elderly/children/pets), constructed inline so this test
# never depends on whatever persona.json happens to be on disk.
EMILIE = {
    "name": "Emilie", "role": "architect", "age_group": "young_adult",
    "household_type": "dual", "household_members": [], "personality": -1.0,
    "sensory_priorities": ["thermal", "olfactory", "tactile", "visual", "acoustic", "spatial"],
    "sensory_sensitivities": ["thermal", "olfactory", "tactile"],
    "comfort_weights": {"thermal": 0.9, "visual": 0.74, "acoustic": 0.8,
                        "spatial": 0.8, "olfactory": 0.9, "tactile": 0.9},
}


print("\n1) apply_context is a no-op for an empty household")
eff = {s: 0.3 for s in SENSES}
out, adj = apply_context(eff, {})
check("empty context returns identical scores", out == eff and adj == [])
check("derive_context(Emilie) is empty", derive_context(EMILIE) == {}, str(derive_context(EMILIE)))


print("\n2) The 4 demo layouts score identically with vs without the context path")
for n in (201, 202, 203, 204):
    lj = _load(n)
    base = persona_scoring_args(EMILIE)            # no 'context' key (Emilie has no flags)
    a = compute_comfort_scores(**{**base, "layout_json": lj, "room_ids": "all"})
    b = compute_comfort_scores(layout_json=lj, room_ids="all",
                               persona=base["persona"],
                               weights_override=base.get("weights_override"),
                               personality=base["personality"], context=None)
    check(f"layout {n} unchanged under context path", a == b)


print("\n3) Elderly + pet persona → small, capped, downward nudges on the right senses")
elderly_pet = dict(EMILIE)
elderly_pet["age_group"] = "elderly"
elderly_pet["household_members"] = ["grandmother", "a cat"]
ctx = derive_context(elderly_pet)
check("derive_context flags elderly + pets", ctx == {"elderly": True, "pets": True}, str(ctx))

lj = _load(201)
neutral = compute_comfort_scores(layout_json=lj, room_ids="all",
                                 weights_override=json.dumps(EMILIE["comfort_weights"]),
                                 personality=EMILIE["personality"])
withctx = compute_comfort_scores(**{**persona_scoring_args(elderly_pet),
                                    "layout_json": lj, "room_ids": "all"})
on = _overall(neutral)
wn = _overall(withctx)
deltas = {r: round(wn[r] - on[r], 3) for r in on}
print("   overall deltas (elderly+pet vs neutral):", deltas)
check("no room improves (context only lowers)", all(d <= 0 for d in deltas.values()), str(deltas))
check("nudges are small (max drop <= CONTEXT_K)", all(abs(d) <= CONTEXT_K + 1e-9 for d in deltas.values()))
check("at least one room is affected", any(d < 0 for d in deltas.values()))
# per-sense: confirm only context senses moved and only downward, capped at CONTEXT_K
sample = json.loads(withctx)["rooms"][0]
ctx_adj = [a for a in sample.get("adjustments", []) if a.get("basis") == "context"]
print("   first room context adjustments:", [(a["from"], a["sense"], a["delta"]) for a in ctx_adj])
check("context adjustments are all negative", all(a["delta"] < 0 for a in ctx_adj))
check("context senses are within the allowed set",
      all(a["sense"] in ("thermal", "acoustic", "visual", "olfactory", "tactile", "spatial") for a in ctx_adj))


print("\n4) Capture: a stated grandma + cat survives into household_members + context")
members = _extract_household_members("Life stage: 40s+. Living situation: I live with my grandma and a cat.")
check("extractor finds grandparent + cat", "grandparent" in members and "cat" in members, str(members))
prof = dict(_MINIMAL_PROFILE)
prof["household_members"] = []
prof = _apply_quiz_fallback_patch(prof, {"q4": "I live with my grandma and a cat.", "q2": "", "q5": ""}, "")
check("quiz fallback populates household_members", bool(prof["household_members"]), str(prof["household_members"]))
check("derive_context from captured members → elderly + pets",
      derive_context(prof) == {"elderly": True, "pets": True}, str(derive_context(prof)))
line = format_persona_for_prompt(prof, level="line")
check("prompt line mentions household members", "household members" in line, line)
# synonym dedup: the LLM's "grandma"/"a cat" should absorb the extractor's canonical labels
merged = _merge_household_members(["grandma", "a cat"], ["grandparent", "cat"])
check("merge dedups synonyms (no 'grandparent' beside 'grandma')",
      "grandparent" not in merged and merged == ["grandma", "a cat"], str(merged))


print("\n5) persona_comparison derives a real archetype + a contrast")
check("elderly persona → 'Elderly 65+'", _derive_primary_label(elderly_pet) == "Elderly 65+",
      _derive_primary_label(elderly_pet))
contrast = _pick_comparison_persona("", "Elderly 65+")
check("contrast for elderly is not elderly", contrast != "Elderly 65+", contrast)


print("\n" + ("ALL CHECKS PASSED" if not _fails else f"FAILURES: {_fails}"))
sys.exit(1 if _fails else 0)
