"""
render_mermaid.py — render team_02/python/sensi_graph.mermaid to a PNG for the deck.

Uses mermaid.ink (the public renderer behind mermaid.live). Sends the diagram text to
that service. Output: team_02/docs/shots/03-graph.png.

Run:  python team_02/docs/render_mermaid.py
"""
from __future__ import annotations
import base64, json, zlib, urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
MMD = HERE.parent / "python" / "sensi_graph.mermaid"
OUT = HERE / "shots" / "03-graph.png"
OUT.parent.mkdir(exist_ok=True)

code = MMD.read_text(encoding="utf-8")
state = json.dumps({"code": code, "mermaid": {"theme": "default"}})
pako = base64.urlsafe_b64encode(zlib.compress(state.encode("utf-8"), 9)).decode("ascii")

urls = [
    "https://mermaid.ink/img/pako:" + pako + "?type=png&bgColor=ffffff",
    "https://mermaid.ink/img/pako:" + pako + "?type=png",
]
ok = False
for u in urls:
    try:
        req = urllib.request.Request(u, headers={"User-Agent": "Mozilla/5.0"})
        data = urllib.request.urlopen(req, timeout=40).read()
        if data[:8] == b"\x89PNG\r\n\x1a\n":
            OUT.write_bytes(data)
            print("OK  saved", OUT, "(", len(data), "bytes )")
            ok = True
            break
        print("not PNG from", u[:60], "->", data[:120])
    except Exception as e:
        print("ERR", u[:60], "->", e)
if not ok:
    print("FAILED to render mermaid PNG")
