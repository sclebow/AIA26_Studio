# Sensi

A comfort-analysis copilot for architectural layouts. A **LangGraph** agent reads a
parametric layout (rooms as JSON rectangles), scores sensorial comfort, detects
conflicts, and suggests/edits changes. A **FastAPI** backend exposes the agent and
also serves the **React + Vite** frontend (chat, analysis panel with bars / radar /
2D plan / 3D, and the persona screens).

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

## 2. Install + build — one time (or after pulling new code)

```powershell
pip install -r team_02\python\requirements.txt
cd team_02\web
npm install
npm run build
cd ..\..
```

`npm run build` compiles the frontend into `team_02\web\dist`, which the backend
serves directly — so you never need a second terminal for Vite.

## 3. Run the app — single terminal

From the `AIA26_Studio\` root:

```powershell
uvicorn api.server:app --app-dir team_02\python --port 8000
```

Then open **http://localhost:8000**. The whole app — chat, analysis panel, 3D — is
served from this one process. Press `Ctrl+C` to stop.

> **If you change frontend code** (anything in `team_02\web\src`), re-run
> `npm run build` to see it. The Python backend you can just restart.

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

## Developing the frontend (optional two-terminal mode)

Only needed if you're actively editing `web/src` and want instant live-reload
instead of rebuilding each time. Terminal 1 runs the backend
(`uvicorn api.server:app --app-dir team_02\python --port 8000`); terminal 2 runs
`cd team_02\web; npm run dev` and you open **http://localhost:5173**, which proxies
`/api` calls to the backend.
