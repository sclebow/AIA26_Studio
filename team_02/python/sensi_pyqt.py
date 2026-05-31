"""
sensi_pyqt.py — Sensi desktop app (PyQt5 + QWebEngineView)

Run:     python sensi_pyqt.py
Install: pip install PyQt5 PyQtWebEngine

Architecture:
  QMainWindow
  └── QWebEngineView          ← full-window browser frame
       └── ui/index.html      ← all Sensi screens (HTML/CSS/JS)
            └── QWebChannel   ← Python ↔ JS bridge (SensiBridge)

The UI lives entirely in HTML/CSS/JS.
Python exposes the LangGraph backend through SensiBridge slots.
"""

import sys
import json
import re
import os
from pathlib import Path

# ── DevTools: open http://localhost:19222 in Chrome while the app is running ──
os.environ["QTWEBENGINE_REMOTE_DEBUGGING"] = "19222"

# ── HiDPI: must be set at module level, BEFORE QtWebEngineWidgets is imported ──
# Importing QtWebEngineWidgets initialises Chromium — too late to set DPI after that.
from PyQt5.QtWidgets import QApplication
from PyQt5.QtCore import Qt
QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)

from PyQt5.QtWidgets import QMainWindow
from PyQt5.QtWebEngineWidgets import QWebEngineView, QWebEngineSettings
from PyQt5.QtWebChannel import QWebChannel
from PyQt5.QtCore import QObject, pyqtSlot, pyqtSignal, QThread, QUrl
from PyQt5.QtGui import QColor
from PyQt5.QtWebEngineWidgets import QWebEnginePage
from PyQt5.QtWidgets import QShortcut
from PyQt5.QtGui import QKeySequence

# Add the python/ directory to path so _runtime and graph are importable
sys.path.insert(0, str(Path(__file__).parent))

from _runtime.bootstrap import bootstrap
from graph import run_agent

# ── Paths ─────────────────────────────────────────────────────────────────────
_PERSONA_PATH = Path(__file__).resolve().parent.parent / "personas" / "persona.json"
_UI_PATH      = Path(__file__).resolve().parent / "ui" / "index.html"


# ═══════════════════════════════════════════════════════════════════════════════
# Worker threads  (keep the Qt main thread free — never block it with LLM calls)
# ═══════════════════════════════════════════════════════════════════════════════

class AgentWorker(QThread):
    """Runs one LangGraph turn off the main thread."""
    finished = pyqtSignal(str)   # JSON: {ok, message, session}
    error    = pyqtSignal(str)

    def __init__(self, text: str, ctx, session: dict):
        super().__init__()
        self.text    = text
        self.ctx     = ctx
        self.session = session

    def run(self):
        try:
            response, new_session = run_agent(self.text, self.ctx, self.session)
            self.finished.emit(json.dumps({
                "ok":      True,
                "message": response,
                "session": new_session,
            }))
        except Exception as exc:
            self.error.emit(json.dumps({"ok": False, "error": str(exc)}))


class InspireWorker(QThread):
    """VLM analysis + Unsplash query generation + image fetch — off the main thread."""
    finished = pyqtSignal(str)   # JSON: {ok, round, urls, descs, analysis}
    progress = pyqtSignal(str)   # status string sent to the loading overlay

    def __init__(self, text: str, b64s: list, ctx,
                 existing_analysis: str, round_num: int, refine_desc: str = ""):
        super().__init__()
        self.text              = text
        self.b64s              = b64s
        self.ctx               = ctx
        self.existing_analysis = existing_analysis
        self.round_num         = round_num
        self.refine_desc       = refine_desc

    def run(self):
        try:
            llm = self.ctx.llm_simple

            # Step 1 — VLM (first round only; subsequent rounds reuse analysis)
            self.progress.emit("reading your aesthetic...")
            analysis = (
                self.existing_analysis
                or _vlm_analyze(llm, self.b64s, self.text)
            )

            # Step 2 — Sense-tagged query generation (1 query per sense, 6 total)
            self.progress.emit("building search queries...")
            queries_sensed = _gen_queries_sensed(
                llm, analysis,
                prev_desc=self.refine_desc,
                n_per_sense=1,
            )

            # Step 3 — Fetch 2 images per query = 12 total for the 3×4 grid
            self.progress.emit("gathering images...")
            urls, descs, senses = _fetch_unsplash_sensed(
                queries_sensed, per_query=2, target=12
            )

            self.finished.emit(json.dumps({
                "ok":       True,
                "round":    self.round_num,
                "urls":     urls,
                "descs":    descs,
                "senses":   senses,
                "analysis": analysis,
            }))
        except Exception as exc:
            self.finished.emit(json.dumps({"ok": False, "error": str(exc)}))


class ProfileChatWorker(QThread):
    """
    Lightweight profile-review chat — direct LLM call, no graph required.
    Answers questions about the persona profile, formula, and weights.
    """
    finished = pyqtSignal(str)   # JSON: {ok, message}

    _SYSTEM = (
        "You are Sensi, helping the user understand and optionally refine their comfort profile.\n"
        "Speak warmly and specifically — reference actual numbers from their profile.\n\n"
        "You can:\n"
        "  • Explain how each comfort weight was derived from quiz answers and moodboard picks\n"
        "  • Explain the formula: C(room) = Σ w(s) × raw(room, s)\n"
        "  • Explain what 'evidence baseline' means and why a deviation matters\n"
        "  • Help the user reflect on whether something feels wrong\n"
        "  • Note requested changes (but explain major edits require a fresh session)\n\n"
        "Keep replies concise — 2–4 sentences. No bullet points. No markdown."
    )

    def __init__(self, text: str, profile: dict, llm):
        super().__init__()
        self.text    = text
        self.profile = profile
        self.llm     = llm

    def run(self):
        from langchain_core.messages import HumanMessage, SystemMessage
        try:
            profile_block = json.dumps(self.profile, indent=2, ensure_ascii=False)
            system_full   = f"{self._SYSTEM}\n\nCurrent profile:\n{profile_block}"
            messages = [
                SystemMessage(content=system_full),
                HumanMessage(content=self.text),
            ]
            reply = self.llm.invoke(messages).content.strip()
            self.finished.emit(json.dumps({"ok": True, "message": reply}))
        except Exception as exc:
            self.finished.emit(json.dumps({"ok": False, "error": str(exc)}))


# ═══════════════════════════════════════════════════════════════════════════════
# Inspire helpers — VLM + Unsplash pipeline
# ═══════════════════════════════════════════════════════════════════════════════

def _vlm_analyze(llm, images_b64: list, text_desc: str) -> str:
    from langchain_core.messages import HumanMessage
    SYSTEM = (
        "You are a spatial aesthetic analyst. Extract a rich sensory and visual "
        "profile from the provided reference images and/or description.\n\n"
        "Capture:\n"
        "  • Color palette — dominant hues, temperature (warm/cool), saturation\n"
        "  • Light quality — source (natural/artificial), quality (soft/harsh/diffuse), tone\n"
        "  • Materials & textures — wood, stone, concrete, fabric, metal, plaster, plant\n"
        "  • Spatial mood — intimate/open, minimal/layered, calm/dynamic, raw/refined\n"
        "  • Atmosphere — time of day feel, level of cosiness vs grandeur\n\n"
        "Write a specific, grounded aesthetic profile in 120–150 words. "
        "No lists. No headers. Just a flowing description."
    )
    if images_b64:
        content = [{"type": "text", "text": f"{SYSTEM}\n\nUser description: {text_desc}"}]
        for b64 in images_b64[:4]:
            content.append({"type": "image_url",
                             "image_url": {"url": f"data:image/jpeg;base64,{b64}"}})
        try:
            return llm.invoke([HumanMessage(content=content)]).content.strip()
        except Exception:
            pass  # fall through to text-only
    messages = [
        {"role": "system", "content": SYSTEM},
        {"role": "user",   "content": text_desc or "minimalist interior, warm and natural"},
    ]
    try:
        return llm.invoke(messages).content.strip()
    except Exception:
        return f"Aesthetic preference: {text_desc}"


def _gen_queries(llm, analysis: str, prev_desc: str = "", n: int = 4) -> list:
    from langchain_core.messages import HumanMessage
    extra  = f"\n\nThe user particularly liked: {prev_desc}" if prev_desc else ""
    prompt = (
        f"Aesthetic analysis:\n{analysis}{extra}\n\n"
        f"Generate {n} specific Unsplash search queries to find interior architectural spaces "
        f"matching this aesthetic. Include materials, light quality, and mood words.\n"
        f"RULES: Every query MUST describe an interior room, residential space, or architectural scene. "
        f"No people, no landscapes, no food, no fashion, no abstract imagery.\n"
        f"Each query = 3–5 words.\nReturn ONLY a JSON array: [\"q1\", \"q2\", ...]"
    )
    defaults = [
        "minimal interior warm natural light",
        "calm architectural space texture material",
        "serene residential room daylight",
        "intimate atmospheric interior comfort",
    ]
    try:
        resp = llm.invoke([HumanMessage(content=prompt)])
        m = re.search(r"\[.*?\]", resp.content, re.DOTALL)
        if m:
            parsed = json.loads(m.group())
            if isinstance(parsed, list) and parsed:
                return [str(q) for q in parsed[:n]]
    except Exception:
        pass
    return defaults[:n]


_SENSE_DESCRIPTORS = {
    "thermal":   "warmth, temperature, sun exposure, radiant heat, cozy warmth, fireplace",
    "visual":    "light quality, color palette, brightness, shadow play, visual texture",
    "acoustic":  "sound absorption, quiet atmosphere, soft materials, echo, acoustic quality",
    "spatial":   "spatial volume, ceiling height, openness, layout, proportion, flow",
    "olfactory": "natural materials, plants, wood, earthy quality, fresh air, greenery",
    "tactile":   "material texture, roughness, softness, tactile surfaces, woven fabric",
}
_SENSE_ORDER = ["thermal", "visual", "acoustic", "spatial", "olfactory", "tactile"]


def _gen_queries_sensed(llm, analysis: str, prev_desc: str = "", n_per_sense: int = 2) -> list:
    """
    Returns a list of (query_str, sense_str) tuples — n_per_sense per sense.
    6 senses × 2 = 12 sense-tagged queries for a full 3×4 grid.
    """
    from langchain_core.messages import HumanMessage
    extra  = f"\n\nThe user particularly liked: {prev_desc}" if prev_desc else ""
    sense_lines = "\n".join(
        f'  - {s}: focus on {d}' for s, d in _SENSE_DESCRIPTORS.items()
    )
    example_obj = (
        '{"thermal":["q1","q2"],"visual":["q3","q4"],"acoustic":["q5","q6"],'
        '"spatial":["q7","q8"],"olfactory":["q9","q10"],"tactile":["q11","q12"]}'
    )
    prompt = (
        f"Aesthetic analysis:\n{analysis}{extra}\n\n"
        f"Generate {n_per_sense} Unsplash search queries per sensory category to find interior "
        f"architectural spaces matching this aesthetic.\n"
        f"RULES: Every query MUST describe an interior room, residential space, or architectural scene. "
        f"No people, no landscapes, no food, no fashion, no abstract imagery.\n"
        f"Each query = 3–5 words.\n\n"
        f"Sensory categories:\n{sense_lines}\n\n"
        f"Return ONLY a JSON object matching this shape exactly:\n{example_obj}"
    )
    defaults = {
        "thermal":   ["warm sunlit interior cozy", "fireplace living room warmth"],
        "visual":    ["diffuse natural light minimal interior", "bright airy architectural space"],
        "acoustic":  ["quiet library soft materials interior", "calm reading nook absorptive"],
        "spatial":   ["open plan high ceiling loft", "intimate courtyard spatial volume"],
        "olfactory": ["indoor plants greenery natural material", "wood stone earthy interior"],
        "tactile":   ["rough concrete tactile texture interior", "woven fabric soft surface room"],
    }
    try:
        resp = llm.invoke([HumanMessage(content=prompt)])
        m = re.search(r"\{.*\}", resp.content, re.DOTALL)
        if m:
            parsed = json.loads(m.group())
            if isinstance(parsed, dict):
                result = []
                for sense in _SENSE_ORDER:
                    qs = parsed.get(sense, defaults[sense])
                    for q in (qs or defaults[sense])[:n_per_sense]:
                        result.append((str(q), sense))
                return result
    except Exception:
        pass
    result = []
    for sense in _SENSE_ORDER:
        for q in defaults[sense][:n_per_sense]:
            result.append((q, sense))
    return result


_SENSE_FALLBACKS = {
    "thermal":   "warm sunlit room interior",
    "visual":    "natural light minimal interior",
    "acoustic":  "quiet cozy reading nook interior",
    "spatial":   "open loft architectural space",
    "olfactory": "indoor plants greenery room",
    "tactile":   "wood texture material interior",
}
_SENSE_EXTRAS = [
    ("minimalist interior warm light",      "visual"),
    ("cozy residential room texture",       "tactile"),
    ("serene architectural space calm",     "spatial"),
    ("warm wood interior sunlight",         "thermal"),
    ("calm interior soft diffuse light",    "acoustic"),
    ("earthy natural material room",        "olfactory"),
]


def _fetch_unsplash_sensed(queries_with_senses: list, per_query: int = 2,
                           target: int = 12) -> tuple:
    """
    queries_with_senses: list of (query_str, sense_str).
    Fetches per_query images per query, tags each with its source sense.
    Retries senses that returned 0 images using fallback queries.
    Pads up to target=12 with generic extras if still short.
    Returns (urls, descs, senses) where senses is a list of [sense] lists.
    """
    import httpx
    key = os.getenv("UNSPLASH_ACCESS_KEY", "")
    if not key:
        return [], [], []

    urls, descs, sense_tags = [], [], []
    sense_counts: dict = {}

    def _call(q: str, sense: str, n: int) -> int:
        added = 0
        try:
            resp = httpx.get(
                "https://api.unsplash.com/search/photos",
                params={"query": q, "per_page": n, "orientation": "landscape"},
                headers={"Authorization": f"Client-ID {key}"},
                timeout=10.0,
            )
            if resp.status_code == 200:
                for r in resp.json().get("results", []):
                    urls.append(r["urls"]["small"])
                    descs.append(r.get("alt_description") or q)
                    sense_tags.append([sense])
                    sense_counts[sense] = sense_counts.get(sense, 0) + 1
                    added += 1
        except Exception:
            pass
        return added

    # Primary pass
    for q, sense in queries_with_senses:
        _call(q, sense, per_query)

    # Retry senses that returned 0 images
    for sense in _SENSE_ORDER:
        if sense_counts.get(sense, 0) == 0 and len(urls) < target:
            _call(_SENSE_FALLBACKS[sense], sense, 2)

    # Generic top-up if still short of target
    for q, sense in _SENSE_EXTRAS:
        if len(urls) >= target:
            break
        _call(q, sense, target - len(urls))

    return urls[:target], descs[:target], sense_tags[:target]


def _fetch_unsplash(queries: list, per_query: int = 3) -> tuple:
    import httpx
    key = os.getenv("UNSPLASH_ACCESS_KEY", "")
    if not key:
        return [], []
    urls, descs = [], []
    for q in queries:
        try:
            resp = httpx.get(
                "https://api.unsplash.com/search/photos",
                params={"query": q, "per_page": per_query, "orientation": "landscape"},
                headers={"Authorization": f"Client-ID {key}"},
                timeout=10.0,
            )
            if resp.status_code == 200:
                for r in resp.json().get("results", []):
                    urls.append(r["urls"]["small"])
                    descs.append(r.get("alt_description") or q)
        except Exception:
            pass
    return urls, descs


# ═══════════════════════════════════════════════════════════════════════════════
# Bridge  — Python object exposed to JavaScript via QWebChannel
# ═══════════════════════════════════════════════════════════════════════════════

class SensiBridge(QObject):
    """
    Every public @pyqtSlot method is callable from JS as:
        bridge.methodName(arg1, arg2)
    Python calls JS by:
        self._js("functionName", arg1, arg2)
    """

    def __init__(self, view: QWebEngineView, ctx):
        super().__init__()
        self._view    = view
        self._ctx     = ctx
        self._session: dict = {}
        self._inspire: dict = {
            "analysis":    "",
            "text":        "",
            "b64s":        [],
            "r1_picks":    [],
            "r2_picks":    [],
            "final_picks": [],
        }
        self._worker = None   # reference kept to prevent GC

    # ── Internal helpers ──────────────────────────────────────────────────────

    def _js(self, fn: str, *args):
        """Call window.<fn>(...args) in the browser, args JSON-serialised."""
        serialized = ", ".join(json.dumps(a) for a in args)
        self._view.page().runJavaScript(f"window.{fn}({serialized})")

    def _read_persona(self) -> dict | None:
        if _PERSONA_PATH.exists():
            try:
                return json.loads(_PERSONA_PATH.read_text(encoding="utf-8"))
            except Exception:
                pass
        return None

    def _screen_from_session(self, sess: dict) -> str:
        if not sess.get("quiz_complete"):
            return "quiz"
        if not sess.get("inspire_complete"):
            return "inspire"
        return "chat"

    # ── App lifecycle ─────────────────────────────────────────────────────────

    @pyqtSlot()
    def initApp(self):
        """
        Called by JS once the page is fully loaded.
        Returns initial state so JS can route to the right screen.
        """
        persona = self._read_persona()
        if persona:
            self._session = {
                "onboarding_complete": True,
                "greeted":             True,
                "quiz_complete":       True,
                "inspire_complete":    True,
                "persona_profile":     persona,
                "user_type":           persona.get("role", "client"),
            }
            name = persona.get("name", "")
            msg  = (
                f"Welcome back{', ' + name if name else ''}! "
                "Your comfort profile is loaded. "
                "Tell me which layout you'd like to explore."
            )
            self._js("receiveInit", {
                "screen":     "chat",
                "message":    msg,
                "has_persona": True,
                "persona":    persona,
            })
        else:
            # Run the silent greeting turn (empty input → greet node fires)
            self._worker = AgentWorker("", self._ctx, {})
            self._worker.finished.connect(self._on_init_done)
            self._worker.error.connect(
                lambda e: self._js("receiveError", json.loads(e).get("error", e))
            )
            self._worker.start()

    def _on_init_done(self, result_json: str):
        result = json.loads(result_json)
        if result.get("ok"):
            self._session = result["session"]
            self._js("receiveInit", {
                "screen":      "quiz",
                "message":     result["message"],
                "has_persona": False,
                "quiz_step":   self._session.get("quiz_step", 0),
            })
        else:
            self._js("receiveError", result.get("error", "init failed"))

    @pyqtSlot()
    def resetPersona(self):
        """Delete persona.json and restart full onboarding."""
        if _PERSONA_PATH.exists():
            _PERSONA_PATH.unlink()
        self._session = {}
        self._inspire = {
            "analysis": "", "text": "", "b64s": [],
            "r1_picks": [], "r2_picks": [], "final_picks": [],
        }
        self.initApp()

    # ── Quiz + Chat turns ─────────────────────────────────────────────────────

    @pyqtSlot(str)
    def sendMessage(self, text: str):
        """
        Run one agent turn.  Works for both quiz and chat contexts —
        the graph routes internally based on session state.
        """
        self._worker = AgentWorker(text, self._ctx, self._session)
        self._worker.finished.connect(self._on_agent_response)
        self._worker.error.connect(
            lambda e: self._js("receiveError", json.loads(e).get("error", e))
        )
        self._worker.start()

    def _on_agent_response(self, result_json: str):
        result = json.loads(result_json)
        if not result.get("ok"):
            self._js("receiveError", result.get("error", "agent error"))
            return

        self._session = result["session"]
        sess          = self._session
        screen        = self._screen_from_session(sess)

        self._js("receiveResponse", {
            "ok":                   True,
            "screen":               screen,
            "message":              result["message"],
            "quiz_step":            sess.get("quiz_step", 0),
            "quiz_complete":        sess.get("quiz_complete", False),
            "inspire_complete":     sess.get("inspire_complete", False),
            "onboarding_complete":  sess.get("onboarding_complete", False),
            "layout_id":            sess.get("layout_id"),
            # Analysis panel data — raw MCP results
            "scores_json":          sess.get("last_scores_json", ""),
            "conflicts_json":       sess.get("last_conflicts_json", ""),
            "suggestions_json":     sess.get("last_suggestions_json", ""),
            "analysis_depth":       sess.get("comfort_depth", ""),
            # Specialist interpretations for panel narrative sections
            "score_interpretation": sess.get("score_interpretation", ""),
            "conflict_reasoning":   sess.get("conflict_reasoning", ""),
            "suggestion_critique":  sess.get("suggestion_critique", ""),
        })

    # ── File picker (native OS dialog) ───────────────────────────────────────

    @pyqtSlot()
    def openFilePicker(self):
        """Open a native file dialog; base64-encode selected images → receiveFiles."""
        import base64
        from PyQt5.QtWidgets import QFileDialog
        files, _ = QFileDialog.getOpenFileNames(
            None, "Select reference images", "",
            "Images (*.jpg *.jpeg *.png *.webp)"
        )
        if not files:
            return
        b64s = []
        for f in files[:5]:
            try:
                b64s.append(base64.b64encode(Path(f).read_bytes()).decode())
            except Exception:
                pass
        self._js("receiveFiles", b64s)

    # ── Inspire pipeline ──────────────────────────────────────────────────────

    @pyqtSlot(str, str, int)
    def prepareInspire(self, text: str, b64s_json: str, round_num: int):
        """
        Kick off VLM analysis + Unsplash fetch for round <round_num>.
        b64s_json: JSON array of base64-encoded image strings (may be "[]").
        Calls window.receiveImages({round, urls, descs}) when done.
        """
        b64s = json.loads(b64s_json) if b64s_json else []
        self._inspire["text"] = text
        self._inspire["b64s"] = b64s

        self._worker = InspireWorker(
            text, b64s, self._ctx,
            self._inspire["analysis"],
            round_num,
        )
        self._worker.progress.connect(
            lambda msg: self._js("receiveProgress", msg)
        )
        self._worker.finished.connect(self._on_inspire_ready)
        self._worker.start()

    @pyqtSlot(str, int)
    def refineInspire(self, refine_desc: str, round_num: int):
        """Fetch next image round with a refinement cue."""
        self._worker = InspireWorker(
            self._inspire["text"],
            self._inspire["b64s"],
            self._ctx,
            self._inspire["analysis"],
            round_num,
            refine_desc,
        )
        self._worker.progress.connect(
            lambda msg: self._js("receiveProgress", msg)
        )
        self._worker.finished.connect(self._on_inspire_ready)
        self._worker.start()

    def _on_inspire_ready(self, result_json: str):
        result = json.loads(result_json)
        if result.get("ok"):
            self._inspire["analysis"] = result.get("analysis", self._inspire["analysis"])
            self._js("receiveImages", {
                "round":  result["round"],
                "urls":   result["urls"],
                "descs":  result["descs"],
                "senses": result.get("senses", []),
            })
        else:
            self._js("receiveError", result.get("error", "inspire fetch failed"))

    @pyqtSlot(int, str)
    def saveInspirePicks(self, round_num: int, urls_json: str):
        """Store the user's selected image URLs for a given round."""
        urls = json.loads(urls_json)
        key  = {1: "r1_picks", 2: "r2_picks", 3: "final_picks"}.get(round_num, "final_picks")
        self._inspire[key] = urls

    @pyqtSlot(str)
    def buildMoodboard(self, sense_counts_json: str = "{}"):
        """
        Finalise the inspire phase:
        1. Inject image data + moodboard sense pick counts into session state
        2. Send the aesthetic description to the graph (triggers persona_compiler)
        3. Return persona data via window.receivePersona(...)

        Args:
            sense_counts_json: JSON object mapping sense name → number of images
                               the user selected from that sense category across
                               all moodboard rounds. Example: '{"visual":4,"spatial":2}'.
                               Computed by JS in finaliseMoodboard() from
                               S.inspireSensesPerRound + S.inspireSelectedPerRound.
        """
        all_picks: list = list(dict.fromkeys(
            self._inspire["r1_picks"] +
            self._inspire["r2_picks"] +
            self._inspire["final_picks"]
        ))

        # Parse the sense pick counts sent from JS
        try:
            sense_picks: dict = json.loads(sense_counts_json) if sense_counts_json else {}
        except Exception:
            sense_picks = {}

        # Mirror what app.py does before calling run_agent
        self._session["inspire_image_analysis"] = self._inspire["analysis"]
        self._session["inspire_moodboard_urls"]  = all_picks
        self._session["inspire_sense_picks"]     = sense_picks   # ← new: sense pick counts
        self._session["inspire_prompted"]        = True  # UI handled the aesthetic question; skip inspire sub-step A

        if sense_picks:
            print(f"[buildMoodboard] Sense picks from moodboard: {sense_picks}")

        # Include user_name explicitly so persona_compiler has it even if
        # quiz_answers didn't carry through cleanly.
        user_name = self._session.get("user_name", "")
        context = (
            f"User name: {user_name}\n"
            f"{self._inspire['text']}\n\n"
            f"[Moodboard context: user selected {len(all_picks)} reference image(s) "
            f"across aesthetic refinement rounds.]"
        )

        self._worker = AgentWorker(context, self._ctx, self._session)
        self._worker.finished.connect(lambda r: self._on_moodboard_done(r, all_picks))
        self._worker.error.connect(
            lambda e: self._js("receiveError", json.loads(e).get("error", e))
        )
        self._worker.start()

    def _on_moodboard_done(self, result_json: str, all_picks: list):
        result = json.loads(result_json)
        if result.get("ok"):
            self._session = result["session"]
            persona = dict(self._session.get("persona_profile") or {})

            # Fallback: patch name/role from session data if LLM returned defaults
            stored_name = persona.get("name", "")
            if not stored_name or stored_name.lower() in ("user", "there", ""):
                fallback_name = self._session.get("user_name", "")
                if fallback_name and fallback_name.lower() not in ("there", ""):
                    persona["name"] = fallback_name.strip().capitalize()

            stored_role = persona.get("role", "client")
            if stored_role == "client":
                sess_role = (
                    self._session.get("user_type") or
                    self._session.get("preliminary_role", "client")
                )
                if sess_role and sess_role not in ("client", "", None):
                    persona["role"] = sess_role

            self._js("receivePersona", {
                "persona":        persona,
                "moodboard_urls": all_picks[:6],
                "message":        result["message"],
            })
        else:
            self._js("receiveError", result.get("error", "moodboard failed"))

    # ── Profile review chat ───────────────────────────────────────────────────

    @pyqtSlot(str)
    def profileChat(self, text: str):
        """
        Handle profile-review chat messages.
        Responds to questions about the formula, weights, and persona details.
        Uses a lightweight direct LLM call — no graph required.
        """
        profile = self._session.get("persona_profile") or {}
        worker  = ProfileChatWorker(text, profile, self._ctx.llm_simple)
        # Keep reference to prevent GC
        self._worker = worker
        worker.finished.connect(
            lambda r: self._js("receiveProfileChat", json.loads(r))
        )
        worker.start()


# ═══════════════════════════════════════════════════════════════════════════════
# Main window
# ═══════════════════════════════════════════════════════════════════════════════

class SensiWindow(QMainWindow):
    def __init__(self, ctx):
        super().__init__()
        self.setWindowTitle("sensi")
        self.setMinimumSize(480, 600)
        self.resize(960, 1000)
        self.setStyleSheet("background:#0D0D0D;")

        # Web view
        self.view = QWebEngineView(self)
        self.setCentralWidget(self.view)

        # Settings  (PyQt5 uses flat enum — no WebAttribute. prefix)
        settings = self.view.settings()
        settings.setAttribute(
            QWebEngineSettings.LocalContentCanAccessRemoteUrls, True
        )
        settings.setAttribute(
            QWebEngineSettings.JavascriptEnabled, True
        )
        settings.setAttribute(
            QWebEngineSettings.LocalStorageEnabled, True
        )

        # Dark background while the page loads (no white flash)
        self.view.page().setBackgroundColor(QColor("#0D0D0D"))

        # Bridge
        self.channel = QWebChannel(self.view.page())
        self.bridge  = SensiBridge(self.view, ctx)
        self.channel.registerObject("bridge", self.bridge)
        self.view.page().setWebChannel(self.channel)

        # Hard reload shortcut — Ctrl+Shift+R bypasses cache completely
        # Use this instead of F5 after making CSS/HTML changes
        _reload = QShortcut(QKeySequence("Ctrl+Shift+R"), self)
        _reload.activated.connect(
            lambda: self.view.page().triggerAction(QWebEnginePage.ReloadAndBypassCache)
        )

        # Load UI
        self.view.load(QUrl.fromLocalFile(str(_UI_PATH)))


# ═══════════════════════════════════════════════════════════════════════════════
# Entry point
# ═══════════════════════════════════════════════════════════════════════════════

def main():
    print("[sensi] Bootstrapping backend…")
    ctx = bootstrap()
    print("[sensi] Backend ready — launching UI.")

    app = QApplication(sys.argv)
    app.setApplicationName("Sensi")
    app.setOrganizationName("AIA26 Team 02")

    window = SensiWindow(ctx)
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
