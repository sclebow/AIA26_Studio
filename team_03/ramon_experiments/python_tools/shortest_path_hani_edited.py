import json
import math
from collections import deque

def build_graph(layout):
    graph = {}
    for room in layout["rooms"]:
        graph[room["id"]] = []
    for door in layout["doors"]:
        r1, r2 = door["connects"]
        graph[r1].append({"room": r2, "door": door["id"], "position": door["position"]})
        graph[r2].append({"room": r1, "door": door["id"], "position": door["position"]})
    return graph

def get_room_id(layout, name):
    for room in layout["rooms"]:
        if room["name"] == name:
            return room["id"]
    return None

def get_room_name(layout, room_id):
    for room in layout["rooms"]:
        if room["id"] == room_id:
            return room["name"]
    return room_id

def bfs_shortest_paths(graph, start_id):
    distances = {start_id: 0}
    doors_used = {start_id: []}
    queue = deque([start_id])
    while queue:
        current = queue.popleft()
        for neighbor in graph[current]:
            nid = neighbor["room"]
            if nid not in distances:
                distances[nid] = distances[current] + 1
                doors_used[nid] = doors_used[current] + [neighbor["door"]]
                queue.append(nid)
    return distances, doors_used

def door_position_score(layout, graph, start_id, distances):
    door_scores = {}
    for door in layout["doors"]:
        r1, r2 = door["connects"]
        d1 = distances.get(r1, 999)
        d2 = distances.get(r2, 999)
        far_room = r2 if d1 < d2 else r1
        near_room = r1 if d1 < d2 else r2
        alt_connections = [n for n in graph[near_room] if n["room"] != far_room]
        if alt_connections:
            avg_x = sum(n["position"][0] for n in alt_connections) / len(alt_connections)
            avg_y = sum(n["position"][1] for n in alt_connections) / len(alt_connections)
            dx = door["position"][0] - avg_x
            dy = door["position"][1] - avg_y
            deviation = math.sqrt(dx**2 + dy**2)
        else:
            deviation = 0
        if deviation < 1.0:
            score = 1
            label = "optimal"
            advice = "Door position is well placed."
        elif deviation < 2.5:
            score = 2
            label = "minor issue"
            advice = "Consider shifting {} closer to the main circulation center.".format(door["id"])
        else:
            score = 3
            label = "bottleneck"
            advice = "Door {} is far from the main path - shifting it could shorten access.".format(door["id"])
        door_scores[door["id"]] = {
            "door_id": door["id"],
            "connects": door["connects"],
            "position": door["position"],
            "deviation": round(deviation, 2),
            "score": score,
            "label": label,
            "advice": advice
        }
    return door_scores

# ── MAIN (runs in GH context) ──────────────────────────────────────────────
try:
    layout = json.loads(json_str)
    graph = build_graph(layout)
    start_id = get_room_id(layout, start_room)

    if not start_id:
        a = json.dumps({"error": "Room '{}' not found.".format(start_room)})
    else:
        distances, doors_used = bfs_shortest_paths(graph, start_id)
        door_scores = door_position_score(layout, graph, start_id, distances)

        rooms_result = []
        for room_id, depth in distances.items():
            rooms_result.append({
                "room": get_room_name(layout, room_id),
                "depth_from_entry": depth,
                "path_doors": doors_used[room_id]
            })

        doors_result = []
        for did, data in door_scores.items():
            doors_result.append({
                "door_id": data["door_id"],
                "connects": [
                    get_room_name(layout, data["connects"][0]),
                    get_room_name(layout, data["connects"][1])
                ],
                "position": data["position"],
                "deviation": data["deviation"],
                "score": data["score"],
                "label": data["label"],
                "advice": data["advice"]
            })

        a = json.dumps({
            "start_room": start_room,
            "rooms": rooms_result,
            "door_scores": doors_result
        }, indent=2)

except Exception as e:
    a = json.dumps({"error": str(e)})
