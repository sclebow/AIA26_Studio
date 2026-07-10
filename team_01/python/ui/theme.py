from __future__ import annotations
"""Theme tokens + the app stylesheet, extracted from app.py.
`theme_tokens(is_light)` -> dict of colour/font tokens; `build_css(t)` -> CSS string."""


def theme_tokens(is_light: bool) -> dict:
    _is_light = is_light
    if _is_light:
        _BG="#f0f7f7"; _SB="#e2eeee"; _CARD="#ffffff"; _ACC="#088a87"; _ACC2="#40a090"
        _BORD="#c0d8d8"; _TEXT="#1a2a30"; _MUT="#5a7070"; _DIM="#8aacac"
        _FAIL="#c02020"; _PASS_C="#097040"; _PASS_BG="#d0f4e8"; _FAIL_BG="#fce8e8"
        _CHAT_Q="#ddeef0"; _CHAT_A="#f0f9f9"; _NUM1_BG=_ACC; _NUM1_C="#fff"
        _NUM2_BG="#c07020"; _NUM3_BG="#3070a0"
        _HIGH_BG="#d4f0d4"; _HIGH_C="#1a7020"
        _MED_BG="#f4e4b0";  _MED_C="#806010"
        _LOW_BG="#c8ddf0";  _LOW_C="#2060a0"
        _LOAD_BG="#eef6f6"; _SNAP_BG="#e0eef0"
    else:
        _BG="#071a1a"; _SB="#091f1f"; _CARD="#0d2828"; _ACC="#2ac0c0"; _ACC2="#222D28"
        _BORD="#1a4040"; _TEXT="#c8eeed"; _MUT="#5a9090"; _DIM="#3a6060"
        _FAIL="#ff5050"; _PASS_C="#40d090"; _PASS_BG="#0a3020"; _FAIL_BG="#300a0a"
        _CHAT_Q="#0a3030"; _CHAT_A="#071a1a"; _NUM1_BG=_ACC; _NUM1_C="#071a1a"
        _NUM2_BG="#c07020"; _NUM3_BG="#3070a0"
        _HIGH_BG="#0d2e0d"; _HIGH_C="#60d060"
        _MED_BG="#2e2400";  _MED_C="#d0a020"
        _LOW_BG="#0a1e30";  _LOW_C="#40a0c8"
        _LOAD_BG="#0d2020"; _SNAP_BG="#0d2020"

    _F = "'Suisse Intl','Suisse Int\\'l','Inter','Segoe UI',system-ui,sans-serif"
    return ({k[1:]: v for k, v in locals().items()
             if k.startswith("_") and k != "_is_light"} | {"is_light": is_light})


def build_css(t: dict) -> str:
    _BG=t["BG"]; _SB=t["SB"]; _CARD=t["CARD"]; _ACC=t["ACC"]; _ACC2=t["ACC2"]; _BORD=t["BORD"]; _TEXT=t["TEXT"]; _MUT=t["MUT"]; _DIM=t["DIM"]; _FAIL=t["FAIL"]; _PASS_C=t["PASS_C"]; _PASS_BG=t["PASS_BG"]; _FAIL_BG=t["FAIL_BG"]; _CHAT_Q=t["CHAT_Q"]; _CHAT_A=t["CHAT_A"]; _NUM1_BG=t["NUM1_BG"]; _NUM1_C=t["NUM1_C"]; _NUM2_BG=t["NUM2_BG"]; _NUM3_BG=t["NUM3_BG"]; _HIGH_BG=t["HIGH_BG"]; _HIGH_C=t["HIGH_C"]; _MED_BG=t["MED_BG"]; _MED_C=t["MED_C"]; _LOW_BG=t["LOW_BG"]; _LOW_C=t["LOW_C"]; _LOAD_BG=t["LOAD_BG"]; _SNAP_BG=t["SNAP_BG"]; _F=t["F"]; _is_light=t["is_light"]
    return f"""
@import url('https://fonts.cdnfonts.com/css/suisse-intl');
/* ── Universal font: all text elements except icon spans ────────────────── */
html,body,p,h1,h2,h3,h4,h5,h6,
div,section,article,aside,header,main,footer,nav,
label,a,li,td,th,caption,
input,textarea,select,option,
button,
[data-testid]:not([data-testid="stIconMaterial"]){{
  font-family:{_F}!important;
  -webkit-font-smoothing:antialiased!important;
  -moz-osx-font-smoothing:grayscale!important;
}}
/* ── Restore Material Symbols for Streamlit icon spans ───────────────────── */
[data-testid="stIconMaterial"],
[class*="material-symbols"],
[class*="material-icons"]{{
  font-family:'Material Symbols Rounded','Material Symbols Sharp','Material Icons Rounded','Material Icons'!important;
  font-feature-settings:'liga'!important;
  -webkit-font-feature-settings:'liga'!important;
}}
/* ── Buttons: always fit text, no overflow ───────────────────────────────── */
button{{overflow:hidden!important}}
button>div,button p,button span:not([data-testid="stIconMaterial"]){{
  overflow:hidden!important;text-overflow:ellipsis!important;white-space:nowrap!important;
}}
/* ── Type scale (5 steps) ──────────────────────────────────────────────── */
/* xs=0.63rem  sm=0.70rem  md=0.78rem  lg=0.88rem  xl=1.0rem             */
html,body,[data-testid="stApp"],[data-testid="stAppViewContainer"],[data-testid="stMain"]{{
  background:{_BG}!important;font-family:{_F}!important;font-size:13px!important;
  letter-spacing:.01em!important}}
[data-testid="block-container"]{{padding:.3rem 1rem .2rem!important;max-width:100%!important}}
section[data-testid="stSidebar"]{{
  background:{_SB}!important;border-right:1px solid {_BORD}!important;
  width:clamp(280px,24vw,380px)!important;min-width:280px!important;
  flex:0 1 clamp(280px,24vw,380px)!important}}
section[data-testid="stSidebar"]>div:first-child{{padding:14px 14px 10px!important}}
/* ── Responsive: never clip text; reflow on smaller / zoomed screens ───────── */
.page-hdr,.plan-legend{{flex-wrap:wrap!important}}
.stat-chip,.hdr-lid{{white-space:normal!important;overflow:visible!important}}
/* buttons & download buttons wrap their labels rather than truncating */
.stButton>button,[data-testid="stDownloadButton"]>button,[data-testid="stPopover"]>button{{
  white-space:normal!important;height:auto!important;line-height:1.25!important;min-height:0!important}}
@media (max-width:1500px){{
  html,body,[data-testid="stAppViewContainer"]{{font-size:12px!important}}
  section[data-testid="stSidebar"]{{width:clamp(260px,22vw,340px)!important;min-width:260px!important;
    flex:0 1 clamp(260px,22vw,340px)!important;max-width:340px!important}}
}}
@media (max-width:1200px){{
  html,body,[data-testid="stAppViewContainer"]{{font-size:11px!important}}
  [data-testid="block-container"]{{padding:.3rem .5rem!important}}
  section[data-testid="stSidebar"]{{width:clamp(240px,30vw,300px)!important;min-width:240px!important;
    flex:0 1 clamp(240px,30vw,300px)!important;max-width:300px!important}}
}}
.react-resizable-handle{{display:none!important;pointer-events:none!important}}
[data-testid="stSidebarHeader"]{{display:none!important;height:0!important;padding:0!important;margin:0!important}}
section[data-testid="stSidebar"] p,section[data-testid="stSidebar"] label{{color:{_TEXT}!important;font-family:{_F}!important}}
section[data-testid="stSidebar"] [data-testid="stWidgetLabel"] p{{color:{_MUT}!important;font-size:.70rem!important}}
[data-testid="stHeader"],
[data-testid="stStatusWidget"],
[data-testid="stDecoration"],
[data-testid="stToolbar"]{{display:none!important;height:0!important;overflow:hidden!important;padding:0!important;margin:0!important}}
/* ── Tabs ──────────────────────────────────────────────────────────────── */
[data-testid="stTabs"] [data-baseweb="tab-list"]{{background:transparent!important;border-bottom:1px solid {_BORD}!important;gap:0!important;padding:0!important;display:flex!important}}
[data-testid="stTabs"] [data-baseweb="tab"]{{flex:1!important;text-align:center!important;justify-content:center!important;color:{_MUT}!important;font-size:.63rem!important;font-weight:700!important;letter-spacing:1.4px!important;text-transform:uppercase!important;padding:6px 8px!important;border-bottom:2px solid transparent!important;background:transparent!important;font-family:{_F}!important}}
[data-testid="stTabs"] [aria-selected="true"]{{color:{_ACC}!important;border-bottom:2px solid {_ACC}!important}}
[data-testid="stTabs"] [data-baseweb="tab-border"]{{display:none!important}}
[data-testid="stTabPanel"]{{padding-top:6px!important}}
/* ── Form elements ─────────────────────────────────────────────────────── */
[data-testid="stForm"]{{background:{_CARD}!important;border:1px solid {_BORD}!important;border-radius:8px!important;padding:8px!important}}
[data-testid="stTextArea"] textarea{{background:{_CARD}!important;color:{_TEXT}!important;border-color:{_BORD}!important;font-size:.70rem!important;font-family:{_F}!important}}
[data-testid="stTextInput"] input{{background:{_CARD}!important;color:{_TEXT}!important;border-color:{_BORD}!important;font-family:{_F}!important}}
[data-baseweb="select"]>div{{background:{_CARD}!important;border-color:{_BORD}!important;color:{_TEXT}!important;font-family:{_F}!important}}
[data-baseweb="popover"] [role="listbox"]{{background:{_CARD}!important}}
[data-baseweb="popover"] [role="option"]{{color:{_TEXT}!important;font-family:{_F}!important}}
[data-testid="stExpander"] details{{background:{_CARD}!important;border:1px solid {_BORD}!important;border-radius:6px!important}}
[data-testid="stExpander"] summary{{color:{_ACC}!important;font-size:.70rem!important;font-weight:600!important;font-family:{_F}!important}}
/* ── INPUTS dropdown button ────────────────────────────────────────────── */
section[data-testid="stSidebar"] [data-testid="stExpander"]:first-of-type details{{
  background:{_ACC}!important;border:none!important;border-radius:8px!important}}
section[data-testid="stSidebar"] [data-testid="stExpander"]:first-of-type summary{{
  color:#ffffff!important;font-size:.78rem!important;
  font-weight:800!important;letter-spacing:1.2px!important;text-transform:uppercase!important;
  padding:10px 14px!important;font-family:{_F}!important}}
section[data-testid="stSidebar"] [data-testid="stExpander"]:first-of-type details[open]{{
  background:{_CARD}!important;border:1px solid {_ACC}!important}}
section[data-testid="stSidebar"] [data-testid="stExpander"]:first-of-type details[open] summary{{
  color:{_ACC}!important;border-bottom:1px solid {_BORD}!important;margin-bottom:4px!important}}
.inp-sub-hdr{{font-size:.63rem;font-weight:700;color:{_ACC};letter-spacing:1.1px;font-family:{_F};
  text-transform:uppercase;margin:4px 0 6px;padding-bottom:3px;border-bottom:1px solid {_BORD}}}
[data-testid="stFileUploader"] section{{background:{_CARD}!important;border-color:{_BORD}!important}}
[data-testid="stFileUploaderDropzoneInstructions"]{{display:none!important}}
[data-testid="stFileUploaderDropzone"]{{min-height:auto!important;padding:5px 10px!important;background:{_CARD}!important;border-color:{_BORD}!important}}
[data-testid="stRadio"] label p{{color:{_TEXT}!important;font-size:.70rem!important;font-family:{_F}!important}}
[data-testid="stCheckbox"] label p{{color:{_TEXT}!important;font-size:.70rem!important;font-family:{_F}!important}}
[data-testid="stSlider"] [data-baseweb="slider"] [role="slider"]{{background:{_ACC}!important}}
p,label{{color:{_TEXT};font-family:{_F}}}
[data-testid="stMarkdown"] p{{color:{_TEXT};font-family:{_F}}}
small,[data-testid="stCaption"] p{{color:{_MUT}!important;font-size:.63rem!important;font-family:{_F}!important}}
[data-testid="stMetricValue"]{{color:{_TEXT}!important;font-size:.88rem!important;font-family:{_F}!important}}
[data-testid="stMetricLabel"] p{{color:{_MUT}!important;font-size:.63rem!important;font-family:{_F}!important}}
hr{{border-color:{_BORD}!important;margin:8px 0!important}}
button[kind="primary"]{{background:{_ACC}!important;color:#ffffff!important;border:none!important;font-weight:700!important;font-size:.70rem!important;border-radius:6px!important;font-family:{_F}!important;letter-spacing:.3px!important}}
button[kind="secondary"]{{background:transparent!important;color:{_TEXT}!important;border:1px solid {_BORD}!important;font-size:.70rem!important;border-radius:6px!important;font-family:{_F}!important}}
[data-testid="stFormSubmitButton"] button{{color:#ffffff!important}}
/* ── INPUTS expander label ────────────────────────────────────────────── */
section[data-testid="stSidebar"] [data-testid="stExpander"]:first-of-type summary{{
  color:#ffffff!important}}
/* ── Sidebar components ────────────────────────────────────────────────── */
.sb-brand{{font-size:.88rem;font-weight:800;color:{_ACC};letter-spacing:.8px;line-height:1.1;font-family:{_F}}}
.sb-sub{{font-size:.63rem;color:{_MUT};margin-bottom:10px;font-family:{_F}}}
.sb-section{{font-size:.63rem;font-weight:700;color:{_ACC};letter-spacing:1.5px;text-transform:uppercase;margin:12px 0 5px;display:flex;align-items:center;gap:6px;font-family:{_F}}}
.sb-section::after{{content:'';flex:1;height:1px;background:{_BORD}}}
.sb-filename{{font-size:.70rem;font-weight:600;color:{_TEXT};margin:3px 0 1px;font-family:{_F}}}
.sb-success{{font-size:.63rem;color:{_ACC2};font-weight:600;font-family:{_F}}}
.beta{{background:{"#d4f0ee" if _is_light else "#0a3030"};color:{_ACC};font-size:.60rem;font-weight:700;padding:1px 5px;border-radius:3px;vertical-align:middle;margin-left:4px;text-transform:uppercase;letter-spacing:.5px;border:1px solid {_BORD};font-family:{_F}}}
.load-row{{display:flex;justify-content:space-between;font-size:.70rem;padding:3px 0;border-bottom:1px solid {_BORD};color:{_MUT};font-family:{_F}}}
.load-row b{{color:{_TEXT};font-weight:600}}
.load-block{{background:{_LOAD_BG};border:1px solid {_BORD};border-radius:6px;padding:8px 10px}}
/* ── Page header ───────────────────────────────────────────────────────── */
.page-hdr{{display:flex;align-items:center;gap:4px;padding:4px 0 3px;font-family:{_F}}}
.hdr-lid{{font-size:.70rem;color:{_MUT};margin-right:6px;font-family:{_F}}}
.stat-chip{{display:inline-block;background:{"#e8f4f4" if _is_light else "#0d3030"};border:1px solid {_BORD};border-radius:4px;padding:2px 7px;margin-left:3px;font-size:.63rem;color:{_MUT};font-family:{_F}}}
.stat-chip b{{color:{_ACC}}}
.needs-review{{background:{"#fff0e8" if _is_light else "#3a1a08"}!important;color:{"#c04010" if _is_light else "#ff9860"}!important;border-color:{"#d08060" if _is_light else "#7a4020"}!important}}
/* ── Step bar ──────────────────────────────────────────────────────────── */
.step-bar{{display:flex;align-items:center;gap:0;overflow:hidden;padding:2px 0;font-family:{_F}}}
.stp{{display:flex;align-items:center;gap:4px;padding:3px 5px;white-space:nowrap;min-width:0}}
.stp-n{{display:inline-flex;width:20px;height:20px;border-radius:50%;font-size:.60rem;font-weight:800;align-items:center;justify-content:center;flex-shrink:0;font-family:{_F}}}
.stp-done .stp-n{{background:{_ACC};color:{"#fff" if _is_light else "#071a1a"}}}
.stp-active .stp-n{{background:{"#fff" if _is_light else "#0d2828"};color:{_ACC};border:2px solid {_ACC}}}
.stp-todo .stp-n{{background:{"#dde8e8" if _is_light else "#1a3030"};color:{_MUT}}}
.stp-lbl{{font-size:.63rem;font-weight:600;font-family:{_F}}}
.stp-done .stp-lbl{{color:{_TEXT}}}
.stp-active .stp-lbl{{color:{_ACC};font-weight:700}}
.stp-todo .stp-lbl{{color:{_MUT}}}
.stp-sub{{font-size:.60rem;color:{_MUT};font-family:{_F}}}
.stp-arr{{color:{_BORD};font-size:.63rem;margin:0 0px;flex-shrink:0}}
/* ── Plan legend ───────────────────────────────────────────────────────── */
.plan-legend{{display:flex;gap:12px;padding:5px 4px 3px;flex-wrap:wrap;font-family:{_F}}}
.leg-item{{display:flex;align-items:center;gap:4px;font-size:.63rem;color:{_MUT}}}
.leg-col{{width:9px;height:9px;border-radius:50%;background:{_ACC};flex-shrink:0}}
.leg-beam{{width:14px;height:3px;background:{_ACC2};flex-shrink:0;border-radius:1px}}
.leg-wall{{width:14px;height:3px;background:{"#889898" if _is_light else "#445858"};flex-shrink:0}}
.leg-dash{{width:14px;height:0;border-top:2px dashed {_MUT};flex-shrink:0}}
.stat-bar{{background:{_CARD};border:1px solid {_BORD};border-radius:6px;padding:6px 12px;display:flex;gap:12px;align-items:center;flex-wrap:wrap;margin-top:4px;font-family:{_F}}}
.sb-i{{font-size:.63rem;color:{_MUT};white-space:nowrap;font-family:{_F}}}
.sb-i b{{color:{_TEXT};font-weight:600}}
.sb-pass{{background:{_PASS_BG};color:{_PASS_C};font-size:.63rem;font-weight:700;padding:2px 8px;border-radius:10px;white-space:nowrap;font-family:{_F}}}
.sb-fail{{background:{_FAIL_BG};color:{_FAIL};font-size:.63rem;font-weight:700;padding:2px 8px;border-radius:10px;white-space:nowrap;font-family:{_F}}}
.sb-pend{{color:{_MUT};font-size:.63rem;font-family:{_F}}}
/* ── Panel header ──────────────────────────────────────────────────────── */
.panel-hdr{{font-size:.60rem;font-weight:700;color:{_ACC};letter-spacing:1.4px;text-transform:uppercase;margin:4px 0 7px;display:flex;align-items:center;gap:6px;font-family:{_F}}}
.panel-hdr::after{{content:'';flex:1;height:1px;background:{_BORD}}}
/* ── Recommendation cards ──────────────────────────────────────────────── */
.rec-card{{background:{_CARD};border:1px solid {_BORD};border-radius:8px;padding:12px;margin-bottom:9px;font-family:{_F}}}
.rec-top{{display:flex;align-items:center;gap:6px;margin-bottom:4px}}
.rec-n{{display:inline-flex;width:22px;height:22px;border-radius:50%;font-size:.63rem;font-weight:800;align-items:center;justify-content:center;flex-shrink:0;color:#fff;font-family:{_F}}}
.rec-title{{font-size:.78rem;font-weight:700;color:{_TEXT};flex:1;min-width:0;font-family:{_F}}}
.imp-high{{background:{_HIGH_BG};color:{_HIGH_C};font-size:.60rem;font-weight:700;padding:2px 6px;border-radius:8px;text-transform:uppercase;letter-spacing:.3px;white-space:nowrap;font-family:{_F}}}
.imp-med{{background:{_MED_BG};color:{_MED_C};font-size:.60rem;font-weight:700;padding:2px 6px;border-radius:8px;text-transform:uppercase;letter-spacing:.3px;white-space:nowrap;font-family:{_F}}}
.imp-low{{background:{_LOW_BG};color:{_LOW_C};font-size:.60rem;font-weight:700;padding:2px 6px;border-radius:8px;text-transform:uppercase;letter-spacing:.3px;white-space:nowrap;font-family:{_F}}}
.rec-desc{{font-size:.70rem;color:{_MUT};line-height:1.4;margin-bottom:8px;font-family:{_F}}}
.rec-metrics{{display:flex;gap:0;border-top:1px solid {_BORD};padding-top:8px;margin-bottom:8px}}
.rec-met{{flex:1;text-align:center}}
.rec-met-lbl{{font-size:.60rem;color:{_MUT};text-transform:uppercase;letter-spacing:.3px;margin-bottom:1px;font-family:{_F}}}
.rec-met-pos{{font-size:.70rem;font-weight:700;color:{_PASS_C};font-family:{_F}}}
.rec-met-neg{{font-size:.70rem;font-weight:700;color:{_FAIL};font-family:{_F}}}
/* ── Chat & agent ──────────────────────────────────────────────────────── */
.chat-q{{background:{_CHAT_Q};border-left:3px solid {_ACC};border-radius:4px;padding:7px 10px;margin-bottom:5px;font-size:.92rem;color:{_TEXT};line-height:1.6;font-family:{_F}}}
.chat-a{{background:{_CHAT_A};border-left:3px solid {_ACC2};border-radius:4px;padding:7px 10px;margin-bottom:5px;font-size:.92rem;color:{_TEXT};line-height:1.6;font-family:{_F}}}
/* Larger, clearer agent input in the sidebar */
section[data-testid="stSidebar"] textarea{{font-size:.92rem!important;line-height:1.55!important}}
section[data-testid="stSidebar"] .stForm [data-testid="stFormSubmitButton"] button{{font-size:.84rem!important;font-weight:700!important}}
.agent-resp{{background:{_CHAT_Q};border-left:3px solid {_ACC};padding:8px 10px;border-radius:3px;font-size:.80rem;color:{_TEXT};line-height:1.6;margin-top:5px;font-family:{_F}}}
/* ── Element & analysis ────────────────────────────────────────────────── */
.crit-item{{background:{"#fff4f4" if _is_light else "#200808"};border-left:3px solid {"#cc2020" if _is_light else "#aa2020"};padding:4px 7px;margin-bottom:3px;border-radius:2px;font-size:.70rem;color:{_TEXT};cursor:pointer;font-family:{_F}}}
.pass-badge{{background:{_PASS_BG};color:{_PASS_C};padding:2px 8px;border-radius:4px;font-weight:700;font-size:.70rem;display:inline-block;margin:3px 0;font-family:{_F}}}
.hist-item{{display:flex;gap:8px;margin-bottom:6px;padding-bottom:6px;border-bottom:1px solid {_BORD};font-family:{_F}}}
.hist-dot{{width:7px;height:7px;border-radius:50%;background:{_ACC};margin-top:4px;flex-shrink:0}}
.hist-label{{font-size:.70rem;color:{_TEXT};font-weight:600;font-family:{_F}}}
.hist-sub{{font-size:.63rem;color:{_MUT};font-family:{_F}}}
.log-entry{{background:{_CARD};border-left:3px solid {_ACC};padding:4px 7px;margin-bottom:3px;border-radius:3px;font-size:.70rem;color:{_TEXT};font-family:{_F}}}
/* ── Grid option cards ─────────────────────────────────────────────────── */
.grid-card{{border:1px solid {_BORD};border-radius:6px;padding:6px 9px;margin-bottom:4px;background:{_CARD};font-family:{_F}}}
.grid-card-active{{border-color:{_ACC};background:{"#ddf4f4" if _is_light else "#0d3030"}}}
.grid-label{{font-size:.78rem;font-weight:700;color:{_TEXT};font-family:{_F}}}
.grid-spacing{{font-size:.63rem;color:{_MUT};font-family:{_F}}}
.fail-ct{{color:{_FAIL};font-weight:700}}.pass-ct{{color:{_PASS_C};font-weight:700}}
.snap-pill{{display:inline-block;background:{_SNAP_BG};border:1px solid {_BORD};color:{_MUT};padding:2px 8px;border-radius:10px;margin:2px;font-size:.63rem;font-family:{_F}}}
.snap-pill-active{{border-color:{_ACC};color:{_ACC};font-weight:700}}
/* ── Compare cards ─────────────────────────────────────────────────────── */
.cmp-card-hdr{{background:{"#eef7f7" if _is_light else "#0d2828"};border-bottom:1px solid {_BORD};padding:6px 11px;display:flex;justify-content:space-between;align-items:center;font-family:{_F}}}
.cmp-title{{font-size:.70rem;font-weight:700;color:{_TEXT};font-family:{_F}}}
.badge-curr{{background:{"#d0ecec" if _is_light else "#0d3030"};color:{_ACC};font-size:.60rem;padding:2px 7px;border-radius:8px;font-family:{_F}}}
.badge-opt{{background:{_HIGH_BG};color:{_HIGH_C};font-size:.60rem;padding:2px 7px;border-radius:8px;font-family:{_F}}}
.insight-card{{background:{_CARD};border:1px solid {_BORD};border-radius:8px;padding:10px 12px;margin-bottom:6px;display:flex;align-items:flex-start;gap:10px;font-family:{_F}}}
.insight-ico{{font-size:1.0rem;margin-top:1px}}
.insight-lbl{{font-size:.60rem;color:{_MUT};text-transform:uppercase;letter-spacing:.3px;font-family:{_F}}}
.insight-opt{{font-size:.78rem;font-weight:700;color:{_TEXT};font-family:{_F}}}
.insight-det{{font-size:.63rem;color:{_MUT};font-family:{_F}}}
.rec-box{{background:{_HIGH_BG};border:1px solid {"#90c8a0" if _is_light else "#1a5020"};border-radius:8px;padding:11px;margin-top:7px;font-family:{_F}}}
.rec-box-lbl{{font-size:.60rem;color:{_HIGH_C};text-transform:uppercase;letter-spacing:1px;font-weight:700;margin-bottom:4px;font-family:{_F}}}
.rec-box-txt{{font-size:.70rem;color:{_TEXT};line-height:1.5;font-family:{_F}}}
/* ── Compare table ─────────────────────────────────────────────────────── */
.cmp-tbl{{width:100%;border-collapse:collapse;border:1px solid {_BORD};border-radius:8px;overflow:hidden;font-family:{_F}}}
.cmp-tbl th{{padding:6px 10px;background:{_CARD};border-bottom:1px solid {_BORD};font-size:.63rem;color:{_MUT};text-transform:uppercase;letter-spacing:.6px;text-align:center;font-family:{_F}}}
.cmp-tbl th:first-child{{text-align:left}}
.cmp-tbl td{{padding:6px 10px;font-size:.70rem;text-align:center;border-bottom:1px solid {_BORD};font-family:{_F}}}
.cmp-tbl td:first-child{{text-align:left;color:{_MUT};font-size:.63rem;font-weight:600}}
.cmp-best{{color:{_PASS_C};font-weight:700}}
.cmp-norm{{color:{_TEXT};font-weight:600}}
/* ── Layout ────────────────────────────────────────────────────────────── */
[data-testid="stAppViewContainer"]{{overflow-x:hidden!important}}
[data-testid="stMainBlockContainer"]{{padding:.4rem .8rem .4rem!important;max-width:100%!important}}
[data-testid="block-container"]{{padding:.4rem .8rem .4rem!important;max-width:100%!important}}
/* ── Static sidebar ────────────────────────────────────────────────────── */
[data-testid="collapsedControl"],
[data-testid="stSidebarCollapseButton"],
[data-testid="stSidebarCollapsedControl"],
button[aria-label="Close sidebar"],
button[aria-label="Open sidebar"],
button[aria-label="collapse"],
button[aria-label="expand"]{{display:none!important;pointer-events:none!important}}
section[data-testid="stSidebar"]{{
  width:clamp(280px,24vw,380px)!important;min-width:280px!important;max-width:380px!important;
  transform:translateX(0)!important;transition:none!important;visibility:visible!important}}
section[data-testid="stSidebar"]>div:first-child{{
  width:100%!important;padding:12px 16px 10px!important;overflow-y:auto!important}}
.inp-toggle button{{
  padding:1px 6px!important;min-height:unset!important;font-size:.70rem!important;
  background:transparent!important;border:1px solid {_BORD}!important;
  color:{_MUT}!important;border-radius:4px!important;line-height:1.4!important;font-family:{_F}!important}}
/* ── Compare tab: slightly narrower sidebar to give more room ─────── */
body:has([role="tablist"] [role="tab"]:nth-child(2)[aria-selected="true"])
  [data-testid="stMainBlockContainer"]{{padding-left:.4rem!important;max-width:100%!important}}
"""

