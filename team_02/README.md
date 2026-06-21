# Sensi

A comfort-analysis copilot for architectural layouts. A **LangGraph** agent reads a
parametric layout (rooms as JSON rectangles), scores sensorial comfort, detects
conflicts, and suggests/edits changes. A **FastAPI** backend exposes the agent and
also serves the **React + Vite** frontend (chat, analysis panel with bars / radar /
2D plan / 3D, and the persona screens).

> **Concept / vision:** the overall number isn't a grade to inflate, it's the weakest
> teacher in the system — the real lesson lives in the edges: *how a change to one sense
> ripples to another*. See [`docs/concept-the-ripple.md`](docs/concept-the-ripple.md).

```
team_02/
├── python/            # FastAPI backend + LangGraph agent
│   ├── api/           # server.py (HTTP + SSE), contracts.py
│   ├── comfort/       # the 3 pure-Python comfort tools (no Rhino)
│   ├── inspire/       # persona / "inspire" pipeline
│   ├── nodes/         # graph nodes (analysis + tools)
│   ├── _runtime/      # config, llm factory, local tool client
│   └── requirements.txt
├── web/               # React + Vite frontend (built into web/dist)
└── Dockerfile         # one-container deploy (builds web, serves via FastAPI)
```

## Prerequisites

- **Python 3.11+** (these steps assume your virtualenv is already active)
- **Node.js 20+** (includes npm) — used once to build the frontend
- An LLM provider. The easiest free option is **Cloudflare Workers AI** (no credit
  card); local models via LM Studio / Ollama also work.

> All commands below are written for **Windows PowerShell**, run from the
> `AIA26_Studio\` repo root (the folder that contains `team_02\` and `.env`).

## 1. Configure your environment (.env) — one time

Settings load from a single `.env` file at the **`AIA26_Studio\` repo root** (the
folder you're already in). Copy the example and fill it in:

```powershell
copy .env.example .env
```

Set `LLM_PROVIDER` to one of `cloudflare`, `openai`, `google`, or `local`, then fill
in the matching keys. Example for Cloudflare:

```env
LLM_PROVIDER = "cloudflare"
CF_ACCOUNT_ID = "your_cloudflare_account_id"
CF_API_TOKEN  = "your_cloudflare_api_token"
CF_MODEL      = "@cf/qwen/qwen3-30b-a3b-fp8"
```

> All providers are called through one OpenAI-compatible client, so you only need
> the keys for the provider you actually select.

### Benchmarking — per-node model tiers (optional)

Nodes can run on different models: a small/cheap model for routing and short text,
a larger one for user-facing prose and reasoning. Set these alongside your provider
keys (they fall back to the base model if unset):

```env
GOOGLE_MODEL_FAST  = "gemini-2.5-flash-lite"   # routing / classification / short text
GOOGLE_MODEL_SMART = "gemini-2.5-flash"        # user-facing prose & nuanced reasoning
```

The same pattern works for any provider (`OPENAI_MODEL_FAST`, etc.). Full rationale
and the node→tier mapping: [docs/week08/benchmarking-findings.md](docs/week08/benchmarking-findings.md).

### Headless CLI (orchestrator subprocess)

Run a single turn non-interactively and get a machine-readable result:

```powershell
python main.py --prompt "add a window to the south wall of the living room" --layout_json '{ ...layout... }'
```

No flags → the normal interactive session. Details: [docs/week08/cli-changes.md](docs/week08/cli-changes.md).

## 2. Install + build — one time (or after pulling new code)

```powershell
pip install -r team_02\python\requirements.txt
cd team_02\web
npm install
npm run build
cd ..\..
```

`npm run build` compiles the frontend into `team_02\web\dist`, which the backend
serves directly. You need this for the **single-process** mode (step 4) and must
re-run it after every frontend change there. For **development** (step 3) you don't
need to build at all — Vite serves `web/src` live.

## 3. Run the app — two terminals (development)

Use this mode while editing the frontend: Vite hot-reloads on every save, so you
never rebuild. Both commands run from the `AIA26_Studio\` root.

**Terminal 1 — backend (FastAPI on :8000):**

```powershell
uvicorn api.server:app --app-dir team_02\python --reload --port 8000
```

**Terminal 2 — frontend (Vite dev server on :5173):**

```powershell
cd team_02\web
npm run dev
```

Then open **http://localhost:5173** — *not* 8000. Vite serves `web/src` directly and
proxies `/api` calls to the backend, so it behaves as one app. Anything you change in
`web/src` shows up on save; restart uvicorn only if you change Python. Press `Ctrl+C`
in each terminal to stop.

## 4. Run as one process (preview / share)

When you're **not** editing — to preview the built app or hand someone a single link —
build the frontend once and let the backend serve it:

```powershell
cd team_02\web; npm run build; cd ..\..
uvicorn api.server:app --app-dir team_02\python --port 8000
```

Then open **http://localhost:8000**. Re-run `npm run build` after any frontend change
to refresh what's served here.

## Docker (single shareable container)

```powershell
cd team_02
docker build -t sensi .
docker run --env-file ..\.env -p 8000:8000 sensi
```

App is served at **http://localhost:8000**. The image builds the frontend and runs
the FastAPI backend that serves it.

## Troubleshooting

- **`Missing or empty required environment variable`** — your `.env` is missing a key
  for the selected `LLM_PROVIDER`, or `.env` isn't at the `AIA26_Studio\` root.
- **Blank page / 404 at `:8000`** — the frontend isn't built yet. Run
  `npm run build` in `team_02\web` (step 2).
- **Frontend loads but chat does nothing** — check the terminal running uvicorn for
  errors (usually a bad/missing API key in `.env`).
- **Port already in use** — change `--port 8000` to another port and use that in the
  URL.
- **Editing the frontend but changes don't show?** You're probably on **:8000**
  (built mode). Use the two-terminal dev flow (step 3) and open **:5173** for live
  reload, or re-run `npm run build`.
