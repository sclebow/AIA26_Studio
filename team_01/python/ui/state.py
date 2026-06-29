from __future__ import annotations
"""Shared UI context for the extracted renderers (ui/header.py, ui/sidebar.py, …).

`AppState` is built once per Streamlit run in app.py and passed to each renderer so
they don't depend on app.py's module globals. It carries:
  - `tokens`: the `ui.theme.theme_tokens()` dict (renderers unpack what they need),
  - `fns`:    helper-name → app.py function, passed in to avoid importing app.py back
              (which would be circular),
  - data fields (layout_obj, eval_result, element counts, loads/material, …) set as
    they become available during the run.

Renderers follow the same safe pattern as ui/theme.build_css: a short preamble that
unpacks `tokens`/`fns`/data into the original local names, then the verbatim body.
"""
from dataclasses import dataclass, field
from typing import Any, Callable


@dataclass
class AppState:
    tokens: dict[str, Any]
    fns: dict[str, Callable]
    is_light: bool = False
    layout_obj: dict = field(default_factory=dict)
    eval_result: dict | None = None
    lid: str = ""
    n_cols: int = 0
    n_beams: int = 0
    has_fail: bool = False
    mat_now: str = "RCC"
    sdl_now: float = 3.5
    ll_now: float = 2.0
    logo_light: str = ""
    logo_dark: str = ""
    edited_layout_path: Any = None
    repo_root: Any = None
    user_name: str = ""
    user_email: str = ""
