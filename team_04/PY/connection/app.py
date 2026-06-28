"""Connection FastAPI app — the HTTP bridge frontend2 talks to.

Run from team_04/PY:
    uvicorn connection.app:app --reload --port 8001

Serves frontend2 at / (same-origin), so frontend2/core/config.js can use
AGENT_BASE = "" if you load the UI from this server. It also enables permissive
CORS, so frontend2 served from elsewhere can still call these routes cross-origin.

Routes (the notebook-validated contract):
  /sessions ...           — create/list/delete + state + messages
  /sessions/{id}/chat     — SSE streaming chat with the REAL agent
  /sessions/{id}/decisions — decision graph {nodes, edges, head} + select
  /sessions/{id}/explorer — site + buildings + wings + placement options
  /site/...               — geocode proxy + boundary analysis/buildable-zone
  /sessions/{id}/site/boundary — persist a confirmed boundary onto AgentState
  /export/{id}/...        — geojson/json export of the real session geometry
  /tools                  — direct agent.tools.* invocation
"""
from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

# Side-effect import puts team_04/ on sys.path so agent.* resolves.
from . import _TEAM_ROOT  # noqa: F401
from .routers import chat, decisions, explorer, export, sessions, site, tools

# New /api/* routes — thin wrappers over the shared connection.notebook_logic
# runtime modules (the same implementation the notebooks use).
from .routes import (
    agent_routes,
    building_transform_routes,
    constraints_routes,
    context_routes,
    decision_graph_routes,
    decision_history_routes,
    design_options_routes,
    env_mode_routes,
    feedback_routes,
    generate_options_routes,
    geometry_routes,
    optimization_engine_routes,
    optimization_routes,
    reason_routes,
    session_optimize_routes,
    shape_selection_routes,
    site_routes,
    validate_routes,
)
from .export import router as export_selected_router

FRONTEND_DIR = Path(__file__).resolve().parents[1] / "frontend2"

app = FastAPI(
    title="AIA26 Studio — Team 04 Connection API",
    description="HTTP bridge between frontend2 and the real agent (agent.graph / agent.tools).",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(sessions.router)
app.include_router(chat.router)
app.include_router(decisions.router)
app.include_router(explorer.router)
app.include_router(site.router)
app.include_router(export.router)
app.include_router(tools.router)

# /api/* runtime routes
app.include_router(site_routes.router)
app.include_router(geometry_routes.router)
app.include_router(agent_routes.router)
app.include_router(optimization_routes.router)
app.include_router(decision_graph_routes.router)
app.include_router(building_transform_routes.router)
app.include_router(session_optimize_routes.router)
app.include_router(optimization_engine_routes.router)
app.include_router(design_options_routes.router)
app.include_router(env_mode_routes.router)
app.include_router(decision_history_routes.router)
app.include_router(generate_options_routes.router)
app.include_router(shape_selection_routes.router)
app.include_router(context_routes.router)
app.include_router(feedback_routes.router)
app.include_router(constraints_routes.router)
app.include_router(reason_routes.router)
app.include_router(validate_routes.router)
app.include_router(export_selected_router.router)


@app.get("/health", tags=["health"])
async def health() -> dict:
    # Report whether the agent runtime can actually be built (env configured).
    from .agent_runtime import is_ready

    return {"status": "ok", "agent_ready": is_ready()}


# The browser caches ES modules aggressively. During development that means edits
# to frontend2/*.js silently don't take effect — and worse, a query-string cache
# bust on boot.js does NOT cascade: the browser resolves a relative `import
# "./panels/explorer.js"` to the bare path (dropping ?v=), so it re-uses the OLD
# cached sub-module. The robust fix is to (a) send no-store, and (b) for every
# served .js module, REWRITE its own relative import specifiers to carry a fresh
# version token. Then boot.js?v=T imports ./explorer.js?v=T imports ./store.js?v=T …
# and the entire graph is forced fresh. This makes plain reloads pick up edits.
import re as _re
import time as _time

_START_TOKEN = str(int(_time.time() * 1000))  # changes every server start
# matches:  from "./x.js"   from '../x.js'   import("./x.js")
_IMPORT_RE = _re.compile(r'(\bfrom\s+|\bimport\s*\(\s*)(["\'])(\.{1,2}/[^"\']+?)(["\'])')


def _stamp_module(text: str, token: str) -> str:
    def repl(m: "_re.Match") -> str:
        spec = m.group(3)
        if "?" in spec:  # already has a query — leave it
            return m.group(0)
        return f"{m.group(1)}{m.group(2)}{spec}?v={token}{m.group(4)}"

    return _IMPORT_RE.sub(repl, text)


@app.middleware("http")
async def _no_cache_static(request, call_next):
    response = await call_next(request)
    path = request.url.path
    if path == "/" or path.startswith("/static/"):
        response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
    return response


# Serve frontend2 statically so the UI can run same-origin off this server.
if FRONTEND_DIR.exists():
    from fastapi import Request
    from fastapi.responses import PlainTextResponse, Response

    # JS modules are served through this route (BEFORE the static mount) so their
    # relative imports get version-stamped — this is what actually busts the cache
    # for the whole module graph. ?v= on the request wins; else the server token.
    @app.get("/static/{file_path:path}", include_in_schema=False)
    async def _static_js_aware(file_path: str, request: Request):
        target = (FRONTEND_DIR / file_path).resolve()
        # Path-traversal guard: must stay inside FRONTEND_DIR.
        if not str(target).startswith(str(FRONTEND_DIR.resolve())) or not target.is_file():
            return Response(status_code=404)
        no_cache = {
            "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
            "Pragma": "no-cache",
        }
        if target.suffix == ".js":
            token = request.query_params.get("v") or _START_TOKEN
            body = _stamp_module(target.read_text(encoding="utf-8"), token)
            return PlainTextResponse(
                body, media_type="application/javascript", headers=no_cache
            )
        # Non-JS (css/json/png/…) served as-is via FileResponse.
        return FileResponse(str(target), headers=no_cache)

    @app.get("/", include_in_schema=False)
    async def index():
        # Stamp boot.js + CSS with a fresh per-load token. boot.js?v=T is fetched
        # fresh, and the JS route above rewrites ITS imports to ./x.js?v=T, so the
        # whole module graph re-downloads. Plain reloads now pick up edits.
        import time

        from fastapi.responses import HTMLResponse

        html = (FRONTEND_DIR / "index.html").read_text(encoding="utf-8")
        token = str(int(time.time() * 1000))
        html = html.replace("/static/boot.js", f"/static/boot.js?v={token}")
        # Stamp local CSS links too (third-party CDN hrefs are left untouched).
        html = _re.sub(r'(href="/static/styles/[^"]+?\.css)"', rf'\1?v={token}"', html)
        return HTMLResponse(
            html,
            headers={"Cache-Control": "no-store, no-cache, must-revalidate, max-age=0", "Pragma": "no-cache"},
        )
else:
    @app.get("/", tags=["health"])
    async def root() -> dict:
        return {"status": "ok", "service": "AIA26 Studio Team 04 Connection", "docs": "/docs"}
