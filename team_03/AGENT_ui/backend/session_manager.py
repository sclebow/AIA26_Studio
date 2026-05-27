"""
In-memory session state manager.
Stores the current layout, spatial graph, and scoring results.
"""
from __future__ import annotations

from typing import Any, Dict, Optional


class SessionManager:
    """Single-session in-memory store (no database)."""

    def __init__(self) -> None:
        self._state: Dict[str, Any] = {
            "layout": None,
            "layout_name": None,
            "graph": None,
            "scores": None,
            "pending_layout": None,
        }

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def create_session(self, layout_name: str, layout_data: dict) -> Dict[str, Any]:
        """
        Initialise a session with a chosen layout.
        Resets graph and scores to None.
        """
        self._state = {
            "layout_name": layout_name,
            "layout": layout_data,
            "graph": None,
            "scores": None,
            "pending_layout": None,
        }
        return self.get_session()

    def get_session(self) -> Optional[Dict[str, Any]]:
        """Return the current session state, or None when no layout is loaded."""
        if self._state["layout"] is None:
            return None
        return dict(self._state)

    def update_layout(self, layout_data: dict) -> None:
        """Replace the layout stored in the current session."""
        self._state["layout"] = layout_data

    def update_graph(self, graph_data: dict) -> None:
        """Store the spatial graph (node-link JSON)."""
        self._state["graph"] = graph_data

    def update_scores(self, scores_data: dict) -> None:
        """Store the latest scoring results."""
        self._state["scores"] = scores_data

    def set_pending_layout(self, data: dict) -> None:
        """Store a proposed layout awaiting user acceptance."""
        self._state["pending_layout"] = data

    def clear_pending(self) -> None:
        """Clear the pending layout proposal."""
        self._state["pending_layout"] = None
