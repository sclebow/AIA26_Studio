from __future__ import annotations

import os

import uvicorn


if __name__ == "__main__":
    # Host/port overridable via env so a stuck port never blocks a run
    # (e.g. PORT=8001 python main.py).
    host = os.environ.get("HOST", "127.0.0.1")
    port = int(os.environ.get("PORT", "8000"))
    uvicorn.run("backend.main:app", host=host, port=port, reload=False)
