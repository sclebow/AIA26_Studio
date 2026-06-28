"""Throwaway smoke test for the connection layer (no LLM required).

Run from team_04/PY:  python -m connection._smoke_test
Exercises: health, tools, session create, decisions (grow+select), explorer.
"""
from __future__ import annotations

import asyncio

from fastapi.testclient import TestClient

from connection.app import app
from connection.decision_graph import make_branch_nodes, make_intent_node
from connection.session_store import store

c = TestClient(app)

print("HEALTH:", c.get("/health").json())
print("TOOLS:", c.get("/tools").json())

site = [[0, 0], [40, 0], [40, 30], [0, 30], [0, 0]]
r = c.post(
    "/sessions",
    json={
        "layout_payload": {"user_prompt": "Place one building", "site_boundary": site},
        "max_optimization_cycles": 4,
    },
)
print("CREATE:", r.status_code, r.json())
sid = r.json()["session_id"]

print("LIST:", c.get("/sessions").json())
print("DECISIONS (empty):", c.get(f"/sessions/{sid}/decisions").json())
print("EXPLORER:", c.get(f"/sessions/{sid}/explorer").json())
print("SITE:", c.get(f"/sessions/{sid}/site").json())
print("STATE keys:", sorted(c.get(f"/sessions/{sid}/state").json().keys())[:8])


async def grow() -> str:
    g = await store.get_graph(sid)
    iid = make_intent_node(g, "optimize")
    bid = make_branch_nodes(
        g,
        iid,
        [
            {"rank": 1, "combined_score": 0.9, "boundary": site},
            {"rank": 2, "combined_score": 0.8, "boundary": site},
        ],
    )
    await store.save_graph(sid, g)
    return g.children_of(bid)[0]["node_id"]


child = asyncio.new_event_loop().run_until_complete(grow())
sel = c.post(f"/sessions/{sid}/decisions/{child}/select", json={"reason": "test"}).json()
print("SELECT ok, selected:", sel["selected_node_id"][:8], "head:", sel["graph_head"][:8])

dg = c.get(f"/sessions/{sid}/decisions").json()
print("GRAPH after select: nodes=", len(dg["nodes"]), "edges=", len(dg["edges"]), "head_set=", bool(dg["head"]))
print("ALL OK")
