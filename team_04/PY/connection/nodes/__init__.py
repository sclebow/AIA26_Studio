"""TerraPilot prompt-understanding nodes — a 3-layer pipeline that turns natural
language into validated geometry operations, behaving like an architectural AI
assistant rather than a keyword matcher.

    prompt_understanding.understand(prompt, context)
        │
        ├─ 1. DIRECT COMMAND LAYER  (direct_command.py)
        │      "move 5m north", "rotate 20", "add 5 floors" → exact op, no LLM
        │
        ├─ 2. INTENT CLASSIFICATION (intent_classifier.py)
        │      "it feels too compact" → increase_openness   (LLM-first, keyword
        │      fallback — understands MEANING, not exact words)
        │
        └─ 3. REASON NODE           (reason_node.py — existing, extended)
               intent + shape + site + context → best VALID operation
               (intent_to_operations.py ranks candidates; architectural_operations.py
                lists what each intent can do)

These modules are thin orchestration over the EXISTING geometry/validation engine
(feedback_reasoning, architectural_intent, reason_node). They do not reimplement
any algorithm. The keyword reason_node remains the deterministic safety net so the
system never regresses when the LLM is slow or unavailable.
"""
from __future__ import annotations

from .. import _TEAM_ROOT  # noqa: F401  (puts team_04/ on sys.path)
