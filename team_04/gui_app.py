import json
from datetime import datetime, timezone

import streamlit as st


st.set_page_config(page_title="TerraPilot Site Agent", layout="wide")

st.title("TerraPilot — Site Agent Draft")
st.caption("Yeni taslak başlangıcı: önce iskelet, sonra detaylandırma.")

if "draft_log" not in st.session_state:
    st.session_state.draft_log = []
if "latest_draft" not in st.session_state:
    st.session_state.latest_draft = None

with st.sidebar:
    st.header("Draft Inputs")
    project_name = st.text_input("Project name", value="New Site Study")
    site_width = st.number_input("Site width (m)", min_value=1.0, value=100.0, step=1.0)
    site_depth = st.number_input("Site depth (m)", min_value=1.0, value=80.0, step=1.0)
    target_gfa = st.number_input("Target GFA (m²)", min_value=1.0, value=8000.0, step=100.0)
    prompt = st.text_area("Design prompt", value="Create an initial massing option for this site.")

    if st.button("Create draft"):
        draft = {
            "project_name": project_name,
            "site": {
                "width_m": site_width,
                "depth_m": site_depth,
                "area_m2": round(site_width * site_depth, 2),
            },
            "target_gfa_m2": target_gfa,
            "prompt": prompt.strip(),
            "status": "draft_initialized",
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        st.session_state.latest_draft = draft
        st.session_state.draft_log.append(
            f"{datetime.now().strftime('%H:%M:%S')} — Draft initialized for '{project_name}'."
        )
        st.success("Draft created. You can now iterate on details.")

left_col, right_col = st.columns([2, 1])

with left_col:
    st.subheader("Viewport (placeholder)")
    st.info("Site/geometry preview will appear here as we add tool integrations.")
    st.code(
        "┌───────────────────────────┐\n"
        "│       SITE VIEWPORT       │\n"
        "│    (2D/3D preview area)   │\n"
        "└───────────────────────────┘"
    )

    st.subheader("Draft JSON")
    if st.session_state.latest_draft:
        st.json(st.session_state.latest_draft)
    else:
        st.write("No draft yet. Fill inputs and click **Create draft**.")

with right_col:
    st.subheader("Agent Activity")
    if st.session_state.draft_log:
        for item in reversed(st.session_state.draft_log[-10:]):
            st.write(f"- {item}")
    else:
        st.write("No activity yet.")

st.divider()
st.subheader("Notes")
st.write(
    "This is a reset baseline for the site-agent UI. Next iterations can plug in "
    "MCP tools, real geometry previews, and richer TerraPilot workflows."
)

if st.session_state.latest_draft:
    st.download_button(
        label="Download latest draft as JSON",
        data=json.dumps(st.session_state.latest_draft, indent=2),
        file_name="terrapilot_site_draft.json",
        mime="application/json",
    )
