from __future__ import annotations
import json
import streamlit as st
from ui.state import AppState


def render_sidebar(s: AppState):
    """Left sidebar: brand, INPUTS (upload / loads / material / OK), Generate-Grid + option cards, and the AI-Agent chat form. Returns (prompt_input, submitted)."""
    t = s.tokens
    _BORD = t["BORD"]; _CARD = t["CARD"]; _ACC = t["ACC"]; _TEXT = t["TEXT"]; _MUT = t["MUT"]
    _is_light = s.is_light
    layout_obj = s.layout_obj
    _sdl_now = s.sdl_now; _ll_now = s.ll_now; _mat_now = s.mat_now
    _logo_b64_light = s.logo_light; _logo_b64_dark = s.logo_dark
    EDITED_LAYOUT_PATH = s.edited_layout_path; REPO_ROOT = s.repo_root
    _f = s.fns
    _normalize_layout = _f["normalize_layout"]; _strip_structure = _f["strip_structure"]
    _write_json = _f["write_json"]; _sync_viewers = _f["sync_viewers"]
    _run_grid_options = _f["run_grid_options"]; _push_version = _f["push_version"]
    _run_evaluate = _f["run_evaluate"]; _get_failure_alternatives = _f["get_failure_alternatives"]
    _grid_option_kpis = _f["grid_option_kpis"]; _grid_option_description = _f["grid_option_description"]
    prompt_input = ""
    submitted    = False

    with st.sidebar:
        _active_logo = _logo_b64_light if _is_light else _logo_b64_dark
        if _active_logo:
            st.markdown(
                f'<img src="data:image/png;base64,{_active_logo}"'
                f' style="width:100%;max-height:120px;object-fit:contain;'
                f'object-position:left center;display:block;margin-bottom:6px">',
                unsafe_allow_html=True,
            )
        else:
            st.markdown(
                '<div class="sb-brand">PermanenceOS</div>'
                '<div class="sb-sub">AI-Powered Structural Design</div>',
                unsafe_allow_html=True,
            )

        # ── INPUTS dropdown ───────────────────────────────────────────────────────
        _lid = layout_obj.get("layoutId", "")   # always defined for page header use

        with st.expander("INPUTS", expanded=True):

            # ── Upload ────────────────────────────────────────────────────────────
            st.markdown(
                f'<div class="inp-sub-hdr">Upload</div>',
                unsafe_allow_html=True,
            )
            _upload = st.file_uploader(
                "layout", type=["json"], label_visibility="collapsed", key="sb_uploader"
            )
            # Only process the file when it is genuinely new (name+size changed).
            # Without this guard the handler runs on EVERY rerun while the file
            # sits in the uploader, calling st.rerun() each time and preventing
            # any other button (OK, agent, etc.) from executing.
            if _upload is not None:
                _upload_fp = (_upload.name, _upload.size)
                if _upload_fp != st.session_state.get("_last_upload_fp"):
                    try:
                        _loaded = _normalize_layout(json.loads(_upload.getvalue().decode("utf-8")))
                        # Strip any pre-built structure from the JSON so the user always
                        # starts with a blank design and must press "Generate Grid" explicitly.
                        _loaded = _strip_structure(_loaded)
                        # Reset all derived state — new file, clean slate
                        for _k in ("eval_result", "eval_alts", "agent_log", "grid_options",
                                   "selected_grid", "cost_flexibility", "last_comparison",
                                   "history", "state_history", "output_log", "snapshots"):
                            st.session_state[_k] = (
                                [] if isinstance(st.session_state.get(_k), list) else None)
                        st.session_state.currentLayout   = _loaded
                        st.session_state.versionHistory  = []
                        st.session_state.currentVersion  = 1
                        st.session_state.setupDone       = False
                        st.session_state.selected_el     = ""
                        st.session_state.active_level    = "level_01"
                        st.session_state.active_element_level = ""
                        st.session_state["_last_upload_fp"]      = _upload_fp
                        st.session_state["_last_url_sel"]        = "\x00"
                        st.session_state["_last_url_lvl"]        = "\x00"
                        st.session_state["selected_opt_bar_idx"] = -1
                        _write_json(EDITED_LAYOUT_PATH, _loaded)
                        st.rerun()
                    except Exception as _exc:
                        st.error(f"Invalid JSON: {_exc}")
            if _lid:
                st.markdown(
                    f'<div class="sb-filename">{_lid}</div>'
                    f'<div class="sb-success">✓ Model loaded — press OK ▶ Apply & Render</div>',
                    unsafe_allow_html=True,
                )
                if st.button("↺  Clear & Reset", width="stretch",
                             key="btn_reset_layout"):
                    # Wipe everything — user must re-upload
                    for _rk, _rv in {
                        "currentLayout": None, "versionHistory": [], "currentVersion": 0,
                        "setupDone": False, "_last_upload_fp": None,
                        "eval_result": None, "eval_alts": [], "agent_log": [],
                        "grid_options": [], "selected_grid": None,
                        "cost_flexibility": None, "last_comparison": None,
                        "history": [], "state_history": [], "output_log": [],
                        "snapshots": [], "selected_el": "",
                        "active_level": "level_01", "active_element_level": "",
                        "_last_url_sel": "\x00", "selected_opt_bar_idx": -1,
                        "_last_url_lvl": "\x00",
                    }.items():
                        st.session_state[_rk] = _rv
                    if EDITED_LAYOUT_PATH.exists():
                        EDITED_LAYOUT_PATH.unlink()
                    st.rerun()

            st.divider()

            # ── Define Loads ──────────────────────────────────────────────────────
            st.markdown(
                f'<div class="inp-sub-hdr">Define Loads</div>',
                unsafe_allow_html=True,
            )
            with st.expander("What do these mean?", expanded=False):
                st.markdown(
                    "- **SDL — Superimposed Dead Load**: permanent weight *on top of* the "
                    "structure's own self-weight — floor finishes, screed, partitions, ceilings, "
                    "services. Typical **2.5–3.5 kN/m²**.\n"
                    "- **LL — Live Load**: movable/occupancy load (people, furniture). Code values: "
                    "**residential ≈2.0**, **office ≈3.0**, **assembly/retail ≈5.0 kN/m²**.\n"
                    "- Higher loads → larger sections / closer columns. Pick the use that matches "
                    "your building before generating a grid."
                )
            _sdl_opts = {1.5: "1.5", 2.5: "2.5", 3.5: "3.5", 5.0: "5.0"}
            _sdl_v = st.select_slider(
                "Dead Load SDL (kN/m²)", list(_sdl_opts.keys()),
                value=_sdl_now, format_func=lambda v: f"{v} kN/m²",
                help="Permanent load on top of self-weight: finishes, screed, partitions, "
                     "services. Typical 2.5–3.5 kN/m².",
            )
            if _sdl_v != _sdl_now:
                st.session_state.sdl_kNm2 = _sdl_v

            _ll_opts = {2.0: "2.0", 3.0: "3.0", 5.0: "5.0"}
            _ll_v = st.select_slider(
                "Live Load LL (kN/m²)", list(_ll_opts.keys()),
                value=_ll_now, format_func=lambda v: f"{v} kN/m²",
                help="Occupancy load (people, furniture): residential ≈2.0, office ≈3.0, "
                     "assembly/retail ≈5.0 kN/m².",
            )
            if _ll_v != _ll_now:
                st.session_state.live_load_kNm2 = _ll_v

            st.divider()

            # ── Define Materials ──────────────────────────────────────────────────
            st.markdown(
                f'<div class="inp-sub-hdr">Define Materials</div>',
                unsafe_allow_html=True,
            )
            _MAT_LABELS = {"RCC": "Concrete", "STEEL": "Steel", "TIMBER": "Timber"}
            mat_choice = st.radio(
                "Material", list(_MAT_LABELS.keys()),
                format_func=lambda k: _MAT_LABELS[k],
                index=list(_MAT_LABELS.keys()).index(_mat_now),
                horizontal=True, label_visibility="collapsed",
                help="Concrete (RCC): heavy, cheap, fire-resistant, moderate spans. "
                     "Steel: light, strong, long spans, higher cost. "
                     "Timber: lightest & low-carbon but needs larger sections / shorter spans.",
            )
            if mat_choice != _mat_now:
                st.session_state.material     = mat_choice
                st.session_state.grid_options = []
                st.session_state.setupDone    = False   # require OK again after material change

            # ── OK button — commits loads/material into layout metadata and enables viewers
            _ok_disabled = st.session_state.currentLayout is None
            if st.button(
                "OK  ▶  Apply & Render",
                width="stretch", type="primary",
                key="btn_ok_apply", disabled=_ok_disabled,
            ):
                if st.session_state.currentLayout is not None:
                    _cl = st.session_state.currentLayout
                    if "meta" not in _cl or not isinstance(_cl.get("meta"), dict):
                        _cl["meta"] = {}
                    _cl["meta"]["material"] = mat_choice
                    _cl["meta"]["SDL"]      = st.session_state.sdl_kNm2
                    _cl["meta"]["LL"]       = st.session_state.live_load_kNm2
                    st.session_state.currentLayout = _cl
                    _write_json(EDITED_LAYOUT_PATH, _cl)
                    st.session_state.setupDone  = True
                    st.session_state.material   = mat_choice
                    _sync_viewers()
                    st.rerun()

        # ── Generate Grid + Options ───────────────────────────────────────────────
        st.markdown(
            f'<div style="margin:8px 0 6px;border-top:1px solid {_BORD}"></div>',
            unsafe_allow_html=True,
        )
        _gopts_sb  = st.session_state.grid_options
        _gate_off  = not st.session_state.get("setupDone", False)
        st.checkbox(
            "Respect openings", value=st.session_state.get("respect_openings", False),
            key="respect_openings",
            help="Optional: nudge INTERNAL grid-lines off doors/windows when generating "
                 "(perimeter columns are never moved). Off = the clean grid that follows "
                 "the building outline exactly.",
        )
        if st.button("⊕  Generate Grid", width="stretch",
                     type="primary", key="btn_gen_main", disabled=_gate_off):
            with st.spinner("Computing grid options…"):
                st.session_state.grid_options = _run_grid_options(layout_obj, _mat_now)
            # Auto-apply option 1 so structure is immediately available
            if st.session_state.grid_options:
                _auto_opt = st.session_state.grid_options[0].get("layout", {})
                if _auto_opt:
                    _push_version(_auto_opt)
                    st.session_state.diff_baseline = json.loads(json.dumps(_auto_opt))
            st.session_state["selected_opt_bar_idx"] = 0
            st.rerun()

        if _gopts_sb:
            for _bi, _gopt_sb in enumerate(_gopts_sb[:3]):
                _is_sel_sb = st.session_state.get("selected_opt_bar_idx", -1) == _bi
                _kpis = _grid_option_kpis(_gopt_sb.get("layout", {}))
                _desc  = _grid_option_description(_bi, _kpis)
                _bcard_bg  = f"background:{'rgba(42,192,192,0.10)' if _is_sel_sb else _CARD}"
                _bcard_brd = f"border:1px solid {_ACC if _is_sel_sb else _BORD}"
                st.markdown(
                    f'<div style="{_bcard_bg};{_bcard_brd};border-radius:8px;'
                    f'padding:8px 10px;margin-bottom:6px">'
                    f'<div style="font-size:.63rem;font-weight:700;color:{"#2ac0c0" if _is_sel_sb else _TEXT};'
                    f'margin-bottom:4px">Option {_bi+1}'
                    f'{"  ✓ Active" if _is_sel_sb else ""}</div>'
                    f'<div style="font-size:.60rem;color:{_MUT};line-height:1.55;margin-bottom:6px">{_desc}</div>'
                    f'<div style="display:flex;gap:8px;flex-wrap:wrap">'
                    f'<span style="font-size:.60rem;color:{_TEXT}">⬛ {_kpis["n_cols"]} col</span>'
                    f'<span style="font-size:.60rem;color:{_TEXT}">— {_kpis["n_beams"]} beam</span>'
                    f'<span style="font-size:.60rem;color:{_TEXT}">↔ max {_kpis["max_span"]}m</span>'
                    f'<span style="font-size:.60rem;color:{_TEXT}">avg {_kpis["avg_span"]}m</span>'
                    f'</div></div>',
                    unsafe_allow_html=True,
                )
                if st.button(
                    f"Apply Option {_bi+1}", key=f"sb_opt_{_bi}",
                    width="stretch",
                    type="primary" if _is_sel_sb else "secondary",
                ):
                    _opt_layout = _gopt_sb.get("layout", {})
                    _opt_ev = _gopt_sb.get("evaluation")
                    if _opt_ev is None:
                        with st.spinner(f"Evaluating Option {_bi+1}…"):
                            _opt_ev = _run_evaluate(
                                json.dumps(_opt_layout),
                                sdl=_sdl_now, ll=_ll_now)
                        if _opt_ev:
                            st.session_state.grid_options[_bi]["evaluation"] = _opt_ev
                    if _opt_layout:
                        _push_version(_opt_layout)
                        st.session_state.diff_baseline = json.loads(json.dumps(_opt_layout))
                    st.session_state["selected_opt_bar_idx"] = _bi
                    st.session_state.eval_result = _opt_ev
                    st.session_state.eval_alts = _get_failure_alternatives(
                        _opt_ev or {}, _mat_now)
                    st.rerun()

        # ── AI AGENT ──────────────────────────────────────────────────────────────
        st.markdown(
            f'<div style="border-top:1px solid {_BORD};margin:10px 0 6px"></div>'
            f'<div style="font-size:.76rem;font-weight:700;color:{_TEXT};margin-bottom:4px">'
            f'AI Agent <span class="beta">BETA</span></div>',
            unsafe_allow_html=True,
        )
        _history = st.session_state.get("history", [])
        if _history:
            _bub = ""
            for _msg in _history[-8:]:
                _q = _msg.get("prompt", "")
                _a = _msg.get("response", "")
                if _q:
                    _bub += f'<div class="chat-q">{_q}</div>'
                if _a:
                    _bub += f'<div class="chat-a">{_a}</div>'
            st.markdown(
                f'<div style="max-height:460px;overflow-y:auto;margin-bottom:8px">{_bub}</div>',
                unsafe_allow_html=True,
            )

        with st.form("agent_form", clear_on_submit=True):
            prompt_input = st.text_area(
                "Ask agent",
                placeholder="Ask anything about your structure…\ne.g. remove column C4 / explain beam B1 failure",
                label_visibility="collapsed",
                height=150,
            )
            submitted = st.form_submit_button("Ask Agent  ›", width="stretch")

        # ── AI Recommendations (shown in ANALYSIS tab) ────────────────────────────
        _alts_sb = st.session_state.eval_alts
        if _alts_sb:
            st.markdown(
                f'<div style="font-size:.63rem;color:{_MUT};margin-top:8px;line-height:1.6">'
                f'{len(_alts_sb)} recommendation{"s" if len(_alts_sb)>1 else ""} ready — '
                f'open the <b style="color:{_ACC}">Analysis</b> tab to preview or apply.</div>',
                unsafe_allow_html=True,
            )
        else:
            st.markdown(
                f'<div style="font-size:.63rem;color:{_MUT};margin-top:8px;line-height:1.5">'
                f'Generate a grid and run analysis to see AI recommendations.</div>',
                unsafe_allow_html=True,
            )

    return prompt_input, submitted
