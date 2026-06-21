"""
gen_before_after.py — generate the slide-11 before/after Kitchen renders for the deck.

Uses the app's own imaging pipeline (Gemini / Nano Banana). The "after" is the room's
canonical render; the "before" is that same image edited by a "what changed" clause
(colder / harder / stuffier), anchored on the after via reference_b64 — exactly how the
Report's before/after holds the scene.

Run (from team_02/python/, UTF-8):  python gen_before_after.py
Out: team_02/docs/week09/deck/assets/shots/report-after.png + report-before.png
"""
from __future__ import annotations
import base64, os, sys
from pathlib import Path
from dotenv import load_dotenv

HERE = Path(__file__).resolve().parent          # team_02/python
REPO = Path(__file__).resolve().parents[2]      # AIA26_Studio
sys.path.insert(0, str(HERE))
load_dotenv(REPO / ".env")
os.environ["IMAGE_PROVIDER"] = "google"

from imaging import build_room_prompt          # noqa: E402
from imaging.client import generate_image      # noqa: E402

out = REPO / "team_02" / "docs" / "week09" / "deck" / "assets" / "shots"
out.mkdir(parents=True, exist_ok=True)

room = {"name": "Kitchen", "attributes": {"roomType": "kitchen", "floorMaterial": "warm oak"}}
persona = {"role": "architect"}
# AFTER = the improved room (warm, soft, fresh) — the canonical render.
after_scores = {"thermal": 0.78, "visual": 0.74, "acoustic": 0.74,
                "spatial": 0.80, "olfactory": 0.80, "tactile": 0.82}

after_prompt = build_room_prompt(room, after_scores, persona) + (
    " The floor is warm honey-toned oak boards. Several large leafy potted plants and trailing "
    "hanging greenery fill the room. A large window along one wall floods the space with bright "
    "natural daylight and a view of greenery outside."
)
print("AFTER prompt:\n", after_prompt, "\n", flush=True)
print("generating AFTER ...", flush=True)
after_b64 = generate_image(after_prompt)
(out / "report-after.png").write_bytes(base64.b64decode(after_b64))
print("  saved report-after.png", flush=True)

before_prompt = (
    "First-person, eye-level interior photograph of the SAME kitchen — identical layout, "
    "furniture, oak floor, window and viewpoint — but BEFORE the comfort edits: noticeably "
    "colder, with a flat, bluish daylight cast, far fewer plants and bare surfaces, and a "
    "harder, more clinical and less inviting atmosphere. 35mm lens, photorealistic, high "
    "detail, no text, no people. Shot as restrained, material-honest architectural photography."
)
print("generating BEFORE (anchored on after) ...", flush=True)
before_b64 = generate_image(before_prompt, reference_b64=after_b64)
(out / "report-before.png").write_bytes(base64.b64decode(before_b64))
print("  saved report-before.png", flush=True)
print("DONE ->", out, flush=True)
