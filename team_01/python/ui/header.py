from __future__ import annotations
import json
import streamlit as st
from ui.state import AppState


def render_header(s: AppState) -> None:
    """Top page header: layout-id + stat chips, theme toggle, Export JSON/PDF, and the kebab (⋮) menu with Diagnostics."""
    _is_light = s.is_light
    layout_obj = s.layout_obj
    er = s.eval_result
    _lid = s.lid
    n_cols = s.n_cols
    n_beams = s.n_beams
    _has_fail = s.has_fail
    _mat_now = s.mat_now
    _user_name = s.user_name
    _user_email = s.user_email
    _f = s.fns
    _sheet_pdf_bytes = _f["sheet_pdf_bytes"]
    _count_elements = _f["count_elements"]
    _materials_present = _f["materials_present"]
    is_multilevel = _f["is_multilevel"]
    get_level_count = _f["get_level_count"]
    _llm_is_reachable = _f["llm_is_reachable"]
    _write_json = _f["write_json"]
    EDITED_LAYOUT_PATH = s.edited_layout_path
    _cf_h  = st.session_state.get("cost_flexibility")
    # Title takes the slack; the action buttons share equal widths so they line up.
    _hcols = st.columns([3.4, 1.1, 1.1, 1.1, 1.1, 0.5], gap="small", vertical_alignment="center")

    with _hcols[0]:
        _rev_chip  = ('<span class="stat-chip needs-review">⚠ Review</span>'
                      if _has_fail else "")
        _cost_chip = (f'<span class="stat-chip">net <b>${_cf_h["net_cost_usd"]:+,.0f}</b></span>'
                      if _cf_h else "")
        _user_chip = (f'<span class="stat-chip" title="{_user_email}">👤 <b>{_user_name}</b></span>'
                      if _user_name else "")
        st.markdown(
            f'<div class="page-hdr">'
            f'<span class="hdr-lid">{_lid}</span>'
            f'<span class="stat-chip"><b>{n_cols}</b> col</span>'
            f'<span class="stat-chip"><b>{n_beams}</b> beam</span>'
            f'<span class="stat-chip"><b>{_mat_now}</b></span>'
            f'{_cost_chip}{_rev_chip}{_user_chip}</div>',
            unsafe_allow_html=True,
        )
    with _hcols[1]:
        if st.button("Light" if not _is_light else "Dark",
                     width="stretch", key="btn_theme"):
            st.session_state.theme        = "light" if not _is_light else "dark"
            st.session_state.viewer_nonce += 1
            st.rerun()
    with _hcols[2]:
        _undo_hist = st.session_state.get("versionHistory", [])
        if st.button("↶ Back", width="stretch", key="btn_undo",
                     disabled=not _undo_hist,
                     help="Undo the last change — revert to the previous version."):
            _hist = st.session_state.versionHistory
            _prev = _hist.pop()
            st.session_state.versionHistory = _hist
            st.session_state.currentLayout  = _prev
            st.session_state.currentVersion = max(1, st.session_state.get("currentVersion", 1) - 1)
            st.session_state.eval_result = None   # geometry may have changed → re-run analysis
            st.session_state.eval_alts   = []
            st.session_state.selected_el = ""
            st.session_state.active_element_level = ""
            st.session_state["selected_opt_bar_idx"] = -1
            _write_json(EDITED_LAYOUT_PATH, _prev)
            st.rerun()
    with _hcols[3]:
        st.download_button(
            "Export JSON",
            data=json.dumps(layout_obj, indent=2, ensure_ascii=False),
            file_name="layout_export.json",
            mime="application/json",
            width="stretch",
        )
    with _hcols[4]:
        _revs = tuple(
            (h.get("prompt") or h.get("label") or "")
            for h in st.session_state.get("history", [])[-7:]
        )
        # Single export entry point — pick which design + whether to show labels.
        _export_choices: dict[str, tuple[str, str]] = {
            "Current design": (json.dumps(layout_obj), json.dumps(er) if er else "")
        }
        for _gi_x, _go_x in enumerate(st.session_state.get("grid_options", []), 1):
            _ev_x = _go_x.get("evaluation")
            _export_choices[f"Grid Option {_gi_x}"] = (
                json.dumps(_go_x.get("layout", {})), json.dumps(_ev_x) if _ev_x else "")
        for _sn_x in st.session_state.get("snapshots", []):
            _ev_x = _sn_x.get("eval_result")
            _export_choices[_sn_x["label"]] = (
                _sn_x["layout_json"], json.dumps(_ev_x) if _ev_x else "")

        with st.popover("⤓ Export", width="stretch"):
            _exp_sel = st.selectbox("Design to export", list(_export_choices.keys()),
                                    key="exp_design_sel")
            _exp_lbl = st.checkbox("Show element labels", value=True, key="exp_show_labels")
            _exp_lj, _exp_ej = _export_choices.get(_exp_sel, (json.dumps(layout_obj), ""))
            _prep = (f"{_user_name} ({_user_email})" if _user_name else "")
            try:
                _exp_data = _sheet_pdf_bytes(_exp_lj, _exp_ej, str(_lid), str(_mat_now),
                                             _revs, _exp_lbl, "", "", _prep)
                st.download_button(
                    "⤓ Download sheet (PDF)", data=_exp_data,
                    file_name=f"{_lid}_{_exp_sel.replace(' ', '_')}.pdf",
                    mime="application/pdf", width="stretch", key="exp_dl_btn",
                )
            except Exception as _ee:
                st.caption(f"Export failed: {_ee}")
    with _hcols[5]:
        with st.popover("⋮", width="stretch"):
            st.markdown(
                f'<div style="font-size:.72rem;font-weight:700;color:#c8eeed;'
                f'margin-bottom:6px">PermanenceOS</div>'
                f'<div style="font-size:.65rem;color:#5a9090">AI Structural Design</div>'
                + (f'<div style="font-size:.62rem;color:#5a9090;margin-top:4px">'
                   f'Signed in: <b style="color:#c8eeed">{_user_name}</b><br>{_user_email}</div>'
                   if _user_name else ""),
                unsafe_allow_html=True,
            )
            st.divider()
            if _user_name and st.button("Sign out", key="btn_sign_out", width="stretch"):
                # work is already persisted per-email; just drop the session identity
                st.session_state.user_name = ""
                st.session_state.user_email = ""
                st.rerun()
            if _user_name and st.button("🗑 Clear my saved work", key="btn_clear_work",
                                        width="stretch",
                                        help="Delete your saved layout & snapshots and start fresh (stays signed in)."):
                _f["clear_user_store"]()
                st.rerun()
            if st.button("Rerun", key="btn_menu_rerun", width="stretch"):
                st.rerun()
            _theme_lbl = "Switch to Light" if not _is_light else "Switch to Dark"
            if st.button(_theme_lbl, key="btn_menu_theme", width="stretch"):
                st.session_state.theme        = "light" if not _is_light else "dark"
                st.session_state.viewer_nonce += 1
                st.rerun()
            st.toggle("🐞 Debug mode", key="debug_mode",
                      help="Show diagnostics and full error tracebacks for fast problem-finding.")
            with st.expander("Diagnostics", expanded=bool(st.session_state.get("debug_mode"))):
                _diag_cols, _diag_beams = _count_elements(layout_obj)
                _diag_mats = ", ".join(l for _c, l in _materials_present(layout_obj)) or "none"
                _diag_sm = (er or {}).get("summary", {})
                _diag_err = st.session_state.get("_last_error", "")
                st.markdown(
                    f"<div style='font-size:.66rem;line-height:1.7;font-family:monospace'>"
                    f"version: <b>{st.session_state.get('currentVersion', 0)}</b><br>"
                    f"multilevel: <b>{is_multilevel(layout_obj)}</b> · levels: <b>{get_level_count(layout_obj)}</b><br>"
                    f"columns: <b>{_diag_cols}</b> · beams: <b>{_diag_beams}</b><br>"
                    f"materials: <b>{_diag_mats}</b><br>"
                    f"eval: <b>{'PASS' if _diag_sm.get('overall_PASS') else ('FAIL' if er else '—')}</b> "
                    f"({_diag_sm.get('beam_failures', 0)}B / {_diag_sm.get('column_failures', 0)}C fail)<br>"
                    f"selected: <b>{st.session_state.get('selected_el') or '—'}</b><br>"
                    f"diff baseline set: <b>{st.session_state.get('diff_baseline') is not None}</b><br>"
                    f"LLM reachable: <b>{_llm_is_reachable()}</b>"
                    f"</div>",
                    unsafe_allow_html=True,
                )
                if _diag_err:
                    st.error(_diag_err)
                if st.button("Clear last error", key="btn_clear_err", width="stretch"):
                    st.session_state["_last_error"] = ""
                    st.rerun()
