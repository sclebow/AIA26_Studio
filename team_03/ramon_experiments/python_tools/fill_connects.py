import json
import math

def min_dist_to_polygon(point, polygon):
    x, y = point
    min_dist = float('inf')
    n = len(polygon)
    for i in range(n):
        x1, y1 = polygon[i]
        x2, y2 = polygon[(i + 1) % n]
        dx, dy = x2 - x1, y2 - y1
        length = math.sqrt(dx**2 + dy**2)
        if length == 0:
            continue
        t = max(0, min(1, ((x - x1) * dx + (y - y1) * dy) / (length**2)))
        px, py = x1 + t * dx, y1 + t * dy
        dist = math.sqrt((x - px)**2 + (y - py)**2)
        min_dist = min(min_dist, dist)
    return min_dist

with open("layout_schema.json", encoding="utf-8") as f:
    layout = json.load(f)

for door in layout["doors"]:
    pos = door["position"]
    distances = []
    for room in layout["rooms"]:
        dist = min_dist_to_polygon(pos, room["geometry"])
        distances.append((dist, room["id"]))
    distances.sort()
    top2 = [rid for dist, rid in distances[:2] if dist < 1.0]
    door["connects"] = top2
    print(f"{door['id']}: {top2} (distances: {[round(d,3) for d,_ in distances[:3]]})")

with open("layout_schema.json", "w", encoding="utf-8") as f:
    json.dump(layout, f, indent=2)

print("Done!")
