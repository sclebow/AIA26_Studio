from __future__ import annotations

import os
import re
import shutil
import subprocess
from pathlib import Path

from IPython.display import HTML, Image, display


def build_mermaid_html_document(source: str) -> str:
    import html

    escaped_source = html.escape(source)
    return f'''<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <style>
    html, body {{
      margin: 0;
            padding: 8px;
      background: #ffffff;
      font-family: Segoe UI, Arial, sans-serif;
            width: max-content;
            height: max-content;
            overflow: hidden;
    }}
        body {{
            display: inline-block;
        }}
    .mermaid {{
            display: inline-block;
            text-align: left;
        }}
        .mermaid svg {{
            max-width: none;
            height: auto;
    }}
  </style>
</head>
<body>
  <pre class="mermaid">
{escaped_source}
  </pre>
  <script type="module">
    import mermaid from 'https://cdn.jsdelivr.net/npm/mermaid@11/dist/mermaid.esm.min.mjs';
        mermaid.initialize({{
            startOnLoad: false,
            securityLevel: 'loose',
            flowchart: {{ useMaxWidth: false }},
        }});

        const diagramNodes = document.querySelectorAll('.mermaid');
        try {{
            await mermaid.run({{ nodes: diagramNodes }});
            const svg = document.querySelector('.mermaid svg');
            if (svg) {{
                const rect = svg.getBoundingClientRect();
                const bbox = typeof svg.getBBox === 'function' ? svg.getBBox() : null;
                const viewBox = svg.viewBox && svg.viewBox.baseVal ? svg.viewBox.baseVal : null;
                const measuredWidth = Math.ceil(Math.max(
                    rect.width || 0,
                    bbox ? bbox.width : 0,
                    viewBox ? viewBox.width : 0,
                ));
                const measuredHeight = Math.ceil(Math.max(
                    rect.height || 0,
                    bbox ? bbox.height : 0,
                    viewBox ? viewBox.height : 0,
                ));
                document.body.setAttribute('data-diagram-width', String(measuredWidth));
                document.body.setAttribute('data-diagram-height', String(measuredHeight));
            }}
        }} catch (error) {{
            const message = error instanceof Error ? error.message : String(error);
            document.body.setAttribute('data-render-error', message);
        }}
  </script>
</body>
</html>'''


def render_mermaid(source: str, py_dir: Path) -> Path:
    html_doc = build_mermaid_html_document(source)
    preview_path = py_dir / "workflow_mermaid_preview.html"
    preview_path.write_text(html_doc, encoding="utf-8")

    iframe_html = f'''
<div style="margin-bottom:12px; padding:10px 12px; border:1px solid #dee2e6; border-radius:10px; background:#fff9db; color:#343a40;">
    Embedded Mermaid preview. If it does not appear below, open the backup file:<br/>
  <strong>{preview_path.name}</strong>
</div>
<iframe
  srcdoc={html_doc!r}
  style="width:100%; height:1400px; border:1px solid #dee2e6; border-radius:12px; background:#ffffff;"
  loading="lazy"
  referrerpolicy="no-referrer">
</iframe>
'''
    display(HTML(iframe_html))
    print(f"Backup HTML updated: {preview_path}")
    return preview_path


def find_browser_executable() -> Path | None:
    browser_candidates = [
        Path(r"C:\Program Files\Google\Chrome\Application\chrome.exe"),
        Path(r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"),
        Path(r"C:\Program Files\Microsoft\Edge\Application\msedge.exe"),
        Path(r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe"),
    ]
    return next((path for path in browser_candidates if path.exists()), None)


def measure_diagram_size_with_browser(
    html_path: Path,
    timeout_seconds: int = 120,
    virtual_time_budget_ms: int = 12000,
) -> tuple[tuple[int, int] | None, str | None]:
    browser_executable = find_browser_executable()
    if browser_executable is None:
        return None, "Chrome or Edge was not found to measure the Mermaid diagram."

    command = [
        str(browser_executable),
        "--headless=new",
        "--disable-gpu",
        "--hide-scrollbars",
        "--force-device-scale-factor=1",
        f"--virtual-time-budget={virtual_time_budget_ms}",
        "--dump-dom",
        html_path.as_uri(),
    ]

    try:
        result = subprocess.run(
            command,
            cwd=str(html_path.parent),
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return None, "Measuring the diagram in the browser took too long."
    except FileNotFoundError as exc:
        return None, f"Could not launch the headless browser to measure the diagram: {exc}"

    if result.returncode != 0:
        diagnostic = (result.stderr or result.stdout or "").strip()
        return None, diagnostic or "The browser could not measure the Mermaid diagram."

    dom_text = result.stdout
    render_error_match = re.search(r'data-render-error="([^"]+)"', dom_text)
    if render_error_match:
        return None, render_error_match.group(1)

    width_match = re.search(r'data-diagram-width="(\d+)"', dom_text)
    height_match = re.search(r'data-diagram-height="(\d+)"', dom_text)
    if not width_match or not height_match:
        return None, "Could not read the rendered SVG dimensions from the DOM."

    width = int(width_match.group(1))
    height = int(height_match.group(1))
    if width <= 0 or height <= 0:
        return None, "The measured diagram dimensions are not valid."

    return (width, height), None


def export_png_with_browser(
    html_path: Path,
    output_path: Path,
    timeout_seconds: int = 120,
    virtual_time_budget_ms: int = 12000,
    window_size: str = "3200,950",
) -> tuple[Path | None, str | None]:
    browser_executable = find_browser_executable()
    if browser_executable is None:
        return None, "Chrome or Edge was not found to export a PNG with a headless screenshot."

    effective_window_size = window_size
    measured_size, measurement_error = measure_diagram_size_with_browser(
        html_path,
        timeout_seconds=timeout_seconds,
        virtual_time_budget_ms=virtual_time_budget_ms,
    )
    if measured_size is not None:
        measured_width, measured_height = measured_size
        padded_width = max(measured_width + 32, 400)
        padded_height = max(measured_height + 32, 300)
        effective_window_size = f"{padded_width},{padded_height}"
        print(f"Measured diagram size: {measured_width}x{measured_height} px")
    elif measurement_error:
        print(f"Could not measure the diagram before the screenshot: {measurement_error}")

    command = [
        str(browser_executable),
        "--headless=new",
        "--disable-gpu",
        "--hide-scrollbars",
        "--force-device-scale-factor=2",
        f"--window-size={effective_window_size}",
        f"--virtual-time-budget={virtual_time_budget_ms}",
        f"--screenshot={output_path}",
        html_path.as_uri(),
    ]

    print(f"Trying to export PNG with local browser: {browser_executable}")
    try:
        result = subprocess.run(
            command,
            cwd=str(html_path.parent),
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return None, "The browser screenshot took too long and was cancelled."
    except FileNotFoundError as exc:
        return None, f"Could not launch the headless browser: {exc}"

    if result.returncode == 0 and output_path.exists():
        return output_path, None

    diagnostic = (result.stderr or result.stdout or "").strip()
    return None, diagnostic or "The browser finished without generating the expected PNG."


def export_png_with_mermaid_cli(
    source: str,
    py_dir: Path,
    output_path: Path,
    timeout_seconds: int = 600,
    scale: int = 2,
    background_color: str = "white",
) -> tuple[Path | None, str | None]:
    source_path = py_dir / "workflow_mermaid_preview.mmd"
    source_path.write_text(source, encoding="utf-8")

    mmdc_executable = shutil.which("mmdc.cmd") or shutil.which("mmdc")
    npx_executable = shutil.which("npx.cmd") or shutil.which("npx")
    npm_cache_dir = py_dir / ".npm_cache_mermaid"
    npm_cache_dir.mkdir(parents=True, exist_ok=True)

    browser_executable = find_browser_executable()
    env = os.environ.copy()
    env["npm_config_cache"] = str(npm_cache_dir)
    if browser_executable is not None:
        env["PUPPETEER_SKIP_DOWNLOAD"] = "true"
        env["PUPPETEER_EXECUTABLE_PATH"] = str(browser_executable)

    if mmdc_executable:
        command = [
            mmdc_executable,
            "-i", str(source_path),
            "-o", str(output_path),
            "-b", background_color,
            "-s", str(scale),
        ]
    elif npx_executable:
        command = [
            npx_executable,
            "-y",
            "@mermaid-js/mermaid-cli",
            "-i", str(source_path),
            "-o", str(output_path),
            "-b", background_color,
            "-s", str(scale),
        ]
    else:
        return None, "Mermaid CLI was not found. Install mmdc or use npx to enable PNG export."

    print("Fallback: trying to export PNG with Mermaid CLI...")
    try:
        result = subprocess.run(
            command,
            cwd=str(py_dir),
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            check=False,
            env=env,
        )
    except subprocess.TimeoutExpired:
        return None, "PNG export with Mermaid CLI took too long."
    except FileNotFoundError as exc:
        return None, f"Could not launch Mermaid CLI: {exc}"

    if result.returncode == 0 and output_path.exists():
        return output_path, None

    diagnostic = (result.stderr or result.stdout or "").strip()
    return None, diagnostic or "Mermaid CLI finished without generating the expected PNG."


def export_mermaid_png(source: str, py_dir: Path, output_path: Path | None = None) -> Path | None:
    output_path = output_path or (py_dir / "workflow_mermaid_preview.png")
    html_path = py_dir / "workflow_mermaid_preview.html"
    if not html_path.exists():
        html_path.write_text(build_mermaid_html_document(source), encoding="utf-8")

    png_path, browser_error = export_png_with_browser(html_path, output_path)
    if png_path is not None:
        display(Image(filename=str(png_path)))
        print(f"PNG exported: {png_path}")
        return png_path

    print("Could not export the PNG with a headless browser.")
    if browser_error:
        print(browser_error[:2000])

    png_path, cli_error = export_png_with_mermaid_cli(source, py_dir, output_path)
    if png_path is not None:
        display(Image(filename=str(png_path)))
        print(f"PNG exported: {png_path}")
        return png_path

    print("Could not export the PNG automatically.")
    if cli_error:
        print(cli_error[:2000])
    return None
