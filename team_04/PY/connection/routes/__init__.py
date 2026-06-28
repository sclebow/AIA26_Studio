"""Thin API routes — request → runtime module → response.

These routes contain NO business logic. Each one validates input and delegates to
a connection.notebook_logic.* runtime module (the single shared implementation
used by the notebooks too). They are registered additively in connection/app.py
under the /api prefix, alongside the pre-existing /sessions, /site, /export routers.
"""
from __future__ import annotations

from .. import _TEAM_ROOT  # noqa: F401  (side-effect import — puts team_04/ on sys.path)
