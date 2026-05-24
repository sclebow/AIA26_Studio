from __future__ import annotations

import json
from typing import Any

import streamlit as st


st.set_page_config(
    page_title="TerraPilot",
    page_icon="▣",
    layout="wide",
)


SKETCH_CANVAS = """
<style>
  .tp-canvas-host {
    margin: 0;
    background: #f7f7f2;
    font-family: "IBM Plex Mono", "SFMono-Regular", monospace;
  }
  .tp-canvas-host .toolbar {
    display: flex;
    gap: 8px;
    align-items: center;
    padding: 10px 14px 0 14px;
    color: #2f2f2f;
    font-size: 12px;
  }
  .tp-canvas-host button {
    border: 1px solid #c8c8be;
    background: white;
    color: #202020;
    border-radius: 999px;
    padding: 6px 12px;
    cursor: pointer;
    font: inherit;
  }
  .tp-canvas-host .frame {
    padding: 12px 14px 14px 14px;
  }
  .tp-canvas-host canvas {
    width: 100%;
    height: 480px;
    background:
      linear-gradient(#ecece4 1px, transparent 1px),
      linear-gradient(90deg, #ecece4 1px, transparent 1px),
      #fffdfa;
    background-size: 24px 24px;
    border: 1px solid #d5d5cb;
    border-radius: 18px;
    touch-action: none;
  }
  .tp-canvas-host .hint {
    padding: 8px 14px 0 14px;
    color: #66665f;
    font-size: 11px;
  }
</style>
<div class="tp-canvas-host">
<div class="toolbar">
  <button data-tool="pen">pen</button>
  <button data-tool="erase">erase</button>
  <button data-tool="clear">clear</button>
  <span>freehand site sketch viewport</span>
</div>
<div class="frame">
  <canvas id="site-canvas"></canvas>
</div>
<div class="hint">Drag to sketch massing, site edges, trees, or circulation.</div>
</div>
<script>
  const root = document.currentScript.previousElementSibling;
  const canvas = root.querySelector("#site-canvas");
  const ctx = canvas.getContext("2d");
  let drawing = false;
  let mode = "pen";

  const fitCanvas = () => {
    const ratio = window.devicePixelRatio || 1;
    const rect = canvas.getBoundingClientRect();
    canvas.width = rect.width * ratio;
    canvas.height = rect.height * ratio;
    ctx.setTransform(ratio, 0, 0, ratio, 0, 0);
    ctx.lineJoin = "round";
    ctx.lineCap = "round";
    ctx.lineWidth = 2;
    ctx.strokeStyle = "#202020";
  };

  const point = (event) => {
    const rect = canvas.getBoundingClientRect();
    const source = event.touches ? event.touches[0] : event;
    return {
      x: source.clientX - rect.left,
      y: source.clientY - rect.top,
    };
  };

  const start = (event) => {
    drawing = true;
    const { x, y } = point(event);
    ctx.beginPath();
    ctx.moveTo(x, y);
  };

  const draw = (event) => {
    if (!drawing) return;
    event.preventDefault();
    const { x, y } = point(event);
    ctx.globalCompositeOperation = mode === "erase" ? "destination-out" : "source-over";
    ctx.lineWidth = mode === "erase" ? 18 : 2;
    ctx.strokeStyle = "#202020";
    ctx.lineTo(x, y);
    ctx.stroke();
  };

  const stop = () => {
    drawing = false;
    ctx.closePath();
  };

  root.querySelector('[data-tool="pen"]').onclick = () => { mode = "pen"; };
  root.querySelector('[data-tool="erase"]').onclick = () => { mode = "erase"; };
  root.querySelector('[data-tool="clear"]').onclick = () => {
    ctx.clearRect(0, 0, canvas.width, canvas.height);
  };

  canvas.addEventListener("mousedown", start);
  canvas.addEventListener("mousemove", draw);
  canvas.addEventListener("mouseup", stop);
  canvas.addEventListener("mouseleave", stop);
  canvas.addEventListener("touchstart", start, { passive: false });
  canvas.addEventListener("touchmove", draw, { passive: false });
  canvas.addEventListener("touchend", stop);
  window.addEventListener("resize", fitCanvas);

  fitCanvas();
</script>
"""


APP_CSS = """
<style>
  .stApp {
    background: linear-gradient(180deg, #fbfbf8 0%, #f4f4ef 100%);
    color: #151515;
    font-family: "IBM Plex Mono", "SFMono-Regular", monospace;
  }
  .block-container {
    padding-top: 2rem;
    padding-bottom: 2rem;
    max-width: 1240px;
  }
  .terrapilot-card {
    background: rgba(255, 255, 255, 0.78);
    border: 1px solid #d9d9cf;
    border-radius: 24px;
    padding: 1rem 1.1rem;
    box-shadow: 0 18px 40px rgba(34, 34, 34, 0.05);
  }
  .terrapilot-eyebrow {
    color: #75756c;
    text-transform: uppercase;
    letter-spacing: 0.12em;
    font-size: 0.72rem;
    margin-bottom: 0.35rem;
  }
  .terrapilot-title {
    font-size: 3rem;
    line-height: 0.95;
    margin: 0;
  }
  .terrapilot-subtitle {
    color: #55554e;
    max-width: 52rem;
    margin-top: 0.85rem;
    margin-bottom: 0;
  }
  .terrapilot-panel-title {
    font-size: 0.9rem;
    text-transform: uppercase;
    letter-spacing: 0.12em;
    color: #66665f;
    margin-bottom: 0.75rem;
  }
  .terrapilot-note {
    border-left: 2px solid #1b1b1b;
    padding-left: 0.75rem;
    color: #3c3c38;
    margin-bottom: 0.9rem;
  }
</style>
"""


def _uploaded_file_names(files: list[Any]) -> list[str]:
    return [uploaded_file.name for uploaded_file in files]


def _build_response(prompt: str, focus: str, files: list[str]) -> str:
    if not prompt.strip():
        return "Describe the site intent or upload context files to start shaping a concept."

    file_note = ", ".join(files) if files else "no reference files yet"
    return (
        f"TerraPilot is ready to develop a {focus.lower()} concept from: {prompt.strip()}.\n\n"
        f"Attached context: {file_note}.\n\n"
        "Use the viewport to sketch the footprint, massing, tree buffers, or circulation before wiring this UI to the full workflow."
    )


st.markdown(APP_CSS, unsafe_allow_html=True)

st.markdown(
    """
    <div class="terrapilot-card">
      <div class="terrapilot-eyebrow">site agent / design workspace</div>
      <h1 class="terrapilot-title">TerraPilot</h1>
      <p class="terrapilot-subtitle">
        A minimalist interface for uploading site context, sketching directly in the viewport,
        and shaping the next architectural move without extra widget noise.
      </p>
    </div>
    """,
    unsafe_allow_html=True,
)

st.write("")

brief_col, files_col = st.columns([1.4, 1], gap="large")

with brief_col:
    st.markdown('<div class="terrapilot-panel-title">design brief</div>', unsafe_allow_html=True)
    prompt = st.text_area(
        "Describe the site task",
        placeholder="Example: Place a compact housing block that preserves the existing tree line and opens toward the south edge.",
        height=140,
        label_visibility="collapsed",
    )
    focus = st.selectbox(
        "Focus mode",
        ["Site response", "Massing", "Circulation", "Landscape"],
    )

with files_col:
    st.markdown('<div class="terrapilot-panel-title">input files</div>', unsafe_allow_html=True)
    uploaded_files = st.file_uploader(
        "Upload references",
        accept_multiple_files=True,
        type=["json", "txt", "csv", "pdf", "png", "jpg", "jpeg"],
        label_visibility="collapsed",
    )
    st.caption("Drop layout exports, sketches, zoning notes, or precedent images.")

viewport_col, notes_col = st.columns([1.8, 1], gap="large")

with viewport_col:
    st.markdown('<div class="terrapilot-panel-title">viewport</div>', unsafe_allow_html=True)
    st.html(SKETCH_CANVAS, unsafe_allow_javascript=True)

with notes_col:
    st.markdown('<div class="terrapilot-panel-title">agent notes</div>', unsafe_allow_html=True)
    names = _uploaded_file_names(uploaded_files)
    st.markdown(
        f"""
        <div class="terrapilot-card">
          <div class="terrapilot-note">{_build_response(prompt, focus, names).replace(chr(10), "<br><br>")}</div>
          <strong>Loaded files</strong>
          <div>{", ".join(names) if names else "No files uploaded yet."}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    st.download_button(
        "Download brief snapshot",
        data=json.dumps(
            {
                "prompt": prompt,
                "focus": focus,
                "files": names,
            },
            indent=2,
        ),
        file_name="terrapilot_brief.json",
        mime="application/json",
        use_container_width=True,
    )

st.write("")
st.markdown(
    """
    <div class="terrapilot-card">
      <div class="terrapilot-panel-title">workflow hints</div>
      <div class="terrapilot-note">1. Upload layout/context files.</div>
      <div class="terrapilot-note">2. Sketch the site directly in the viewport.</div>
      <div class="terrapilot-note">3. Refine the brief until the concept direction feels right.</div>
    </div>
    """,
    unsafe_allow_html=True,
)
