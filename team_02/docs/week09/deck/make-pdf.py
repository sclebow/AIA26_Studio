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

for i in range(N):
    png = TMP / f"p{i:02}.png"
    subprocess.run(
        [EDGE, "--headless=new", "--disable-gpu", "--hide-scrollbars",
         "--window-size=1280,720", "--virtual-time-budget=5000",
         f"--screenshot={png}", f"http://127.0.0.1:{PORT}/index.html#/{i}"],
        timeout=45, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
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
doc.save(str(OUT))
doc.close()
for f in TMP.glob("*.png"):
    f.unlink()
TMP.rmdir()
print("PDF saved:", OUT, OUT.stat().st_size, "bytes")
