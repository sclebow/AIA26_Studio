"""
make-pdf.py — export the reveal deck to a static PDF (one page per slide).

reveal's ?print-pdf doesn't render reliably under headless Edge, so we screenshot
each slide at 1280x720 (headless Edge, navigating by hash) and assemble them into a
PDF with PyMuPDF. Self-contained: serves deck/ on a local port, captures, cleans up.

Run (from anywhere, UTF-8):  python team_02/docs/week09/deck/make-pdf.py
Out: team_02/docs/week09/Sensi-FinalReview-week09.pdf
"""
from __future__ import annotations
import functools, http.server, socketserver, subprocess, threading, time
from pathlib import Path
import fitz  # PyMuPDF

DECK = Path(__file__).resolve().parent
OUT = DECK.parent / "Sensi-FinalReview-week09.pdf"
TMP = DECK / "_pdf_frames"
TMP.mkdir(exist_ok=True)
EDGE = r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"
PORT = 8033
N = 21  # total sections (18 numbered + 3 clip pages)

Handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(DECK))
httpd = socketserver.TCPServer(("127.0.0.1", PORT), Handler)
threading.Thread(target=httpd.serve_forever, daemon=True).start()
time.sleep(0.6)

PROFILE = TMP / "_edge_profile"  # dedicated profile so Edge never reuses the user's running instance
for i in range(N):
    png = TMP / f"p{i:02}.png"
    if png.exists():
        png.unlink()
    subprocess.run(
        [EDGE, "--headless=new", "--disable-gpu", "--hide-scrollbars",
         "--no-first-run", "--no-default-browser-check", f"--user-data-dir={PROFILE}",
         "--window-size=1280,720", "--virtual-time-budget=6000",
         f"--screenshot={png}", f"http://127.0.0.1:{PORT}/index.html#/{i}"],
        timeout=60, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    for _ in range(40):  # wait for the async screenshot to actually land
        if png.exists() and png.stat().st_size > 0:
            break
        time.sleep(0.3)
    print("captured", i, "ok" if png.exists() else "MISSING", flush=True)

httpd.shutdown()

doc = fitz.open()
for i in range(N):
    png = TMP / f"p{i:02}.png"
    if not png.exists():
        continue
    img = fitz.open(str(png))
    pdfbytes = img.convert_to_pdf()
    img.close()
    doc.insert_pdf(fitz.open("pdf", pdfbytes))
doc_pages = doc.page_count
doc.save(str(OUT))
doc.close()
import shutil
for f in TMP.glob("*.png"):
    f.unlink()
shutil.rmtree(TMP, ignore_errors=True)
print(f"PDF saved: {OUT} ({doc_pages} pages, {OUT.stat().st_size} bytes)")
