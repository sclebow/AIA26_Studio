"""
make-pdf.py — export the reveal deck to a static PDF (one page per slide).

Renders the CURRENT deck headlessly and assembles a PDF (one screenshot per
slide). Clip pages can't play video in a PDF, so they render as a static
"DEMO n / 3" placeholder. Self-contained: serves deck/ locally, captures with
headless Chrome (falls back to Edge), assembles with PyMuPDF, cleans up.

Run (UTF-8):  PYTHONIOENCODING=utf-8 python team_02/docs/week09/deliverables/deck/make-pdf.py
Out: team_02/docs/week09/deliverables/Sensi-FinalReview-week09.pdf
"""
from __future__ import annotations
import functools, http.server, socketserver, subprocess, threading, time, re, os, shutil, tempfile
from pathlib import Path
import fitz  # PyMuPDF

DECK = Path(__file__).resolve().parent
OUT  = DECK.parent / "Sensi-FinalReview-week09.pdf"
TMP  = Path(tempfile.mkdtemp(prefix="sensi_pdf_"))  # frames + browser profile, outside the repo
PDF_HTML = DECK / "_index_pdf.html"                  # must sit in deck/ to resolve relative assets
PORT = 8046
N = 21  # total sections (18 numbered + 3 clip pages)

def find_browser():
    candidates = [
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
        os.path.expandvars(r"%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe"),
        r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
    ]
    for c in candidates:
        if os.path.isfile(c):
            return c
    raise SystemExit("No Chrome/Edge found for headless capture.")

BROWSER = find_browser()
# ---- pdf-render copy: clip <video>s -> a real demo screenshot (PDF can't play video,
# and the videos' preload=auto otherwise stalls headless load). Falls back to a
# 'DEMO n / 3' placeholder if a screenshot is missing. ----
html = open(DECK / "index.html", encoding="utf-8").read()
NUM = {"onboard": 1, "shape": 2, "report": 3}
SHOTS = DECK / "assets" / "demo-screenshots"
def _repl(m):
    blob = m.group(0)
    key = next((k for k in NUM if k in blob), None)
    n = NUM.get(key, 0)
    shot = SHOTS / f"demo-screenshot-{key}.png" if key else None
    if shot and shot.exists():
        return (f'<img src="assets/demo-screenshots/demo-screenshot-{key}.png" '
                f'style="position:absolute;inset:0;width:100%;height:100%;'
                f'object-fit:contain;background:#0D0D0D">')
    return (f'<div class="pdf-demo"><div class="pdf-demo-t">&#9654; DEMO {n} / 3</div>'
            f'<div class="pdf-demo-s">video plays in the live deck</div></div>')
html = re.sub(r'<video class="clip-vid".*?</video>', _repl, html, flags=re.S)
html = html.replace("</head>",
    "<style>.pdf-demo{position:absolute;inset:0 0 64px 0;display:flex;flex-direction:column;"
    "align-items:center;justify-content:center;gap:14px;background:#0D0D0D;}"
    ".pdf-demo-t{font:600 30px 'JetBrains Mono',monospace;color:#E8836A;letter-spacing:.12em;}"
    ".pdf-demo-s{font:400 15px Inter;color:#8a8780;}</style>\n</head>")
PDF_HTML.write_text(html, encoding="utf-8")

Handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(DECK))
httpd = socketserver.TCPServer(("127.0.0.1", PORT), Handler)
threading.Thread(target=httpd.serve_forever, daemon=True).start()
time.sleep(0.6)

PROFILE = TMP / "_browser_profile"
for i in range(N):
    png = TMP / f"p{i:02}.png"
    if png.exists():
        png.unlink()
    try:
        subprocess.run(
            [BROWSER, "--headless=new", "--no-sandbox", "--disable-gpu", "--hide-scrollbars",
             "--no-first-run", "--no-default-browser-check", f"--user-data-dir={PROFILE}",
             "--force-device-scale-factor=2", "--window-size=1280,720",
             "--virtual-time-budget=4000", f"--screenshot={png}",
             f"http://127.0.0.1:{PORT}/_index_pdf.html#/{i}"],
            timeout=45, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
    except subprocess.TimeoutExpired:
        pass
    print("captured", i, "ok" if (png.exists() and png.stat().st_size > 0) else "MISSING", flush=True)

httpd.shutdown()

doc = fitz.open()
missing = []
for i in range(N):
    png = TMP / f"p{i:02}.png"
    if not (png.exists() and png.stat().st_size > 0):
        missing.append(i); continue
    img = fitz.open(str(png)); pb = img.convert_to_pdf(); img.close()
    doc.insert_pdf(fitz.open("pdf", pb))
pages = doc.page_count
doc.save(str(OUT)); doc.close()

# cleanup
try: PDF_HTML.unlink()
except OSError: pass
shutil.rmtree(TMP, ignore_errors=True)

print(f"PDF saved: {OUT} ({pages} pages, {OUT.stat().st_size/1048576:.2f} MB, missing={missing})")
