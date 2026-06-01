"""
build_deck.py — generate the Sensi presentation deck as a PDF (reportlab).

12 slides: 8 content (title · philosophy · 3 maths · research · architecture · next)
+ 4 annotated hero screenshots. Minimal, visual, plainly-worded, with light visual cues
(colored sense glyphs, weight/veto bar-charts, a ripple node→node diagram, slide counters).

Screenshots auto-embed from team_02/docs/shots/ by filename (placeholders if absent):
    03-graph.png (mermaid) · 04-comfort.png · 05-topology.png · 06-galaxy.png · 07-whatif.png
Render the mermaid PNG with:  python team_02/docs/render_mermaid.py

Run:  python team_02/docs/build_deck.py
Out:  team_02/docs/Sensi-Presentation.pdf
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
SHOTS = HERE / "shots"; SHOTS.mkdir(exist_ok=True)
OUT = HERE / "Sensi-Presentation.pdf"

W, H = 960.0, 540.0  # 16:9 at 72dpi

# ── Palette (web/src/lib/senses.js) ────────────────────────────────────────────
HUE = {"thermal": "E8836A", "visual": "D4B96A", "acoustic": "9B8FD4",
       "spatial": "6AB8C8", "olfactory": "8BB88A", "tactile": "C4A882"}
GLYPH = {"thermal": "△", "visual": "○", "acoustic": "∿", "spatial": "□",
         "olfactory": "≈", "tactile": "∶"}
PASS, FAIL = "3FB97A", "E0524A"
BG, PANEL, BORDER = "0B0D10", "14171C", "2A2E35"
FG, MUTED, RED = "E6E8EC", "9AA0A8", "FF5247"
# mermaid node colors (for the architecture legend)
M_LLM, M_TOOL, M_PY, M_ON = "D6E8F8", "CDEFD9", "FCE9C8", "EAD5F5"

# ── Fonts (Windows TTFs; all offline) ──────────────────────────────────────────
_F = r"C:\Windows\Fonts"
def _reg(name, file, fallback):
    try:
        pdfmetrics.registerFont(TTFont(name, _F + "\\" + file)); return name
    except Exception:
        return fallback
SANS  = _reg("Sans",  "segoeui.ttf", "Helvetica")
SANSB = _reg("SansB", "seguisb.ttf", "Helvetica-Bold")
MONO  = _reg("Mono",  "consola.ttf", "Courier")
HAND  = _reg("Hand",  "segoepr.ttf", "Helvetica-Oblique")
SYM   = _reg("Sym",   "seguisym.ttf", SANS)

def col(h): return HexColor("#" + h)

# Some glyphs (△ ∿ ↔ ⚛ ❝ ◇ ✦ ● ∶) are missing in Segoe UI / Consolas and render
# as tofu; draw those code points with Segoe UI Symbol instead.
_SYM_CHARS = "△∿↔⚛❝◇✦●∶"
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
                        leading=leading or size * 1.32, alignment=align)
    p = Paragraph(symify(html), st); pw, ph = p.wrap(w, H)
    p.drawOn(c, x, H - yt - ph); return ph


def rrect(c, x, yt, w, h, *, fill=PANEL, stroke=BORDER, r=10, sw=1):
    if fill: c.setFillColor(col(fill))
    if stroke: c.setStrokeColor(col(stroke)); c.setLineWidth(sw)
    c.roundRect(x, H - yt - h, w, h, r, stroke=1 if stroke else 0, fill=1 if fill else 0)


def img(c, x, yt, w, h, name, hue):
    f = SHOTS / name
    if f.exists():
        rrect(c, x, yt, w, h, fill=PANEL, stroke=hue, sw=1.5)
        try:
            c.drawImage(ImageReader(str(f)), x + 5, H - yt - h + 5, w - 10, h - 10,
                        preserveAspectRatio=True, anchor="c", mask="auto")
            return
        except Exception:
            pass
    rrect(c, x, yt, w, h, fill=PANEL, stroke=hue, sw=1.25)
    c.setFillColor(col(MUTED)); c.setFont(MONO, 12)
    c.drawCentredString(x + w / 2, H - yt - h / 2 - 4, "[ drop  shots/" + name + " ]")


def hand(c, x, yt, w, text, *, size=15, align=TA_LEFT, rot=0):
    st = ParagraphStyle("h", fontName=HAND, fontSize=size, textColor=col(RED),
                        leading=size * 1.12, alignment=align)
    p = Paragraph(symify(text), st); pw, ph = p.wrap(w, H)
    if rot:
        c.saveState(); c.translate(x, H - yt - ph); c.rotate(rot); p.drawOn(c, 0, 0); c.restoreState()
    else:
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


def circle(c, cx, cyt, rx, ry, *, width=2.2):
    c.setStrokeColor(col(RED)); c.setLineWidth(width); c.setFillColor(col(BG))
    c.ellipse(cx - rx, H - cyt - ry, cx + rx, H - cyt + ry, stroke=1, fill=0)


def kicker(c, text, hue):
    bar(c, 40, 42, hue)
    c.setFillColor(col(hue)); c.setFont(MONO, 11)
    c.drawString(84, H - 50, text)


def counter(c, n):
    c.setFillColor(col(MUTED)); c.setFont(MONO, 10)
    c.drawRightString(W - 40, H - 50, "%02d / 12" % n)


def eq_card(c, x, yt, w, h, eq, gloss, tag, hue):
    rrect(c, x, yt, w, h)
    para(c, x + 22, yt + 18, w - 44, eq, font=MONO, size=21, color=FG)
    para(c, x + 22, yt + h - 42, w - 220, gloss, font=SANS, size=13, color=MUTED)
    para(c, x + w - 250, yt + h - 30, 230, tag, font=MONO, size=10.5, color=hue, align=TA_RIGHT)


def vbars(c, x, yt, items, *, maxh=64, bw=24, gap=20):
    """items: list of (hue, value 0..1, glyph). Vertical bars on a shared baseline."""
    base = H - (yt + maxh)
    for i, (hue, val, g) in enumerate(items):
        bx = x + i * (bw + gap)
        bh = max(4, maxh * val)
        c.setFillColor(col(hue)); c.roundRect(bx, base, bw, bh, 3, stroke=0, fill=1)
        c.setFont(SYM, 13); c.setFillColor(col(hue))
        c.drawCentredString(bx + bw / 2, base - 17, g)
    return x + len(items) * (bw + gap) - gap


def ripple_viz(c, x, yt, ah, bh, ag, bg_, alabel, blabel, caption):
    """Two sense nodes A→B with a green 'lift' arrow — the ripple, visualized."""
    ay = H - yt
    for cx, hue, g in ((x + 16, ah, ag), (x + 172, bh, bg_)):
        c.setFillColor(col(hue)); c.circle(cx, ay, 15, stroke=0, fill=1)
        c.setFillColor(col(BG)); c.setFont(SYM, 13); c.drawCentredString(cx, ay - 5, g)
    c.setStrokeColor(col(PASS)); c.setLineWidth(2.4); c.setLineCap(1); c.line(x + 34, ay, x + 150, ay)
    p = c.beginPath(); p.moveTo(x + 156, ay); p.lineTo(x + 146, ay + 5); p.lineTo(x + 146, ay - 5); p.close()
    c.setFillColor(col(PASS)); c.drawPath(p, fill=1, stroke=0)
    c.setFont(SANS, 10); c.setFillColor(col(MUTED))
    c.drawCentredString(x + 16, ay - 32, alabel); c.drawCentredString(x + 172, ay - 32, blabel)
    c.setFillColor(col(PASS)); c.setFont(SANS, 9); c.drawCentredString(x + 92, ay + 9, "+ lift")
    c.setFillColor(col(MUTED)); c.setFont(SANS, 11); c.drawString(x, ay - 54, caption)


def chip(c, x, yt, hue, label):
    c.setFillColor(col(hue)); c.roundRect(x, H - yt - 12, 15, 11, 2, stroke=0, fill=1)
    c.setFillColor(col(MUTED)); c.setFont(MONO, 10); c.drawString(x + 23, H - yt - 11, label)


def page(c):
    c.showPage()


def hero(c, hue, kick, title, name, callouts, circ, n):
    bg(c); kicker(c, kick, hue); counter(c, n)
    para(c, 40, 70, 600, "<b>" + title + "</b>", font=SANSB, size=23, color=FG)
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
    if circ:
        circle(c, *circ)
    page(c)


c = canvas.Canvas(str(OUT), pagesize=(W, H))

# ── 1 · TITLE ───────────────────────────────────────────────────────────────
bg(c)
c.setFillColor(col(FG)); c.setFont(MONO, 66); c.drawString(70, H - 250, "SENSI")
para(c, 72, 268, 800, "a sensorial-comfort copilot for architectural layouts", font=SANS, size=20, color=MUTED)
para(c, 72, 320, 800, "<i>the number isn’t the lesson — the edges are</i>", font=SANS, size=15, color=HUE["acoustic"])
glyphrow = "&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;".join(
    "<font color='#%s'>%s</font> %s" % (HUE[k], GLYPH[k], k) for k in HUE)
para(c, 72, 425, 880, glyphrow, font=SANS, size=14, color=MUTED)
page(c)

# ── 2 · PHILOSOPHY ────────────────────────────────────────────────────────────
bg(c); kicker(c, "01 · THE IDEA", HUE["acoustic"]); counter(c, 2)
para(c, 40, 78, 880, "<b>A space is a conversation between your senses</b>", font=SANSB, size=30, color=FG)
para(c, 40, 150, 600,
     "Soften a wall and the room goes quiet. Open a window and it smells fresh — but gets louder. "
     "Every change <b>echoes</b> from one sense to the next.<br/><br/>"
     "Sensi reads that conversation, and teaches it.", font=SANS, size=17, color=FG, leading=25)
rrect(c, 690, 150, 230, 230, fill=PANEL, stroke=HUE["acoustic"], sw=1.25)
para(c, 712, 172, 188,
     "“The overall score is the least interesting part. The lesson lives in the <b>edges</b> — "
     "how a change to one sense ripples to another.”", font=SANS, size=13, color=HUE["acoustic"], leading=18)
para(c, 40, 432, 880,
     "<font name='%s' color='#%s'>what it does &nbsp;·&nbsp;</font> reads a plan &nbsp;→&nbsp; scores 6 senses against <i>your</i> persona "
     "&nbsp;→&nbsp; finds conflicts &nbsp;→&nbsp; suggests &amp; edits &nbsp;→&nbsp; shows the ripple"
     % (MONO, MUTED), font=SANS, size=14, color=FG)
page(c)

# ── 3 · MODEL · PERSONALIZATION ───────────────────────────────────────────────
bg(c); kicker(c, "02 · THE MODEL · YOU", HUE["thermal"]); counter(c, 3)
para(c, 40, 78, 880, "<b>No two people feel a room the same</b>", font=SANSB, size=28, color=FG)
para(c, 40, 142, 880,
     "A calm introvert and a buzzy extrovert want opposite things from the same living room. So Sensi "
     "never scores against an average — your onboarding becomes a set of <b>weights</b>, and those weights "
     "decide what “comfortable” means for you. Care more about a sense, and Sensi flags it sooner.",
     font=SANS, size=16, color=FG, leading=24)
eq_card(c, 40, 262, 560, 110,
        "t = clamp( 0.35 + 0.40·w , 0.35 , 0.75 )",
        "your weight w → your personal alert threshold t",
        "context-dependent weights ·<br/>R1 · R5", HUE["thermal"])
# visual cue — Emilie's weights as bars
para(c, 660, 250, 260, "<font name='%s'>EMILIE’S WEIGHTS</font>" % MONO, font=MONO, size=10, color=MUTED)
vbars(c, 662, 278, [(HUE["thermal"], .90, "△"), (HUE["visual"], .74, "○"), (HUE["acoustic"], .80, "∿"),
                    (HUE["spatial"], .80, "□"), (HUE["olfactory"], .90, "≈"), (HUE["tactile"], .90, "∶")])
page(c)

# ── 4 · MODEL · THE HONEST NUMBER ─────────────────────────────────────────────
bg(c); kicker(c, "02 · THE MODEL · THE HONEST NUMBER", FAIL); counter(c, 4)
para(c, 40, 78, 880, "<b>We don’t average the senses</b>", font=SANSB, size=28, color=FG)
para(c, 40, 142, 560,
     "Averaging hides disasters. A room that’s perfect in five senses and unbearable in one isn’t "
     "“83% comfortable” — it’s unbearable. So the overall score leans on the <b>worst</b> sense: a "
     "one-vote veto. You can’t paper over a bad sense by being great elsewhere.",
     font=SANS, size=16, color=FG, leading=24)
# visual cue — five fine, one fails → floored
para(c, 660, 120, 260, "<font name='%s'>5 FINE · 1 FAILS</font>" % MONO, font=MONO, size=10, color=MUTED)
vbars(c, 662, 150, [(HUE["thermal"], .82, "△"), (HUE["visual"], .80, "○"), (HUE["acoustic"], .78, "∿"),
                    (HUE["spatial"], .84, "□"), (FAIL, .18, "≈"), (HUE["tactile"], .80, "∶")])
circle(c, 662 + 4 * 44 + 12, 168, 22, 44)
para(c, 660, 250, 260, "<font color='#%s'>→ the room is scored by the worst, not the mean</font>" % RED,
     font=HAND, size=13, color=RED)
eq_card(c, 40, 322, 880, 96,
        "overall = (1−v)·mean_w + v·worst&nbsp;&nbsp;&nbsp;(v = 0.5)",
        "half the preference-weighted mean, half the single worst sense",
        "non-additive IEQ comfort ·<br/>Yang &amp; Moon 2019 (S2)", FAIL)
page(c)

# ── 5 · MODEL · THE RIPPLE ────────────────────────────────────────────────────
bg(c); kicker(c, "02 · THE MODEL · THE RIPPLE", HUE["acoustic"]); counter(c, 5)
para(c, 40, 76, 880, "<b>Senses don’t live in separate boxes</b>", font=SANSB, size=28, color=FG)
para(c, 40, 120, 880, "<i>“ how a change to one sense ripples to another ”</i>", font=SANS, size=15, color=HUE["acoustic"])
para(c, 40, 158, 540,
     "Soft surfaces absorb sound — a cosier floor makes a room quieter. A stuffy room feels hotter than "
     "it is. When one sense changes, Sensi nudges its partners and <b>labels every nudge with why</b> "
     "(research or physics). Discomfort spreads a little harder than comfort.",
     font=SANS, size=15, color=FG, leading=22)
# visual cue — the ripple, one edge
ripple_viz(c, 620, 168, HUE["tactile"], HUE["acoustic"], "∶", "∿", "tactile", "acoustic",
           "soft floor → a quieter room")
eq_card(c, 40, 300, 880, 92,
        "src &lt; 0.50 → partner −0.06&nbsp;&nbsp;·&nbsp;&nbsp;src ≥ 0.70 (+edge) → +0.04",
        "a failing sense drags its partners; a strong one lifts them (capped)",
        "multisensory thermal review<br/>2025 · Spence 2020 (R2)", HUE["acoustic"])
para(c, 40, 406, 880,
     "<font name='%s' color='#%s'>edges &nbsp;</font> acoustic↔thermal · ventilation→olfactory · tactile→acoustic · glazing↔acoustic"
     % (MONO, MUTED), font=MONO, size=12, color=FG)
para(c, 40, 442, 880,
     "<font name='%s' color='#%s'>+ personality &nbsp;</font> introverts read “busy” as “too much”, so we tilt the stimulation "
     "senses:&nbsp; <font name='%s'>δ = 0.15·p·(stim − 0.5)</font>" % (MONO, MUTED, MONO),
     font=SANS, size=13, color=FG)
page(c)

# ── 6 · RESEARCH ──────────────────────────────────────────────────────────────
bg(c); kicker(c, "02 · THE MODEL · GROUNDED", PASS); counter(c, 6)
para(c, 40, 78, 620, "<b>None of this is invented</b>", font=SANSB, size=28, color=FG)
para(c, 40, 145, 620,
     "The couplings come from peer-reviewed building science. We ran every claim through an "
     "<b>adversarial fact-check</b> — and threw out the ones that didn’t survive (e.g. “acoustic always "
     "matters most”). Where evidence is thin, we encode the <i>direction</i> of an effect, not a "
     "fake-precise number.", font=SANS, size=16, color=FG, leading=24)
rrect(c, 700, 130, 220, 150, fill=PANEL, stroke=PASS, sw=1.5)
c.setFillColor(col(PASS)); c.setFont(SANSB, 52); c.drawCentredString(810, H - 215, "18 / 25")
para(c, 715, 222, 190, "claims confirmed by a 3-vote test", font=SANS, size=12, color=MUTED, align=TA_CENTER)
para(c, 40, 360, 880,
     "<font name='%s' color='#%s'>R1</font> autism sensory taxonomy &nbsp;·&nbsp; "
     "<font name='%s' color='#%s'>R2</font> multisensory mind &nbsp;·&nbsp; "
     "<font name='%s' color='#%s'>R3</font> cross-modal thermal &nbsp;·&nbsp; "
     "<font name='%s' color='#%s'>R5</font> arousal &nbsp;·&nbsp; "
     "<font name='%s' color='#%s'>R6</font> tactile warmth"
     % (MONO, HUE["thermal"], MONO, HUE["visual"], MONO, HUE["spatial"], MONO, HUE["olfactory"], MONO, HUE["tactile"]),
     font=SANS, size=13, color=MUTED)
para(c, 40, 392, 880,
     "<font name='%s' color='#%s'>S2</font> non-additive + acoustic↔thermal &nbsp;·&nbsp; "
     "<font name='%s' color='#%s'>S5</font> BS 8233 acoustic targets &nbsp;·&nbsp; "
     "<font name='%s' color='#%s'>S6</font> ASHRAE ventilation→olfactory"
     % (MONO, HUE["acoustic"], MONO, HUE["acoustic"], MONO, HUE["olfactory"]),
     font=SANS, size=13, color=MUTED)
page(c)

# ── 7 · ARCHITECTURE ──────────────────────────────────────────────────────────
bg(c); kicker(c, "03 · ARCHITECTURE", HUE["visual"]); counter(c, 7)
para(c, 40, 66, 880, "<b>From a desktop plugin to the browser</b>", font=SANSB, size=24, color=FG)
para(c, 40, 116, 320, "<font name='%s' color='#%s'>WAS</font>" % (MONO, MUTED), font=MONO, size=11, color=MUTED)
para(c, 40, 134, 320, "MCP · PyQt5 · Grasshopper / Rhino", font=SANS, size=14, color=MUTED)
c.setStrokeColor(col(RED)); c.setLineWidth(2.2); c.line(44, H - 146, 300, H - 142)
arrow(c, 318, 142, 392, 142, width=2)
para(c, 410, 116, 510, "<font name='%s' color='#%s'>NOW</font>" % (MONO, PASS), font=MONO, size=11, color=PASS)
para(c, 410, 134, 510, "FastAPI · React + Vite · LangGraph · in-process tools", font=SANS, size=14, color=FG)
# mermaid (portrait) on the left
img(c, 40, 178, 300, 330, "03-graph.png", HUE["visual"])
# notes + color legend on the right
para(c, 380, 190, 540,
     "<font name='%s'>26 nodes, verified</font><br/><br/>"
     "<b>one action_classifier</b>  →  13 actions in one call<br/><br/>"
     "<b>cache-aware</b> re-scoring (skip redundant work)<br/><br/>"
     "<b>edit → re-score → compare</b>  <i><font color='#%s'>= the agentic ripple</font></i>"
     % (MONO, HUE["visual"]), font=SANS, size=14, color=FG, leading=20)
para(c, 380, 400, 540, "<font name='%s'>WHAT THE COLOURS MEAN</font>" % MONO, font=MONO, size=10, color=MUTED)
chip(c, 382, 426, M_LLM, "LLM reasoning")
chip(c, 532, 426, M_TOOL, "in-process tool")
chip(c, 700, 426, M_PY, "Python step")
chip(c, 382, 450, M_ON, "onboarding (once)")
para(c, 40, 516, 880,
     "Rhino &amp; Grasshopper are no longer required — Sensi runs anywhere, behind one link.",
     font=SANS, size=12, color=HUE["olfactory"])
page(c)

# ── 8–11 · HERO SCREENSHOTS  (load → score → topology → galaxy) ────────────────
hero(c, HUE["tactile"], "04 · THE INSTRUMENT", "It starts with a layout", "07-layout.png",
     {"tl": "pick a layout —<br/>or upload your own", "tr": "rooms · walls ·<br/>openings · furniture",
      "bl": "parametric<br/>JSON in", "br": "no scores yet —<br/>just the space"},
     (440, 285, 74, 54), 8)

hero(c, HUE["thermal"], "04 · THE INSTRUMENT", "Scores, made personal", "04-comfort.png",
     {"tl": "ring = room’s<br/>overall score", "tr": "the rose —<br/>whole profile,<br/>one glance",
      "bl": "comfort tints<br/>each room", "br": "base → effective<br/>= the ripple ⚛ ❝"},
     (663, 212, 30, 28), 9)

hero(c, HUE["acoustic"], "04 · THE INSTRUMENT", "Room topology = sensory zoning", "05-topology.png",
     {"tl": "nodes = rooms<br/>size = doors", "tr": "arc = sense bleeding<br/>worse → better",
      "bl": "buffer loud rooms<br/>from quiet  [R1]", "br": "Hallway = hub —<br/>remove it, plan splits"},
     (455, 295, 34, 34), 10)

hero(c, HUE["spatial"], "04 · THE INSTRUMENT", "The relationship galaxy", "06-galaxy.png",
     {"tl": "the whole edge<br/>system, in 3D", "tr": "● senses<br/>● rooms<br/>● levers",
      "bl": "lazy three.js<br/>(code-split)", "br": "L1 / L2 / L3<br/>complexity"},
     (470, 295, 42, 42), 11)

# ── 12 · WHAT'S NEXT ──────────────────────────────────────────────────────────
bg(c); kicker(c, "05 · WHAT’S NEXT", HUE["olfactory"]); counter(c, 12)
para(c, 40, 80, 880, "<b>Make the edges more legible</b>", font=SANSB, size=30, color=FG)
items = [("∿", "make the ripple more visual", "pulses everywhere a value moves"),
         ("◇", "deepen the agentic loop", "the agent proposes, previews, you accept"),
         ("∑", "surface the formula", "see &amp; tune which coupling fired"),
         ("✦", "generative outputs", "images of the improved space + more")]
y = 180
for g, head, sub in items:
    para(c, 60, y, 60, "<font name='%s' color='#%s'>%s</font>" % (MONO, HUE["olfactory"], g), font=MONO, size=22)
    para(c, 120, y, 760, "<b>%s</b> &nbsp;—&nbsp; <font color='#%s'>%s</font>" % (head, MUTED, sub), font=SANS, size=19, color=FG)
    y += 70
para(c, 60, 470, 880, "<i>every one makes the edges more legible.</i>", font=SANS, size=14, color=HUE["olfactory"])
page(c)

c.save()
print("Saved:", OUT)
