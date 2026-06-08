"""
build_deck_week08.py — Sensi WEEK 8 deck (PDF, reportlab). Forked from build_deck.py.

11-slide update deck. Order: cover · what shipped · the graph · edit+checkpoints ·
HERO vision · HERO before/after · Act-3 under the hood · benchmark table · benchmark
images · fine-tunings · next. Brand fonts (Inter / JetBrains Mono / Caveat) are
bundled in docs/fonts/ and embedded — all selectable in Canva for editing.

Screenshots embed from team_02/docs/week08/shots/ (placeholders if absent):
    vision-rooms-cards.png · before-after-screen.png · commit-changes.png ·
    bench-{google,openai}-{living,kitchen,bedroom}.png
Run:  python team_02/docs/build_deck_week08.py
Out:  team_02/docs/week08/Sensi-Presentation-week08.pdf
"""
from __future__ import annotations
import math
from pathlib import Path

from reportlab.pdfgen import canvas
from reportlab.lib.colors import HexColor
from reportlab.lib.utils import ImageReader
from reportlab.lib.enums import TA_LEFT, TA_RIGHT, TA_CENTER
from reportlab.lib.styles import ParagraphStyle
from reportlab.platypus import Paragraph
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

HERE = Path(__file__).resolve().parent
SHOTS = HERE / "week08" / "shots"; SHOTS.mkdir(parents=True, exist_ok=True)
FONTS = HERE / "fonts"
OUT = HERE / "week08" / "Sensi-Presentation-week08.pdf"
TOTAL = 11

W, H = 960.0, 540.0  # 16:9 at 72dpi

# ── Palette (web/src/lib/senses.js) ────────────────────────────────────────────
HUE = {"thermal": "E8836A", "visual": "D4B96A", "acoustic": "9B8FD4",
       "spatial": "6AB8C8", "olfactory": "8BB88A", "tactile": "C4A882"}
GLYPH = {"thermal": "△", "visual": "○", "acoustic": "∿", "spatial": "□",
         "olfactory": "≈", "tactile": "∶"}
PASS, FAIL = "3FB97A", "E0524A"
BG, PANEL, BORDER = "0B0D10", "14171C", "2A2E35"
ZEBRA = "0E1115"
FG, MUTED, RED = "E6E8EC", "9AA0A8", "FF5247"

# ── Fonts — brand TTFs (docs/fonts/), embedded + Canva-available (Inter · JetBrains
# Mono · Caveat, open-source via Fontsource). Falls back to Windows system fonts.
# Sense glyphs (△ ∿ □ …) use Segoe UI Symbol — decorative accents, not body text. ──
_F = r"C:\Windows\Fonts"
def _reg(name, file, fallback):
    try:
        pdfmetrics.registerFont(TTFont(name, _F + "\\" + file)); return name
    except Exception:
        return fallback
def _regf(name, brand_file, sys_file, fallback):
    try:
        pdfmetrics.registerFont(TTFont(name, str(FONTS / brand_file))); return name
    except Exception:
        return _reg(name, sys_file, fallback)
SANS  = _regf("Sans",  "Inter-Regular.ttf",         "segoeui.ttf", "Helvetica")
SANSB = _regf("SansB", "Inter-SemiBold.ttf",        "seguisb.ttf", "Helvetica-Bold")
MONO  = _regf("Mono",  "JetBrainsMono-Regular.ttf", "consola.ttf", "Courier")
HAND  = _regf("Hand",  "Caveat-SemiBold.ttf",       "segoepr.ttf", "Helvetica-Oblique")
SYM   = _reg("Sym",    "seguisym.ttf", SANS)

def col(h): return HexColor("#" + h)

_SYM_CHARS = "△∿↔⚛❝◇✦●∶≈□○→"
def symify(s):
    for ch in _SYM_CHARS:
        if ch in s:
            s = s.replace(ch, "<font name='%s'>%s</font>" % (SYM, ch))
    return s


def bg(c):
    c.setFillColor(col(BG)); c.rect(0, 0, W, H, fill=1, stroke=0)


def bar(c, x, yt, hue, w=34, h=5):
    c.setFillColor(col(hue)); c.rect(x, H - yt - h, w, h, fill=1, stroke=0)


def para(c, x, yt, w, html, *, font=SANS, size=16, color=FG, leading=None, align=TA_LEFT):
    st = ParagraphStyle("s", fontName=font, fontSize=size, textColor=col(color),
                        leading=leading or size * 1.42, alignment=align)
    p = Paragraph(symify(html), st); pw, ph = p.wrap(w, H)
    p.drawOn(c, x, H - yt - ph); return ph


def rrect(c, x, yt, w, h, *, fill=PANEL, stroke=BORDER, r=10, sw=1):
    if fill: c.setFillColor(col(fill))
    if stroke: c.setStrokeColor(col(stroke)); c.setLineWidth(sw)
    c.roundRect(x, H - yt - h, w, h, r, stroke=1 if stroke else 0, fill=1 if fill else 0)


def img(c, x, yt, w, h, name, hue, *, label=None):
    f = SHOTS / name
    if f.exists():
        rrect(c, x, yt, w, h, fill=PANEL, stroke=hue, sw=1.5)
        try:
            c.drawImage(ImageReader(str(f)), x + 5, H - yt - h + 5, w - 10, h - 10,
                        preserveAspectRatio=True, anchor="c", mask="auto")
        except Exception:
            pass
    else:
        rrect(c, x, yt, w, h, fill=PANEL, stroke=hue, sw=1.25)
        c.setFillColor(col(MUTED)); c.setFont(MONO, 10)
        c.drawCentredString(x + w / 2, H - yt - h / 2 - 4, "[ drop  " + name + " ]")
    if label:
        c.setFillColor(col(MUTED)); c.setFont(MONO, 9)
        c.drawString(x + 2, H - yt + 6, label)


def hand(c, x, yt, w, text, *, size=15, align=TA_LEFT):
    st = ParagraphStyle("h", fontName=HAND, fontSize=size, textColor=col(RED),
                        leading=size * 1.18, alignment=align)
    p = Paragraph(symify(text), st); pw, ph = p.wrap(w, H)
    p.drawOn(c, x, H - yt - ph)


def arrow(c, x1, yt1, x2, yt2, *, width=1.6, head=8, color=RED):
    Y1, Y2 = H - yt1, H - yt2
    c.setStrokeColor(col(color)); c.setLineWidth(width); c.setLineCap(1)
    c.line(x1, Y1, x2, Y2)
    a = math.atan2(Y2 - Y1, x2 - x1)
    p = c.beginPath(); p.moveTo(x2, Y2)
    p.lineTo(x2 - head * math.cos(a - 0.4), Y2 - head * math.sin(a - 0.4))
    p.lineTo(x2 - head * math.cos(a + 0.4), Y2 - head * math.sin(a + 0.4)); p.close()
    c.setFillColor(col(color)); c.drawPath(p, fill=1, stroke=0)


def kicker(c, text, hue):
    bar(c, 40, 42, hue)
    c.setFillColor(col(hue)); c.setFont(MONO, 11)
    c.drawString(84, H - 50, text)


def counter(c, n):
    c.setFillColor(col(MUTED)); c.setFont(MONO, 10)
    c.drawRightString(W - 40, H - 50, "%02d / %02d" % (n, TOTAL))


def card(c, x, yt, w, h, title, body, hue, *, glyph=None):
    rrect(c, x, yt, w, h, stroke=hue, sw=1.25)
    if glyph:
        c.setFillColor(col(hue)); c.setFont(SYM, 16)
        c.drawString(x + 16, H - yt - 30, glyph)
        para(c, x + 42, yt + 14, w - 58, "<font name='%s'>%s</font>" % (MONO, title), font=MONO, size=10.5, color=hue)
    else:
        para(c, x + 16, yt + 14, w - 32, "<font name='%s'>%s</font>" % (MONO, title), font=MONO, size=10.5, color=hue)
    para(c, x + 16, yt + 40, w - 32, body, font=SANS, size=11.5, color=FG, leading=17)


def eq_card(c, x, yt, w, h, eq, gloss, tag, hue, *, eq_size=15, eq_lead=21):
    rrect(c, x, yt, w, h)
    para(c, x + 22, yt + 18, w - 44, eq, font=MONO, size=eq_size, color=FG, leading=eq_lead)
    if gloss:
        para(c, x + 22, yt + h - 30, w - 210, gloss, font=SANS, size=11.5, color=MUTED)
    if tag:
        para(c, x + w - 250, yt + h - 28, 230, tag, font=MONO, size=10, color=hue, align=TA_RIGHT)


def table(c, x, yt, w, header, body, colw, *, rowh=24, size=11):
    cols = [w * f for f in colw]
    xs = [x + sum(cols[:i]) for i in range(len(cols))]
    top = yt
    rrect(c, x, top, w, rowh, fill=PANEL, stroke=None, r=4)
    c.setFont(MONO, 9.5); c.setFillColor(col(MUTED))
    for i, h in enumerate(header):
        if i == 0: c.drawString(xs[i] + 14, H - top - rowh + 8, h)
        else: c.drawRightString(xs[i] + cols[i] - 14, H - top - rowh + 8, h)
    top += rowh
    for ri, row in enumerate(body):
        ry = H - top - rowh
        if ri % 2 == 1:
            c.setFillColor(col(ZEBRA)); c.rect(x, ry, w, rowh, fill=1, stroke=0)
        c.setFont(MONO, size)
        for i, (txt, clr) in enumerate(row):
            c.setFillColor(col(clr))
            if i == 0: c.drawString(xs[i] + 14, ry + 8, txt)
            else: c.drawRightString(xs[i] + cols[i] - 14, ry + 8, txt)
        top += rowh
    return top


def flowbox(c, x, yt, w, h, title, sub, hue):
    rrect(c, x, yt, w, h, stroke=hue, sw=1.4)
    para(c, x, yt + 15, w, "<b>%s</b>" % title, font=SANSB, size=13.5, color=FG, align=TA_CENTER)
    para(c, x + 8, yt + 39, w - 16, sub, font=SANS, size=10.5, color=MUTED, align=TA_CENTER, leading=13)


def page(c):
    c.showPage()


def hero(c, hue, kick, title, name, callouts, n):
    bg(c); kicker(c, kick, hue); counter(c, n)
    para(c, 40, 70, 760, "<b>" + title + "</b>", font=SANSB, size=23, color=FG)
    ix, iy, iw, ih = 215, 150, 530, 300
    img(c, ix, iy, iw, ih, name, hue)
    spots = {
        "tl": (28, 110, 175, TA_LEFT, ix + 18, iy + 22),
        "tr": (760, 110, 178, TA_RIGHT, ix + iw - 18, iy + 22),
        "bl": (28, 452, 175, TA_LEFT, ix + 18, iy + ih - 22),
        "br": (760, 452, 178, TA_RIGHT, ix + iw - 18, iy + ih - 22),
    }
    for corner, txt in callouts.items():
        nx, ny, nw, al, ax, ay = spots[corner]
        hand(c, nx, ny, nw, txt, size=14, align=al)
        sx = nx + (nw if corner in ("tl", "bl") else 0)
        arrow(c, sx, ny + 34, ax, ay)
    page(c)


c = canvas.Canvas(str(OUT), pagesize=(W, H))

# ── 1 · COVER ───────────────────────────────────────────────────────────────
bg(c)
c.setFillColor(col(FG)); c.setFont(MONO, 60); c.drawString(70, H - 210, "SENSI")
c.setFillColor(col(HUE["olfactory"])); c.setFont(MONO, 20); c.drawString(74, H - 248, "WEEK 8")
para(c, 72, 290, 820, "a sensorial-comfort copilot for architectural layouts", font=SANS, size=18, color=MUTED)
para(c, 72, 324, 820, "<i>what shipped since week 7 — the space becomes an image</i>", font=SANS, size=15, color=HUE["acoustic"])
glyphrow = "&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;".join(
    "<font color='#%s'>%s</font> %s" % (HUE[k], GLYPH[k], k) for k in HUE)
para(c, 72, 432, 880, glyphrow, font=SANS, size=14, color=MUTED)
page(c)

# ── 2 · WHAT SHIPPED ──────────────────────────────────────────────────────────
bg(c); kicker(c, "WEEK 8 · WHAT SHIPPED", HUE["visual"]); counter(c, 2)
para(c, 40, 76, 880, "<b>Six things landed</b>", font=SANSB, size=27, color=FG)
cw, ch, gx, gy = 280, 104, 20, 20
x0, y0 = 40, 132
cells = [
    ("THE VISION / REPORT", "scores <b>become a prompt, then an image</b>.", HUE["thermal"], "○"),
    ("BEFORE / AFTER", "scrub the glow-up — image, scores &amp; prompt move together.", HUE["acoustic"], "∿"),
    ("BENCHMARKING", "per-node tiers, measured; Google vs OpenAI images.", HUE["olfactory"], "≈"),
    ("CLI ORCHESTRATOR", "headless mode — Sensi runs as a component.", HUE["visual"], "□"),
    ("CHECKPOINTS + MULTI-EDIT", "git-like commits; many edits, one re-score.", HUE["spatial"], "◇"),
    ("FINE-TUNINGS", "orbs · linkified chat · prompts · declutter.", HUE["tactile"], "∶"),
]
for i, (t, b, hue, g) in enumerate(cells):
    cx = x0 + (i % 3) * (cw + gx)
    cy = y0 + (i // 3) * (ch + gy)
    card(c, cx, cy, cw, ch, t, b, hue, glyph=g)
para(c, 40, 372, 880,
     "<font name='%s' color='#%s'>the thesis holds &nbsp;·&nbsp;</font> the number isn’t the lesson — the edges are. "
     "week 8 makes them <i>visible</i>." % (MONO, MUTED), font=SANS, size=13, color=FG)
page(c)

# ── 3 · THE GRAPH (architecture) ──────────────────────────────────────────────
bg(c); kicker(c, "ARCHITECTURE · THE GRAPH", HUE["spatial"]); counter(c, 3)
para(c, 40, 72, 880, "<b>One classifier, many paths</b>", font=SANSB, size=24, color=FG)
para(c, 40, 116, 880,
     "A single <font name='%s' color='#%s'>action_classifier</font> picks one of 13 actions in one LLM call — "
     "then the right chain runs." % (MONO, HUE["visual"]), font=SANS, size=13.5, color=FG)
bw2, bgap, byt, bh2 = 160, 20, 158, 66
stages = [("action_classifier", "route the turn", HUE["visual"]),
          ("load_layout", "bring in the plan", HUE["tactile"]),
          ("analyze → score", "comfort + meaning", HUE["spatial"]),
          ("detect → suggest", "conflicts + fixes", HUE["olfactory"]),
          ("respond → eval", "answer, checked", HUE["thermal"])]
for i, (t, s, hue) in enumerate(stages):
    x = 40 + i * (bw2 + bgap)
    flowbox(c, x, byt, bw2, bh2, t, s, hue)
    if i < len(stages) - 1:
        arrow(c, x + bw2 + 2, byt + bh2 / 2, x + bw2 + bgap - 2, byt + bh2 / 2, width=2)
para(c, 40, 252, 880,
     "<font name='%s' color='#%s'>edit &nbsp;</font> plan → apply → re-score → compare &nbsp;&nbsp;&nbsp;"
     "<font name='%s' color='#%s'>insight &nbsp;</font> topology · biophilic · persona &nbsp;&nbsp;&nbsp;"
     "<font name='%s' color='#%s'>else &nbsp;</font> follow-up · chitchat"
     % (MONO, HUE["acoustic"], MONO, HUE["olfactory"], MONO, MUTED), font=SANS, size=12.5, color=FG)
for i, (t, b, hue) in enumerate([
        ("13 actions, 1 call", "routing that was three LLM calls is now one.", HUE["visual"]),
        ("cache-aware", "no re-scoring when the layout hasn’t changed.", HUE["spatial"]),
        ("edit → re-score", "the agentic ripple — every change is measured.", HUE["thermal"])]):
    card(c, 40 + i * 300, 300, 280, 92, t, b, hue)
para(c, 40, 436, 880,
     "<font name='%s' color='#%s'>stack &nbsp;</font> FastAPI · LangGraph · React + Vite — "
     "no Rhino / Grasshopper, runs behind one link." % (MONO, MUTED), font=SANS, size=12, color=HUE["olfactory"])
page(c)

# ── 4 · EDIT ENGINE + CHECKPOINTS ─────────────────────────────────────────────
bg(c); kicker(c, "ARCHITECTURE · EDIT + CHECKPOINTS", HUE["acoustic"]); counter(c, 4)
para(c, 40, 70, 880, "<b>Editing is live — commit when you’re happy</b>", font=SANSB, size=23, color=FG)
para(c, 40, 114, 470,
     "One instruction can carry several changes. <font name='%s' color='#%s'>edit_planner</font> splits it into "
     "ops; <font name='%s' color='#%s'>apply_edits</font> mutates them at one chokepoint — then we re-score "
     "<b>once</b>." % (MONO, HUE["visual"], MONO, HUE["visual"]), font=SANS, size=13, color=FG, leading=20)
mflow = [("one prompt", "“2 plants + glazing”", HUE["tactile"]),
         ("N ops", "edit_planner", HUE["visual"]),
         ("mutate", "apply_edits", HUE["spatial"]),
         ("re-score", "one pass → delta", HUE["thermal"])]
for i, (t, s, hue) in enumerate(mflow):
    fx = 40 + i * 115
    flowbox(c, fx, 184, 104, 70, t, s, hue)
    if i < len(mflow) - 1:
        arrow(c, fx + 104 + 1, 219, fx + 115 - 1, 219, width=1.6, head=6)
eq_card(c, 40, 278, 470, 92,
        "draft → commit → restore",
        "checkpoints are git-like — roll back anytime", "api/checkpoints.py", HUE["acoustic"],
        eq_size=16, eq_lead=20)
para(c, 40, 388, 470,
     "<font name='%s' color='#%s'>why it matters &nbsp;</font> explore freely, never lose a good state — the "
     "Report’s before/after reads the committed checkpoint." % (MONO, MUTED),
     font=SANS, size=12, color=FG, leading=18)
img(c, 540, 116, 380, 300, "commit-changes.png", HUE["acoustic"], label="checkpoints in the UI")
page(c)

# ── 5 · HERO — THE VISION ─────────────────────────────────────────────────────
hero(c, HUE["thermal"], "HERO · THE VISION (ACT 3)", "Scores become a prompt, become an image",
     "vision-rooms-cards.png",
     {"tl": "the rose —<br/>6 senses,<br/>one glance", "tr": "the prompt,<br/>from the<br/>scores",
      "bl": "only extreme<br/>senses speak", "br": "the render —<br/>how it feels"}, 5)

# ── 6 · HERO — BEFORE / AFTER ─────────────────────────────────────────────────
hero(c, HUE["acoustic"], "HERO · WHAT YOUR CHANGES DID", "Before → after, the whole story scrubs",
     "before-after-screen.png",
     {"tl": "one spine —<br/>drag anywhere", "tr": "rose + numbers<br/>morph as<br/>you drag",
      "bl": "before /<br/>after prompt", "br": "after = the<br/>card render"}, 6)

# ── 7 · ACT 3 UNDER THE HOOD ──────────────────────────────────────────────────
bg(c); kicker(c, "ACT 3 · UNDER THE HOOD", HUE["thermal"]); counter(c, 7)
para(c, 40, 66, 880, "<b>How a room becomes an image</b>", font=SANSB, size=24, color=FG)
flowbox(c, 40, 112, 250, 66, "the scores", "6 senses, 0–1, vs persona", HUE["spatial"])
arrow(c, 296, 145, 330, 145, width=2)
flowbox(c, 336, 112, 250, 66, "the prompt", "score → scene mapping", HUE["visual"])
arrow(c, 592, 145, 626, 145, width=2)
flowbox(c, 632, 112, 250, 66, "the render", "“how it feels” photo", HUE["thermal"])
para(c, 40, 206, 880,
     "<font name='%s' color='#%s'>the rule &nbsp;</font> only a room’s <b>extreme</b> senses speak — "
     "<font name='%s'>&lt; 0.45</font> or <font name='%s'>&gt; 0.70</font>. Mid-range stays silent." % (MONO, MUTED, MONO, MONO),
     font=SANS, size=14, color=FG)
eq_card(c, 40, 244, 530, 160,
        "First-person photo of a {room}.<br/>The floor is {material}.<br/>"
        "The space feels {voiced senses}.<br/>Furnishings include {items}.<br/>"
        "35mm, photoreal · {persona register}.",
        "build_room_prompt()", "imaging/prompt.py", HUE["visual"], eq_size=14, eq_lead=22)
para(c, 606, 240, 320, "<font name='%s'>SCORE → WORDS</font>" % MONO, font=MONO, size=10, color=MUTED)
ex = [("∿", "acoustic low", "“hard, reflective surfaces”", HUE["acoustic"]),
      ("≈", "olfactory high", "“fresh, a few plants”", HUE["olfactory"]),
      ("∶", "tactile low", "“cold, hard materials”", HUE["tactile"])]
yy = 264
for g, lab, txt, hue in ex:
    para(c, 608, yy, 320, "<font name='%s' color='#%s'>%s %s</font>" % (MONO, hue, g, lab), font=MONO, size=11, color=hue)
    para(c, 608, yy + 17, 320, txt, font=SANS, size=11, color=FG)
    yy += 47
para(c, 40, 430, 880,
     "<font name='%s' color='#%s'>before / after &nbsp;</font> the <b>after</b> is the room’s canonical render "
     "(the card’s image). The <b>before</b> is that image, edited by a “what changed” clause — so the scene holds, "
     "only the changes move." % (MONO, MUTED), font=SANS, size=12.5, color=FG, leading=18)
page(c)

# ── 8 · BENCHMARK — NODE TIERS (TABLE) ────────────────────────────────────────
bg(c); kicker(c, "BENCHMARKING · NODE TIERS", HUE["olfactory"]); counter(c, 8)
para(c, 40, 70, 880, "<b>Small models for simple work</b>", font=SANSB, size=23, color=FG)
para(c, 40, 114, 880,
     "13 LLM nodes, two tiers. Measured one full session with <font name='%s'>bench_nodes.py</font>:" % MONO,
     font=SANS, size=13, color=FG)
SM, FA = HUE["acoustic"], PASS
body = [
    [("suggestion_critic", FG), ("SMART", SM), ("16.1", FG), ("924 / 838", MUTED), ("$0.0024", FG)],
    [("score_interpreter", FG), ("SMART", SM), ("14.3", FG), ("1696 / 1024", MUTED), ("$0.0031", FG)],
    [("conflict_reasoner", FG), ("SMART", SM), ("9.3", FG), ("1062 / 320", MUTED), ("$0.0011", FG)],
    [("respond", FG), ("SMART", SM), ("7.4", FG), ("4820 / 243", MUTED), ("$0.0021", FG)],
    [("detail_respond", FG), ("SMART", SM), ("2.1", FG), ("8017 / 42", MUTED), ("$0.0025", FG)],
    [("action_classifier", FG), ("FAST", FA), ("0.74", FG), ("4105 / 175", MUTED), ("$0.0005", FG)],
    [("what_next", FG), ("FAST", FA), ("0.79", FG), ("2564 / 182", MUTED), ("$0.0003", FG)],
    [("evaluator", FG), ("FAST", FA), ("0.47", FG), ("1272 / 3", MUTED), ("$0.0001", FG)],
    [("greet", FG), ("FAST", FA), ("0.54", FG), ("124 / 12", MUTED), ("$0.0000", FG)],
]
table(c, 40, 152, 560, ["node", "tier", "avg s", "tok in/out", "$/call"], body,
      [0.34, 0.16, 0.14, 0.22, 0.14], rowh=24, size=11)
rrect(c, 624, 152, 296, 142, stroke=HUE["olfactory"], sw=1.5)
para(c, 644, 170, 268, "<font name='%s'>PER-CALL AVERAGE</font>" % MONO, font=MONO, size=10, color=MUTED)
para(c, 644, 196, 268, "<font name='%s' color='#%s'>FAST</font>&nbsp;&nbsp;0.68 s · ~$0.0002" % (MONO, PASS),
     font=MONO, size=13, color=FG)
para(c, 644, 222, 268, "<font name='%s' color='#%s'>SMART</font>&nbsp;8.48 s · ~$0.002" % (MONO, SM),
     font=MONO, size=13, color=FG)
para(c, 644, 252, 268, "SMART ≈ 12× slower, 11× costlier.", font=SANS, size=11.5, color=MUTED)
rrect(c, 624, 310, 296, 86, stroke=BORDER, sw=1)
para(c, 644, 328, 268, "<font name='%s'>NO-LLM NODES</font>" % MONO, font=MONO, size=10, color=MUTED)
para(c, 644, 350, 268, "analyze · detect · suggest · apply_edits — pure Python, ~0 s.",
     font=SANS, size=11.5, color=FG, leading=16)
para(c, 40, 446, 880,
     "<font name='%s' color='#%s'>repro &nbsp;</font> <font name='%s'>BENCH_NODES=1 python bench_nodes.py</font>"
     % (MONO, MUTED, MONO), font=SANS, size=11, color=FG)
page(c)

# ── 9 · BENCHMARK — IMAGE PROVIDER A/B ────────────────────────────────────────
bg(c); kicker(c, "BENCHMARKING · IMAGE PROVIDER", HUE["olfactory"]); counter(c, 9)
para(c, 40, 70, 880, "<b>Same prompt, two engines</b>", font=SANSB, size=23, color=FG)
cases = [("living", "living · poor"), ("kitchen", "kitchen · mixed"), ("bedroom", "bedroom · cosy")]
tw, th, gx2, gstart = 172, 116, 14, 118
c.setFillColor(col(PASS)); c.setFont(MONO, 11); c.drawString(44, H - 178, "GOOGLE")
c.setFillColor(col(FAIL)); c.setFont(MONO, 11); c.drawString(44, H - 322, "OPENAI")
for ci, (key, lab) in enumerate(cases):
    cx = gstart + ci * (tw + gx2)
    para(c, cx, 100, tw, "<font name='%s'>%s</font>" % (MONO, lab), font=MONO, size=10, color=MUTED, align=TA_CENTER)
    img(c, cx, 120, tw, th, f"bench-google-{key}.png", PASS)
    img(c, cx, 264, tw, th, f"bench-openai-{key}.png", FAIL)
rx = gstart + 3 * (tw + gx2) + 10
cwd = W - rx - 40
rrect(c, rx, 120, cwd, 260, stroke=HUE["visual"], sw=1.4)
para(c, rx + 18, 138, cwd - 30, "<font name='%s'>THE NUMBERS · 06-07</font>" % MONO, font=MONO, size=10, color=MUTED)
para(c, rx + 18, 166, cwd - 30, "<font color='#%s'>Google</font>" % PASS, font=MONO, size=13, color=PASS)
para(c, rx + 18, 186, cwd - 30, "6.7 s · $0.039", font=MONO, size=12, color=FG)
para(c, rx + 18, 218, cwd - 30, "<font color='#%s'>OpenAI</font>" % FAIL, font=MONO, size=13, color=FAIL)
para(c, rx + 18, 238, cwd - 30, "20.5 s · $0.042", font=MONO, size=12, color=FG)
para(c, rx + 18, 274, cwd - 30, "~3× faster, a bit cheaper, steadier across edits.", font=SANS, size=11.5, color=FG, leading=17)
para(c, rx + 18, 336, cwd - 30, "<font color='#%s'>→ stay on Google</font>" % PASS, font=SANS, size=11.5, color=PASS)
para(c, 40, 424, 880,
     "Both read the comfort scores — Google leans clean daylight, OpenAI darker and cinematic.",
     font=SANS, size=11.5, color=MUTED)
page(c)

# ── 10 · FINE-TUNINGS (visual grid) ───────────────────────────────────────────
bg(c); kicker(c, "WEEK 8 · FINE-TUNINGS", HUE["tactile"]); counter(c, 10)
para(c, 40, 76, 880, "<b>Many small wins</b>", font=SANSB, size=27, color=FG)
fcw, fch, fgx, fgy = 430, 120, 20, 22
fx0, fy0 = 40, 136
fcells = [
    ("CLEANER CANVAS", "the material lens is floating orbs + a ripple on every change — not heavy fills.", HUE["visual"], "○"),
    ("CHAT TALKS TO THE PLAN", "rooms, senses &amp; scores linkify and brush the plan both ways.", HUE["acoustic"], "∿"),
    ("SYSTEM PROMPTS REVIEWED", "one shared register; exact room &amp; sense names so the linkifier fires.", HUE["thermal"], "≈"),
    ("DECLUTTERED", "removed redundancies across the report &amp; explore views.", HUE["tactile"], "∶"),
]
for i, (t, b, hue, g) in enumerate(fcells):
    cx = fx0 + (i % 2) * (fcw + fgx)
    cy = fy0 + (i // 2) * (fch + fgy)
    card(c, cx, cy, fcw, fch, t, b, hue, glyph=g)
page(c)

# ── 11 · WHAT'S NEXT ──────────────────────────────────────────────────────────
bg(c); kicker(c, "WHAT'S NEXT", HUE["olfactory"]); counter(c, 11)
para(c, 40, 82, 880, "<b>Where week 9 goes</b>", font=SANSB, size=28, color=FG)
nxt = [("◇", "tune the loop", "make the evaluator earn its keep; stream the slow reasoners"),
       ("○", "attribute orbs", "redesign the orbs per-attribute — see each change, not just material"),
       ("✦", "more agentic tools", "add window · change wall material — and optimise the ones we have")]
y = 184
for g, head, sub in nxt:
    para(c, 60, y, 60, "<font name='%s' color='#%s'>%s</font>" % (MONO, HUE["olfactory"], g), font=MONO, size=22)
    para(c, 122, y, 800, "<b>%s</b>" % head, font=SANS, size=19, color=FG)
    para(c, 122, y + 28, 800, "<font color='#%s'>%s</font>" % (MUTED, sub), font=SANS, size=13, color=MUTED)
    y += 82
para(c, 60, 474, 880, "<i>keep making the edges legible — now in pixels.</i>", font=SANS, size=14, color=HUE["olfactory"])
page(c)

c.save()
print("Saved:", OUT)
