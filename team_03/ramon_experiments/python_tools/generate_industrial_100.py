#!/usr/bin/env python3
"""Generate 100 unique industrial warehouse layouts with full variation."""

import json, random, os, math

random.seed(2026)

OUTPUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "industrial_100")
os.makedirs(OUTPUT, exist_ok=True)

# ── Name pools ──────────────────────────────────────────────────────────────
OFFICE = ["Office", "Manager Office", "Supervisor Office", "Admin Office",
          "Engineering Office", "Sales Office", "HR Office", "Accounting Office",
          "Planning Office", "Quality Office", "Dispatch Office", "Foreman Office"]
RESTROOM = ["Restroom", "WC", "Bathroom", "Lavatory", "Washroom", "Staff WC"]
STORAGE = ["Storage Room", "Tool Room", "Parts Storage", "Supply Room",
           "Inventory Room", "Spare Parts Room", "Chemical Storage"]
BREAK_RM = ["Break Room", "Cafeteria", "Lunch Room", "Rest Area",
            "Staff Lounge", "Kitchenette", "Canteen"]
RECEPTION = ["Reception", "Lobby", "Front Office", "Entrance Hall",
             "Visitor Area", "Security Booth", "Guard Room"]
MEETING = ["Meeting Room", "Conference Room", "Board Room", "Training Room",
           "Briefing Room", "War Room"]
UTILITY = ["Utility Room", "Electrical Room", "Server Room",
           "Mechanical Room", "Compressor Room", "Generator Room"]
WAREHOUSE = [
    "Main Warehouse", "Production Floor", "Assembly Hall", "Workshop",
    "Manufacturing Area", "Loading Bay", "Shipping Area", "Receiving Area",
    "Fabrication Hall", "Processing Floor", "Distribution Floor",
    "Packaging Area", "Inspection Hall", "Testing Floor", "Staging Area",
    "Welding Shop", "Paint Shop", "Clean Room", "Cold Storage Floor",
]

# ── Room furniture templates: (name, width, depth) ─────────────────────────
ROOM_FURN = {
    "office":    [("Desk", 1.2, 0.6), ("Office Chair", 0.5, 0.5),
                  ("Filing Cabinet", 0.8, 0.45)],
    "restroom":  [("Toilet", 0.4, 0.65), ("Sink", 0.6, 0.45)],
    "storage":   [("Storage Shelf", 1.8, 0.6)],
    "break":     [("Table", 1.2, 0.8), ("Chair", 0.5, 0.5),
                  ("Microwave Stand", 0.6, 0.45)],
    "reception": [("Reception Desk", 1.8, 0.7), ("Visitor Chair", 0.5, 0.5)],
    "meeting":   [("Conference Table", 2.0, 1.0), ("Meeting Chair", 0.5, 0.5)],
    "utility":   [("Equipment Rack", 0.6, 0.8)],
}

NAME_POOL = {
    "office": OFFICE, "restroom": RESTROOM, "storage": STORAGE,
    "break": BREAK_RM, "reception": RECEPTION, "meeting": MEETING,
    "utility": UTILITY,
}

# ── Warehouse furniture categories ─────────────────────────────────────────
WH_FURN = {
    "storage_racks": [
        ("Heavy Duty Rack", 5.0, 1.2), ("Pallet Rack", 4.0, 1.0),
        ("Medium Shelf Unit", 3.0, 0.8), ("Cantilever Rack", 4.0, 1.5),
        ("Small Shelving", 2.0, 0.6), ("Wire Rack", 2.5, 0.8),
    ],
    "heavy_machinery": [
        ("CNC Machine", 3.0, 2.5), ("Hydraulic Press", 2.5, 2.0),
        ("Industrial Lathe", 3.5, 1.5), ("Milling Machine", 2.5, 2.0),
        ("Welding Station", 2.0, 1.5), ("Band Saw", 1.5, 1.5),
        ("Drill Press", 1.0, 1.0), ("Grinding Machine", 1.5, 1.2),
    ],
    "forklifts_pallets": [
        ("Forklift Parking Bay", 3.0, 4.0), ("Pallet Stack", 1.2, 1.0),
        ("Loading Platform", 5.0, 2.5), ("Pallet Jack Station", 2.0, 1.0),
        ("Cargo Zone", 6.0, 2.5), ("Shrink Wrap Station", 2.0, 1.5),
    ],
    "workbenches": [
        ("Workbench", 2.0, 0.8), ("Tool Cabinet", 1.0, 0.6),
        ("Assembly Table", 2.5, 1.2), ("Inspection Table", 2.0, 1.0),
        ("Soldering Station", 1.5, 0.8), ("Vise Table", 1.5, 0.8),
    ],
    "desks_floor": [
        ("Standing Desk", 1.5, 0.7), ("Computer Workstation", 1.4, 0.7),
        ("Drafting Table", 1.8, 1.0), ("Filing Cabinet Row", 2.0, 0.5),
        ("Plotter Station", 1.5, 0.8), ("Monitor Stand", 1.2, 0.5),
    ],
    "assembly_line": [
        ("Conveyor Section", 6.0, 0.8), ("Assembly Station", 2.0, 1.5),
        ("Parts Bin Rack", 1.5, 0.8), ("QC Table", 2.0, 1.0),
        ("Packaging Station", 2.5, 1.5), ("Labeling Station", 1.5, 0.8),
    ],
}

R2 = lambda x: round(x, 2)


def snap(v, step=0.5):
    return round(v / step) * step


class Gen:
    """Generates one industrial layout."""

    def __init__(self, idx):
        self.idx = idx
        self.W = snap(random.uniform(10, 20))       # width  (y axis)
        self.L = round(random.uniform(40, 70))       # length (x axis)
        self._n = {"room": 0, "door": 0, "window": 0, "furn": 0, "mep": 0, "wall": 0}
        self.rooms = []; self.doors = []; self.windows = []
        self.furniture = []; self.mep = []; self.structure = []
        self.small = []          # metadata for side rooms
        self.wh_id = None
        self.wh_safe = None      # (x0, y0, x1, y1) safe rect for wh furniture

    def nid(self, kind):
        self._n[kind] += 1
        return f"{kind}-{self._n[kind]}"

    # ── public ──────────────────────────────────────────────────────────────
    def run(self):
        outline = [[0,0],[self.L,0],[self.L,self.W],[0,self.W],[0,0]]
        self._layout_rooms()
        self._ext_doors()
        self._windows()
        self._mep()
        self._walls()
        return {
            "layoutId": f"Layout-IND-{self.idx+1:03d}",
            "outline": outline,
            "rooms": self.rooms, "doors": self.doors,
            "windows": self.windows, "furniture": self.furniture,
            "mep": self.mep, "structure": self.structure,
        }

    # ── rooms ───────────────────────────────────────────────────────────────
    def _layout_rooms(self):
        L, W = self.L, self.W
        pat = random.choices(
            ["back", "back", "back", "front_back", "partial_bot",
             "partial_top", "front", "minimal"],
            weights=[3, 3, 3, 2, 2, 2, 1, 1], k=1)[0]

        d_back = snap(random.uniform(4, min(8, L * 0.15)))
        d_front = snap(random.uniform(4, min(8, L * 0.15)))

        back = []; front = []

        # ---- choose room types for each end ----
        def pick_types(n, with_rec=False):
            pool = ["office","restroom","storage","break","meeting","utility"]
            ts = []
            if n >= 2: ts.append("restroom")
            if with_rec: ts.insert(0, "reception")
            while len(ts) < n:
                ts.append(random.choice(pool))
            return ts[:n]

        def end_rooms(x0, x1, n, types, y0=0, y1=None):
            if y1 is None: y1 = W
            h = (y1 - y0) / n
            out = []
            for i in range(n):
                ys = R2(y0 + i * h); ye = R2(y0 + (i+1) * h)
                if i == n - 1: ye = y1
                rid = self.nid("room")
                tp = types[i]
                nm = random.choice(NAME_POOL[tp])
                # avoid duplicate names
                used = [r["name"] for r in out]
                if nm in used: nm += f" {i+1}"
                g = [[x0,ys],[x1,ys],[x1,ye],[x0,ye],[x0,ys]]
                a = R2(abs(x1-x0)*(ye-ys))
                out.append({"id":rid,"name":nm,"type":tp,
                            "x0":min(x0,x1),"x1":max(x0,x1),
                            "y0":ys,"y1":ye,"geom":g,"area":a})
            return out

        # ---- generate rooms per pattern ----
        if pat == "back":
            n = random.randint(2, min(5, max(2, int(W/2.5))))
            back = end_rooms(L-d_back, L, n, pick_types(n))
            wg = [[0,0],[L-d_back,0],[L-d_back,W],[0,W],[0,0]]
            wa = R2((L-d_back)*W)
            self.wh_safe = (0, 0, L-d_back, W)

        elif pat == "front_back":
            nb = random.randint(2, min(4, max(2, int(W/3))))
            nf = random.randint(1, min(3, max(1, int(W/3))))
            back = end_rooms(L-d_back, L, nb, pick_types(nb))
            front = end_rooms(0, d_front, nf, pick_types(nf, True))
            wg = [[d_front,0],[L-d_back,0],[L-d_back,W],[d_front,W],[d_front,0]]
            wa = R2((L-d_back-d_front)*W)
            self.wh_safe = (d_front, 0, L-d_back, W)

        elif pat == "partial_bot":
            n = random.randint(1, 3)
            ph = snap(W * random.uniform(0.3, 0.6))
            back = end_rooms(L-d_back, L, n, pick_types(n), 0, ph)
            wg = [[0,0],[L-d_back,0],[L-d_back,ph],[L,ph],[L,W],[0,W],[0,0]]
            wa = R2(L*W - d_back*ph)
            self.wh_safe = (0, 0, L-d_back, W)

        elif pat == "partial_top":
            n = random.randint(1, 3)
            ph = snap(W * random.uniform(0.3, 0.6))
            ys = R2(W - ph)
            back = end_rooms(L-d_back, L, n, pick_types(n), ys, W)
            wg = [[0,0],[L,0],[L,ys],[L-d_back,ys],[L-d_back,W],[0,W],[0,0]]
            wa = R2(L*W - d_back*ph)
            self.wh_safe = (0, 0, L-d_back, W)

        elif pat == "front":
            n = random.randint(1, 3)
            front = end_rooms(0, d_front, n, pick_types(n, True))
            wg = [[d_front,0],[L,0],[L,W],[d_front,W],[d_front,0]]
            wa = R2((L-d_front)*W)
            self.wh_safe = (d_front, 0, L, W)

        elif pat == "minimal":
            rh = snap(min(3, W*0.3)); rd = snap(min(3, d_back))
            rid = self.nid("room")
            back = [{"id":rid,"name":random.choice(RESTROOM),"type":"restroom",
                     "x0":L-rd,"x1":L,"y0":0,"y1":rh,
                     "geom":[[L-rd,0],[L,0],[L,rh],[L-rd,rh],[L-rd,0]],
                     "area":R2(rd*rh)}]
            wg = [[0,0],[L-rd,0],[L-rd,rh],[L,rh],[L,W],[0,W],[0,0]]
            wa = R2(L*W - rd*rh)
            self.wh_safe = (0, 0, L-rd, W)

        # ---- register small rooms ----
        self.small = back + front
        for r in self.small:
            self.rooms.append({"id":r["id"],"name":r["name"],
                               "geometry":r["geom"],
                               "attributes":{"area":r["area"]}})
            self._room_furn(r)

        # ---- warehouse room ----
        wh_id = self.nid("room")
        self.wh_id = wh_id
        self.rooms.append({"id":wh_id,"name":random.choice(WAREHOUSE),
                           "geometry":wg,"attributes":{"area":wa}})
        self._wh_furn(wh_id)

        # ---- inter-room doors (room ↔ warehouse) ----
        for r in self.small:
            self._room_door(r, wh_id)

    # ── room furniture ──────────────────────────────────────────────────────
    def _room_furn(self, r):
        templates = ROOM_FURN.get(r["type"], [])
        cx, cy = r["x0"] + 0.3, r["y0"] + 0.3
        for name, fw, fh in templates:
            if cx + fw > r["x1"] - 0.2:
                cx = r["x0"] + 0.3; cy += fh + 0.4
            if cy + fh > r["y1"] - 0.2:
                break
            fid = self.nid("furn")
            self.furniture.append({
                "id":fid,"name":name,
                "geometry":[[R2(cx),R2(cy)],[R2(cx+fw),R2(cy)],
                            [R2(cx+fw),R2(cy+fh)],[R2(cx),R2(cy+fh)],
                            [R2(cx),R2(cy)]],
                "attributes":{"roomId":r["id"]}})
            cx += fw + 0.4

    # ── warehouse furniture ─────────────────────────────────────────────────
    def _wh_furn(self, wh_id):
        cat = random.choice(list(WH_FURN.keys()))
        items = WH_FURN[cat]
        n = random.randint(4, 12)
        sx0, sy0, sx1, sy1 = self.wh_safe
        mg = 2.0
        placed = []
        for i in range(n):
            name, fw, fh = random.choice(items)
            for _ in range(30):
                fx = R2(random.uniform(sx0+mg, sx1-mg-fw))
                fy = R2(random.uniform(sy0+mg, sy1-mg-fh))
                ok = all(fx+fw+0.6<px or px+pw+0.6<fx or
                         fy+fh+0.6<py or py+ph+0.6<fy
                         for px,py,pw,ph in placed)
                if ok: break
            else:
                continue
            fid = self.nid("furn")
            self.furniture.append({
                "id":fid,"name":f"{name} {i+1}",
                "geometry":[[fx,fy],[R2(fx+fw),fy],[R2(fx+fw),R2(fy+fh)],
                            [fx,R2(fy+fh)],[fx,fy]],
                "attributes":{"roomId":wh_id}})
            placed.append((fx,fy,fw,fh))

    # ── room ↔ warehouse door ──────────────────────────────────────────────
    def _room_door(self, r, wh_id):
        did = self.nid("door")
        # shared wall is at x = r["x0"] or r["x1"], whichever is interior
        x0, x1 = r["x0"], r["x1"]
        xw = x0 if 0 < x0 < self.L else x1
        mid_y = R2((r["y0"]+r["y1"])/2 - 0.45)
        self.doors.append({
            "id":did,
            "type":random.choice(["wooden","wooden","fire","sliding"]),
            "name":f"{r['name']} Door",
            "geometry":[[xw, mid_y],[xw, R2(mid_y+0.9)]],
            "attributes":{"connectsRooms":[r["id"], wh_id]}})

    # ── exterior doors ──────────────────────────────────────────────────────
    def _ext_doors(self):
        L, W = self.L, self.W
        wh = self.wh_id
        has_front = any(r["x0"]==0 for r in self.small)

        # main entrance
        did = self.nid("door")
        if has_front:
            dx = R2(L*random.uniform(0.25,0.45))
            self.doors.append({"id":did,"type":"sliding","name":"Main Entrance",
                "geometry":[[dx,0],[R2(dx+2),0]],
                "attributes":{"connectsRooms":[wh,"exterior"]}})
        else:
            dy = R2(W/2-1)
            self.doors.append({"id":did,"type":"sliding","name":"Main Entrance",
                "geometry":[[0,dy],[0,R2(dy+2)]],
                "attributes":{"connectsRooms":[wh,"exterior"]}})

        # loading dock
        did = self.nid("door")
        dock = random.choice([3.0,3.5,4.0])
        side = random.choice(["south","north"])
        dx = R2(L*random.uniform(0.2,0.5))
        sx0 = self.wh_safe[0]
        dx = max(dx, sx0+1)
        y = 0 if side=="south" else W
        self.doors.append({"id":did,"type":"sliding","name":"Loading Dock",
            "geometry":[[dx,y],[R2(dx+dock),y]],
            "attributes":{"connectsRooms":[wh,"exterior"]}})

        # optional: reception exterior door
        for r in self.small:
            if r["type"]=="reception" and r["x0"]==0:
                did = self.nid("door")
                dy = R2((r["y0"]+r["y1"])/2-0.5)
                self.doors.append({"id":did,"type":"glass",
                    "name":f"{r['name']} Entrance",
                    "geometry":[[0,dy],[0,R2(dy+1)]],
                    "attributes":{"connectsRooms":[r["id"],"exterior"]}})

    # ── windows ─────────────────────────────────────────────────────────────
    def _windows(self):
        if random.random() > 0.7:           # 30% no windows
            return
        L, W = self.L, self.W
        sx0,_,sx1,_ = self.wh_safe
        n = random.randint(3, 8)

        for side_y in [0, W]:
            span = sx1 - sx0
            step = span / (n + 1)
            for i in range(n):
                wx = R2(sx0 + step*(i+1))
                if wx < sx0+0.5 or wx > sx1-1.5: continue
                wid = self.nid("window")
                self.windows.append({
                    "id":wid,
                    "type":random.choice(["fixed","sliding","awning"]),
                    "name":f"Warehouse Window {self._n['window']}",
                    "geometry":[[wx,side_y],[R2(wx+1),side_y]],
                    "attributes":{"roomId":self.wh_id}})

        for r in self.small:
            if r["type"] in ("restroom","utility","storage"):
                continue
            # exterior edge?
            if r["x1"]==L:
                wid = self.nid("window")
                wy = R2((r["y0"]+r["y1"])/2-0.5)
                self.windows.append({"id":wid,"type":"casement",
                    "name":f"{r['name']} Window",
                    "geometry":[[L,wy],[L,R2(wy+1)]],
                    "attributes":{"roomId":r["id"]}})
            if r["x0"]==0:
                wid = self.nid("window")
                wy = R2((r["y0"]+r["y1"])/2-0.5)
                self.windows.append({"id":wid,"type":"casement",
                    "name":f"{r['name']} Window",
                    "geometry":[[0,wy],[0,R2(wy+1)]],
                    "attributes":{"roomId":r["id"]}})
            if r["y0"]==0 and r["x1"]-r["x0"]>2:
                wid = self.nid("window")
                wx = R2((r["x0"]+r["x1"])/2-0.5)
                self.windows.append({"id":wid,"type":"casement",
                    "name":f"{r['name']} Window",
                    "geometry":[[wx,0],[R2(wx+1),0]],
                    "attributes":{"roomId":r["id"]}})
            if r["y1"]==W and r["x1"]-r["x0"]>2:
                wid = self.nid("window")
                wx = R2((r["x0"]+r["x1"])/2-0.5)
                self.windows.append({"id":wid,"type":"casement",
                    "name":f"{r['name']} Window",
                    "geometry":[[wx,W],[R2(wx+1),W]],
                    "attributes":{"roomId":r["id"]}})

    # ── MEP ─────────────────────────────────────────────────────────────────
    def _mep(self):
        L, W = self.L, self.W
        sx0 = self.wh_safe[0]

        # HVAC 1
        hx = R2(sx0 + 2)
        mid = self.nid("mep")
        self.mep.append({"id":mid,"name":"HVAC Unit 1",
            "geometry":[[hx,R2(W-0.5)],[R2(hx+0.8),R2(W-0.5)],
                        [R2(hx+0.8),R2(W-0.25)],[hx,R2(W-0.25)],
                        [hx,R2(W-0.5)]],
            "attributes":{"system":"hvac"}})

        if L > 50:
            mid = self.nid("mep")
            hx2 = R2(L*0.55)
            self.mep.append({"id":mid,"name":"HVAC Unit 2",
                "geometry":[[hx2,0.25],[R2(hx2+0.8),0.25],
                            [R2(hx2+0.8),0.5],[hx2,0.5],[hx2,0.25]],
                "attributes":{"system":"hvac"}})

        # electrical
        mid = self.nid("mep")
        ex = R2(sx0+0.5)
        self.mep.append({"id":mid,"name":"Main Electrical Panel",
            "geometry":[[ex,0.2],[R2(ex+0.6),0.2],[R2(ex+0.6),0.5],
                        [ex,0.5],[ex,0.2]],
            "attributes":{"system":"electrical"}})

        # plumbing near restrooms
        for r in self.small:
            if r["type"]=="restroom":
                mid = self.nid("mep")
                px = R2(r["x1"]-0.7); py = R2(r["y0"]+0.2)
                self.mep.append({"id":mid,"name":"Plumbing Riser",
                    "geometry":[[px,py],[R2(px+0.5),py],
                                [R2(px+0.5),R2(py+0.5)],[px,R2(py+0.5)],
                                [px,py]],
                    "attributes":{"system":"plumbing"}})

    # ── structure walls ─────────────────────────────────────────────────────
    def _walls(self):
        L, W = self.L, self.W

        # exterior
        for nm, g in [("South Exterior",[[0,0],[L,0]]),
                      ("East Exterior",[[L,0],[L,W]]),
                      ("North Exterior",[[0,W],[L,W]]),
                      ("West Exterior",[[0,0],[0,W]])]:
            wid = self.nid("wall")
            self.structure.append({"id":wid,"name":f"{nm} Wall",
                "geometry":g,
                "attributes":{"type":"load-bearing","material":"concrete"}})

        # interior walls (non-outline edges of small rooms)
        seen = set()
        for r in self.small:
            x0,x1,y0,y1 = r["x0"],r["x1"],r["y0"],r["y1"]
            edges = [((x0,y0),(x0,y1)),((x0,y1),(x1,y1)),
                     ((x1,y0),(x1,y1)),((x0,y0),(x1,y0))]
            for (ax,ay),(bx,by) in edges:
                if (ax==bx==0)or(ax==bx==L)or(ay==by==0)or(ay==by==W):
                    continue
                k=(min(ax,bx),min(ay,by),max(ax,bx),max(ay,by))
                if k in seen: continue
                seen.add(k)
                wid = self.nid("wall")
                self.structure.append({"id":wid,
                    "name":f"Interior Wall {self._n['wall']}",
                    "geometry":[[R2(ax),R2(ay)],[R2(bx),R2(by)]],
                    "attributes":{"type":"partition","material":"drywall"}})


# ── main ────────────────────────────────────────────────────────────────────
def main():
    for i in range(100):
        g = Gen(i)
        layout = g.run()
        path = os.path.join(OUTPUT, f"industrial_{i+1:03d}.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump(layout, f, indent=2, ensure_ascii=False)
    print(f"Done — 100 layouts written to {OUTPUT}")


if __name__ == "__main__":
    main()
