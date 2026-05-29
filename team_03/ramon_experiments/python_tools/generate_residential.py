#!/usr/bin/env python3
"""
Generate residential_100: house_001-008 (replacements) + house_021-100.
Run from any directory; uses absolute path to output folder.
"""
import json, os, random

random.seed(20260515)

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "residential_20")
os.makedirs(OUT, exist_ok=True)

# ── tiny helpers ──────────────────────────────────────────────────────────────
rn = lambda v: round(float(v), 1)
def close(pts):
    p = [[rn(x), rn(y)] for x,y in pts]
    if p[0] != p[-1]: p.append(p[0])
    return p
def R(x0,y0,x1,y1): return close([[x0,y0],[x1,y0],[x1,y1],[x0,y1]])
def A(x0,y0,x1,y1): return rn(abs((x1-x0)*(y1-y0)))
def seg(x0,y0,x1,y1): return [[rn(x0),rn(y0)],[rn(x1),rn(y1)]]

def room(rid,name,geom,ar):
    return {"id":f"room-{rid}","name":name,"geometry":geom,"attributes":{"area":ar}}
def door(did,dtype,name,g,r1,r2):
    r2s = r2 if isinstance(r2,str) else f"room-{r2}"
    return {"id":f"door-{did}","type":dtype,"name":name,"geometry":g,
            "attributes":{"connectsRooms":[f"room-{r1}",r2s]}}
def win(wid,wtype,name,g,rid):
    return {"id":f"window-{wid}","type":wtype,"name":name,"geometry":g,
            "attributes":{"roomId":f"room-{rid}"}}
def furn(fid,name,g,rid):
    return {"id":f"furn-{fid}","name":name,"geometry":g,
            "attributes":{"roomId":f"room-{rid}"}}
def mep(mid,name,g,sys):
    return {"id":f"mep-{mid}","name":name,"geometry":g,"attributes":{"system":sys}}
def wall(wid,name,g,wt="partition"):
    return {"id":f"wall-{wid}","name":name,"geometry":g,"attributes":{"type":wt}}

# ── Blueprint A: compact studio / 1-bed (80-110m²) ──────────────────────────
def gen_compact(idx, W=10.0, H=9.0):
    W,H = rn(W),rn(H)
    # Zones: south living+kitchen, north bedroom+bath, thin corridor
    kW = rn(W*0.45); lW = rn(W-kW)
    corH = 1.0; bedH = rn((H - corH)*0.5); batH = rn(H - corH - bedH)
    southH = rn(H - corH - bedH - batH) if batH+bedH+corH < H else rn(H*0.45)
    # Simplify: south zone = 40% H, corridor = 1m, north zone = rest
    southH = rn(H*0.4); corH = 1.0; northH = rn(H - southH - corH)
    bedW = rn(W*0.6); batW = rn(W - bedW)

    r = [
        room(1,"Open Living and Kitchen",R(0,0,W,southH),A(0,0,W,southH)),
        room(2,"Corridor",R(0,southH,W,southH+corH),A(0,southH,W,southH+corH)),
        room(3,"Bedroom",R(0,southH+corH,bedW,H),A(0,southH+corH,bedW,H)),
        room(4,"Bathroom",R(bedW,southH+corH,W,H),A(bedW,southH+corH,W,H)),
    ]
    entrX = rn(W/2-1); enW = 2.0
    d = [
        door(1,"sliding","Main Entrance",seg(entrX,0,entrX+enW,0),1,"exterior"),
        door(2,"wooden","Living to Corridor",seg(rn(W*0.3),southH,rn(W*0.3+0.9),southH),1,2),
        door(3,"wooden","Corridor to Bedroom",seg(rn(bedW*0.4),southH+corH,rn(bedW*0.4+0.9),southH+corH),2,3),
        door(4,"wooden","Corridor to Bathroom",seg(rn(bedW+0.3),southH+corH,rn(bedW+1.2),southH+corH),2,4),
    ]
    w = [
        win(1,"sliding","South Window 1",seg(1,0,2.5,0),1),
        win(2,"sliding","South Window 2",seg(rn(W-3),0,rn(W-1.5),0),1),
        win(3,"casement","West Window",seg(0,rn(southH*0.3),0,rn(southH*0.7)),1),
        win(4,"casement","Bedroom North Window",seg(1,H,rn(bedW-1),H),3),
        win(5,"casement","Bedroom West Window",seg(0,rn(southH+corH+northH*0.3),0,rn(southH+corH+northH*0.7)),3),
        win(6,"awning","Bathroom North Window",seg(rn(bedW+0.3),H,rn(W-0.3),H),4),
    ]
    f = [
        furn(1,"Kitchen Counter South",R(0.2,0.2,rn(kW-0.3),0.8),1),
        furn(2,"Refrigerator",R(rn(kW-0.3),0.2,rn(kW+0.4),0.9),1),
        furn(3,"Sofa",R(rn(kW+0.3),0.5,rn(W-0.3),rn(southH*0.55)),1),
        furn(4,"Coffee Table",R(rn(kW+0.5),rn(southH*0.6),rn(W-1),rn(southH-0.5)),1),
        furn(5,"TV Stand",R(0.2,rn(southH-0.5),rn(kW-0.2),rn(southH-0.1)),1),
        furn(6,"Double Bed",R(0.5,rn(southH+corH+0.5),rn(bedW-0.3),rn(H-0.5)),3),
        furn(7,"Wardrobe",R(rn(bedW-1.3),rn(southH+corH+0.3),rn(bedW-0.2),rn(H-0.3)),3),
        furn(8,"Toilet",R(rn(bedW+0.2),rn(southH+corH+0.2),rn(bedW+0.6),rn(southH+corH+0.85)),4),
        furn(9,"Sink",R(rn(bedW+0.8),rn(southH+corH+0.2),rn(W-0.2),rn(southH+corH+0.65)),4),
        furn(10,"Shower",R(rn(bedW+0.2),rn(H-1.5),rn(W-0.2),rn(H-0.2)),4),
    ]
    m = [
        mep(1,"AC Unit",R(0.2,rn(southH-0.4),0.8,rn(southH-0.1)),"hvac"),
        mep(2,"Electrical Panel",R(rn(W/2-0.3),rn(southH+0.1),rn(W/2+0.3),rn(southH+0.4)),"electrical"),
        mep(3,"Water Heater",R(rn(W-0.8),rn(H-0.4),rn(W-0.2),rn(H-0.1)),"plumbing"),
    ]
    s = [
        wall(1,"South Wall",seg(0,0,W,0),"load-bearing"),
        wall(2,"East Wall",seg(W,0,W,H),"load-bearing"),
        wall(3,"North Wall",seg(0,H,W,H),"load-bearing"),
        wall(4,"West Wall",seg(0,0,0,H),"load-bearing"),
        wall(5,"Corridor South Wall",seg(0,southH,W,southH),"load-bearing"),
        wall(6,"Corridor North Wall",seg(0,southH+corH,W,southH+corH),"load-bearing"),
        wall(7,"Bed-Bath Wall",seg(bedW,southH+corH,bedW,H),"partition"),
    ]
    return {"layoutId":f"Layout-RES-{idx:03d}","outline":R(0,0,W,H),"rooms":r,"doors":d,"windows":w,"furniture":f,"mep":m,"structure":s}

# ── Blueprint B: 3-bed standard rectangle ────────────────────────────────────
def gen_3bed(idx, W=14.0, H=11.0):
    W,H = rn(W),rn(H)
    # South: Living + Entrance + Kitchen; Corridor; North: Master+Bath, Bed2, Bed3
    entW = rn(W*0.15); livW = rn(W*0.45); kitW = rn(W - livW - entW)
    southH = rn(H*0.45); corH = 1.0; northH = rn(H - southH - corH)
    mBedW = rn(W*0.35); batW = rn(W*0.15); bed2W = rn(W*0.28); bed3W = rn(W - mBedW - batW - bed2W)

    r = [
        room(1,"Living Room",R(0,0,livW,southH),A(0,0,livW,southH)),
        room(2,"Entrance Hall",R(livW,0,livW+entW,southH),A(livW,0,livW+entW,southH)),
        room(3,"Kitchen",R(livW+entW,0,W,southH),A(livW+entW,0,W,southH)),
        room(4,"Corridor",R(0,southH,W,southH+corH),A(0,southH,W,southH+corH)),
        room(5,"Master Bedroom",R(0,southH+corH,mBedW,H),A(0,southH+corH,mBedW,H)),
        room(6,"Master Bathroom",R(mBedW,southH+corH,mBedW+batW,H),A(mBedW,southH+corH,mBedW+batW,H)),
        room(7,"Bedroom 2",R(mBedW+batW,southH+corH,mBedW+batW+bed2W,H),A(mBedW+batW,southH+corH,mBedW+batW+bed2W,H)),
        room(8,"Bedroom 3",R(mBedW+batW+bed2W,southH+corH,W,H),A(mBedW+batW+bed2W,southH+corH,W,H)),
    ]
    eX = rn(livW + entW*0.1)
    d = [
        door(1,"wooden","Main Entrance",seg(rn(livW+0.2),0,rn(livW+2.2),0),2,"exterior"),
        door(2,"glass","Entrance to Living",seg(livW,rn(southH*0.3),livW,rn(southH*0.3+0.9)),1,2),
        door(3,"wooden","Entrance to Kitchen",seg(livW+entW,rn(southH*0.3),livW+entW,rn(southH*0.3+0.9)),2,3),
        door(4,"wooden","Living to Corridor",seg(rn(livW*0.3),southH,rn(livW*0.3+0.9),southH),1,4),
        door(5,"wooden","Kitchen to Corridor",seg(rn(livW+entW+kitW*0.4),southH,rn(livW+entW+kitW*0.4+0.9),southH),3,4),
        door(6,"wooden","Corridor to Master",seg(rn(mBedW*0.3),southH+corH,rn(mBedW*0.3+0.9),southH+corH),4,5),
        door(7,"wooden","Corridor to Master Bath",seg(rn(mBedW+batW*0.2),southH+corH,rn(mBedW+batW*0.2+0.9),southH+corH),4,6),
        door(8,"wooden","Corridor to Bed2",seg(rn(mBedW+batW+bed2W*0.3),southH+corH,rn(mBedW+batW+bed2W*0.3+0.9),southH+corH),4,7),
        door(9,"wooden","Corridor to Bed3",seg(rn(mBedW+batW+bed2W+bed3W*0.3),southH+corH,rn(mBedW+batW+bed2W+bed3W*0.3+0.9),southH+corH),4,8),
        door(10,"wooden","Master to Bath",seg(mBedW,rn(southH+corH+northH*0.5),mBedW,rn(southH+corH+northH*0.5+0.9)),5,6),
    ]
    w = [
        win(1,"casement","Living S Win 1",seg(0.5,0,2,0),1),
        win(2,"casement","Living S Win 2",seg(3,0,4.5,0),1),
        win(3,"casement","Living W Win",seg(0,rn(southH*0.3),0,rn(southH*0.7)),1),
        win(4,"casement","Kitchen S Win",seg(rn(livW+entW+1),0,rn(livW+entW+2.5),0),3),
        win(5,"casement","Kitchen E Win",seg(W,rn(southH*0.3),W,rn(southH*0.7)),3),
        win(6,"casement","Master N Win",seg(1,H,rn(mBedW-1),H),5),
        win(7,"casement","Master W Win",seg(0,rn(southH+corH+northH*0.3),0,rn(southH+corH+northH*0.7)),5),
        win(8,"awning","Bath N Win",seg(rn(mBedW+0.2),H,rn(mBedW+batW-0.2),H),6),
        win(9,"casement","Bed2 N Win",seg(rn(mBedW+batW+0.5),H,rn(mBedW+batW+bed2W-0.5),H),7),
        win(10,"casement","Bed3 N Win",seg(rn(mBedW+batW+bed2W+0.5),H,rn(W-0.5),H),8),
        win(11,"casement","Bed3 E Win",seg(W,rn(southH+corH+northH*0.3),W,rn(southH+corH+northH*0.7)),8),
    ]
    f = [
        furn(1,"Sectional Sofa",R(0.4,rn(southH*0.3),rn(livW*0.6),rn(southH*0.75)),1),
        furn(2,"Coffee Table",R(rn(livW*0.25),rn(southH*0.77),rn(livW*0.65),rn(southH-0.5)),1),
        furn(3,"TV Stand",R(rn(livW*0.6),rn(southH-0.5),rn(livW-0.2),rn(southH-0.1)),1),
        furn(4,"Dining Table",R(0.3,0.3,rn(livW*0.5),rn(southH*0.28)),1),
        furn(5,"Shoe Rack",R(rn(livW+0.2),0.2,rn(livW+entW-0.2),0.7),2),
        furn(6,"Kitchen Counter S",R(rn(livW+entW+0.2),0.2,rn(W-0.2),0.8),3),
        furn(7,"Kitchen Counter E",R(rn(W-0.7),0.2,rn(W-0.1),rn(southH-0.2)),3),
        furn(8,"Refrigerator",R(rn(livW+entW+0.2),0.9,rn(livW+entW+0.9),1.6),3),
        furn(9,"King Bed",R(0.4,rn(southH+corH+0.4),rn(mBedW*0.65),rn(southH+corH+northH*0.7)),5),
        furn(10,"Wardrobe",R(rn(mBedW*0.65),rn(southH+corH+0.2),rn(mBedW-0.2),rn(southH+corH+northH*0.8)),5),
        furn(11,"Dresser",R(0.3,rn(H-1.5),rn(mBedW*0.45),rn(H-0.2)),5),
        furn(12,"Toilet",R(rn(mBedW+0.2),rn(southH+corH+0.2),rn(mBedW+0.6),rn(southH+corH+0.85)),6),
        furn(13,"Sink",R(rn(mBedW+0.8),rn(southH+corH+0.2),rn(mBedW+batW-0.2),rn(southH+corH+0.65)),6),
        furn(14,"Shower",R(rn(mBedW+0.2),rn(H-1.4),rn(mBedW+batW-0.2),rn(H-0.2)),6),
        furn(15,"Double Bed",R(rn(mBedW+batW+0.3),rn(southH+corH+0.4),rn(mBedW+batW+bed2W*0.7),rn(southH+corH+northH*0.7)),7),
        furn(16,"Wardrobe Bed2",R(rn(mBedW+batW+bed2W*0.7),rn(southH+corH+0.2),rn(mBedW+batW+bed2W-0.2),rn(southH+corH+northH*0.75)),7),
        furn(17,"Single Bed",R(rn(mBedW+batW+bed2W+0.3),rn(southH+corH+0.4),rn(W-0.3),rn(southH+corH+northH*0.65)),8),
        furn(18,"Desk",R(rn(mBedW+batW+bed2W+0.3),rn(H-1.2),rn(W-2),rn(H-0.2)),8),
    ]
    m = [
        mep(1,"Living AC",R(0.2,rn(southH-0.35),0.9,rn(southH-0.1)),"hvac"),
        mep(2,"Electrical Panel",R(rn(W/2-0.3),rn(southH+0.1),rn(W/2+0.3),rn(southH+0.4)),"electrical"),
        mep(3,"Water Heater",R(rn(mBedW+0.2),rn(H-0.4),rn(mBedW+0.8),rn(H-0.1)),"plumbing"),
        mep(4,"Kitchen Exhaust",R(rn(W-2),rn(southH-0.35),rn(W-1.2),rn(southH-0.1)),"hvac"),
    ]
    s = [
        wall(1,"South Wall",seg(0,0,W,0),"load-bearing"),
        wall(2,"East Wall",seg(W,0,W,H),"load-bearing"),
        wall(3,"North Wall",seg(0,H,W,H),"load-bearing"),
        wall(4,"West Wall",seg(0,0,0,H),"load-bearing"),
        wall(5,"Living-Ent Wall",seg(livW,0,livW,southH),"partition"),
        wall(6,"Ent-Kit Wall",seg(livW+entW,0,livW+entW,southH),"partition"),
        wall(7,"Corridor S Wall",seg(0,southH,W,southH),"load-bearing"),
        wall(8,"Corridor N Wall",seg(0,southH+corH,W,southH+corH),"load-bearing"),
        wall(9,"Master-Bath Wall",seg(mBedW,southH+corH,mBedW,H),"partition"),
        wall(10,"Bath-Bed2 Wall",seg(mBedW+batW,southH+corH,mBedW+batW,H),"partition"),
        wall(11,"Bed2-Bed3 Wall",seg(mBedW+batW+bed2W,southH+corH,mBedW+batW+bed2W,H),"partition"),
    ]
    return {"layoutId":f"Layout-RES-{idx:03d}","outline":R(0,0,W,H),"rooms":r,"doors":d,"windows":w,"furniture":f,"mep":m,"structure":s}

# ── Blueprint C: 4-bed large rectangle ───────────────────────────────────────
def gen_4bed(idx, W=18.0, H=12.0):
    W,H = rn(W),rn(H)
    southH = rn(H*0.42); corH = 1.0; northH = rn(H - southH - corH)
    livW = rn(W*0.4); entW = rn(W*0.12); kitW = rn(W - livW - entW)
    mBW = rn(W*0.28); mBatW = rn(W*0.12); b2W = rn(W*0.22); batW = rn(W*0.12); b3W = rn(W - mBW - mBatW - b2W - batW)

    r = [
        room(1,"Living and Dining",R(0,0,livW,southH),A(0,0,livW,southH)),
        room(2,"Entrance Hall",R(livW,0,livW+entW,southH),A(livW,0,livW+entW,southH)),
        room(3,"Kitchen",R(livW+entW,0,W,southH),A(livW+entW,0,W,southH)),
        room(4,"Corridor",R(0,southH,W,southH+corH),A(0,southH,W,southH+corH)),
        room(5,"Master Suite",R(0,southH+corH,mBW,H),A(0,southH+corH,mBW,H)),
        room(6,"Master Bathroom",R(mBW,southH+corH,mBW+mBatW,H),A(mBW,southH+corH,mBW+mBatW,H)),
        room(7,"Bedroom 2",R(mBW+mBatW,southH+corH,mBW+mBatW+b2W,H),A(mBW+mBatW,southH+corH,mBW+mBatW+b2W,H)),
        room(8,"Bathroom 2",R(mBW+mBatW+b2W,southH+corH,mBW+mBatW+b2W+batW,H),A(mBW+mBatW+b2W,southH+corH,mBW+mBatW+b2W+batW,H)),
        room(9,"Bedroom 3",R(mBW+mBatW+b2W+batW,southH+corH,W,H),A(mBW+mBatW+b2W+batW,southH+corH,W,H)),
    ]
    d = [
        door(1,"wooden","Main Entrance",seg(rn(livW+0.2),0,rn(livW+2.2),0),2,"exterior"),
        door(2,"glass","Entrance to Living",seg(livW,rn(southH*0.35),livW,rn(southH*0.35+0.9)),1,2),
        door(3,"wooden","Entrance to Kitchen",seg(livW+entW,rn(southH*0.35),livW+entW,rn(southH*0.35+0.9)),2,3),
        door(4,"sliding","Living to Corridor",seg(rn(livW*0.25),southH,rn(livW*0.25+1.0),southH),1,4),
        door(5,"wooden","Kitchen to Corridor",seg(rn(livW+entW+kitW*0.4),southH,rn(livW+entW+kitW*0.4+0.9),southH),3,4),
        door(6,"wooden","Corridor to Master",seg(rn(mBW*0.25),southH+corH,rn(mBW*0.25+0.9),southH+corH),4,5),
        door(7,"wooden","Master to Bath",seg(mBW,rn(southH+corH+northH*0.4),mBW,rn(southH+corH+northH*0.4+0.9)),5,6),
        door(8,"wooden","Corridor to Bath",seg(rn(mBW+0.2),southH+corH,rn(mBW+1.1),southH+corH),4,6),
        door(9,"wooden","Corridor to Bed2",seg(rn(mBW+mBatW+b2W*0.25),southH+corH,rn(mBW+mBatW+b2W*0.25+0.9),southH+corH),4,7),
        door(10,"wooden","Bath2 to Bed2",seg(rn(mBW+mBatW+b2W),rn(southH+corH+northH*0.4),rn(mBW+mBatW+b2W),rn(southH+corH+northH*0.4+0.9)),7,8),
        door(11,"wooden","Corridor to Bed3",seg(rn(mBW+mBatW+b2W+batW+b3W*0.2),southH+corH,rn(mBW+mBatW+b2W+batW+b3W*0.2+0.9),southH+corH),4,9),
    ]
    w = [
        win(1,"sliding","Living S Win 1",seg(0.5,0,2,0),1),
        win(2,"sliding","Living S Win 2",seg(3.5,0,5,0),1),
        win(3,"casement","Living W Win",seg(0,rn(southH*0.3),0,rn(southH*0.65)),1),
        win(4,"casement","Kitchen S Win 1",seg(rn(livW+entW+0.5),0,rn(livW+entW+2),0),3),
        win(5,"casement","Kitchen S Win 2",seg(rn(W-3),0,rn(W-1.5),0),3),
        win(6,"casement","Kitchen E Win",seg(W,rn(southH*0.25),W,rn(southH*0.65)),3),
        win(7,"casement","Master N Win",seg(1,H,rn(mBW-1),H),5),
        win(8,"casement","Master W Win",seg(0,rn(southH+corH+northH*0.25),0,rn(southH+corH+northH*0.65)),5),
        win(9,"awning","MBath N Win",seg(rn(mBW+0.2),H,rn(mBW+mBatW-0.2),H),6),
        win(10,"casement","Bed2 N Win",seg(rn(mBW+mBatW+0.5),H,rn(mBW+mBatW+b2W-0.5),H),7),
        win(11,"casement","Bed3 N Win",seg(rn(mBW+mBatW+b2W+batW+0.5),H,rn(W-0.5),H),9),
        win(12,"casement","Bed3 E Win",seg(W,rn(southH+corH+northH*0.3),W,rn(southH+corH+northH*0.7)),9),
    ]
    f = [
        furn(1,"L-Sofa",R(0.4,rn(southH*0.3),rn(livW*0.55),rn(southH*0.75)),1),
        furn(2,"Coffee Table",R(rn(livW*0.2),rn(southH*0.78),rn(livW*0.65),rn(southH-0.5)),1),
        furn(3,"TV Stand",R(rn(livW*0.55),rn(southH-0.5),rn(livW-0.3),rn(southH-0.1)),1),
        furn(4,"Dining Table",R(0.3,0.3,rn(livW*0.6),rn(southH*0.28)),1),
        furn(5,"Dining Chair 1",R(0.5,rn(southH*0.28),1,rn(southH*0.28+0.5)),1),
        furn(6,"Dining Chair 2",R(rn(livW*0.35),rn(southH*0.28),rn(livW*0.35+0.5),rn(southH*0.28+0.5)),1),
        furn(7,"Shoe Rack",R(rn(livW+0.2),0.2,rn(livW+entW-0.2),0.7),2),
        furn(8,"Kitchen Counter S",R(rn(livW+entW+0.2),0.2,rn(W-0.2),0.8),3),
        furn(9,"Kitchen Counter E",R(rn(W-0.7),0.2,rn(W-0.1),rn(southH-0.5)),3),
        furn(10,"Refrigerator",R(rn(livW+entW+0.2),0.9,rn(livW+entW+0.9),1.6),3),
        furn(11,"Kitchen Island",R(rn(livW+entW+1.5),rn(southH*0.5),rn(livW+entW+4),rn(southH*0.5+0.7)),3),
        furn(12,"King Bed",R(0.4,rn(southH+corH+0.4),rn(mBW*0.6),rn(southH+corH+northH*0.7)),5),
        furn(13,"Wardrobe",R(rn(mBW*0.65),rn(southH+corH+0.2),rn(mBW-0.2),rn(southH+corH+northH*0.8)),5),
        furn(14,"Toilet",R(rn(mBW+0.2),rn(southH+corH+0.2),rn(mBW+0.6),rn(southH+corH+0.85)),6),
        furn(15,"Sink",R(rn(mBW+0.8),rn(southH+corH+0.2),rn(mBW+mBatW-0.2),rn(southH+corH+0.65)),6),
        furn(16,"Shower",R(rn(mBW+0.2),rn(H-1.4),rn(mBW+mBatW-0.2),rn(H-0.2)),6),
        furn(17,"Queen Bed",R(rn(mBW+mBatW+0.3),rn(southH+corH+0.4),rn(mBW+mBatW+b2W*0.65),rn(southH+corH+northH*0.7)),7),
        furn(18,"Desk",R(rn(mBW+mBatW+b2W*0.65),rn(southH+corH+0.4),rn(mBW+mBatW+b2W-0.2),rn(southH+corH+northH*0.55)),7),
        furn(19,"Toilet Bath2",R(rn(mBW+mBatW+b2W+0.2),rn(southH+corH+0.2),rn(mBW+mBatW+b2W+0.6),rn(southH+corH+0.85)),8),
        furn(20,"Sink Bath2",R(rn(mBW+mBatW+b2W+0.8),rn(southH+corH+0.2),rn(mBW+mBatW+b2W+batW-0.2),rn(southH+corH+0.65)),8),
        furn(21,"Shower Bath2",R(rn(mBW+mBatW+b2W+0.2),rn(H-1.4),rn(mBW+mBatW+b2W+batW-0.2),rn(H-0.2)),8),
        furn(22,"Single Bed",R(rn(mBW+mBatW+b2W+batW+0.3),rn(southH+corH+0.4),rn(W-0.3),rn(southH+corH+northH*0.65)),9),
        furn(23,"Wardrobe Bed3",R(rn(mBW+mBatW+b2W+batW+0.3),rn(H-1.5),rn(W-0.3),rn(H-0.2)),9),
    ]
    m = [
        mep(1,"Living AC",R(0.2,rn(southH-0.35),0.9,rn(southH-0.1)),"hvac"),
        mep(2,"Electrical Panel",R(rn(W/2-0.3),rn(southH+0.1),rn(W/2+0.3),rn(southH+0.4)),"electrical"),
        mep(3,"Water Heater",R(rn(mBW+0.2),rn(H-0.4),rn(mBW+0.8),rn(H-0.1)),"plumbing"),
        mep(4,"Kitchen Exhaust",R(rn(W-2.5),rn(southH-0.35),rn(W-1.7),rn(southH-0.1)),"hvac"),
    ]
    s = [
        wall(1,"South Wall",seg(0,0,W,0),"load-bearing"),
        wall(2,"East Wall",seg(W,0,W,H),"load-bearing"),
        wall(3,"North Wall",seg(0,H,W,H),"load-bearing"),
        wall(4,"West Wall",seg(0,0,0,H),"load-bearing"),
        wall(5,"Liv-Ent Wall",seg(livW,0,livW,southH),"partition"),
        wall(6,"Ent-Kit Wall",seg(livW+entW,0,livW+entW,southH),"partition"),
        wall(7,"Corr S Wall",seg(0,southH,W,southH),"load-bearing"),
        wall(8,"Corr N Wall",seg(0,southH+corH,W,southH+corH),"load-bearing"),
        wall(9,"Master-MBath Wall",seg(mBW,southH+corH,mBW,H),"partition"),
        wall(10,"MBath-Bed2 Wall",seg(mBW+mBatW,southH+corH,mBW+mBatW,H),"partition"),
        wall(11,"Bed2-Bath2 Wall",seg(mBW+mBatW+b2W,southH+corH,mBW+mBatW+b2W,H),"partition"),
        wall(12,"Bath2-Bed3 Wall",seg(mBW+mBatW+b2W+batW,southH+corH,mBW+mBatW+b2W+batW,H),"partition"),
    ]
    return {"layoutId":f"Layout-RES-{idx:03d}","outline":R(0,0,W,H),"rooms":r,"doors":d,"windows":w,"furniture":f,"mep":m,"structure":s}

# ── Blueprint D: Townhouse (narrow tall) ─────────────────────────────────────
def gen_townhouse(idx, W=7.0, H=20.0):
    W,H = rn(W),rn(H)
    # South to north: Entrance+Utility, Kitchen+Dining, Living, Bedroom1+Bath, Bedroom2+Bath2
    z1H = rn(H*0.12); z2H = rn(H*0.22); z3H = rn(H*0.22); z4H = rn(H*0.22); z5H = rn(H-z1H-z2H-z3H-z4H)
    uW = rn(W*0.45); kW = rn(W*0.55); bed1W = rn(W*0.6); bat1W = rn(W-bed1W)

    r = [
        room(1,"Entrance and Utility",R(0,0,W,z1H),A(0,0,W,z1H)),
        room(2,"Kitchen",R(0,z1H,kW,z1H+z2H),A(0,z1H,kW,z1H+z2H)),
        room(3,"Dining",R(kW,z1H,W,z1H+z2H),A(kW,z1H,W,z1H+z2H)),
        room(4,"Living Room",R(0,z1H+z2H,W,z1H+z2H+z3H),A(0,z1H+z2H,W,z1H+z2H+z3H)),
        room(5,"Bedroom 1",R(0,z1H+z2H+z3H,bed1W,z1H+z2H+z3H+z4H),A(0,z1H+z2H+z3H,bed1W,z1H+z2H+z3H+z4H)),
        room(6,"Bathroom 1",R(bed1W,z1H+z2H+z3H,W,z1H+z2H+z3H+z4H),A(bed1W,z1H+z2H+z3H,W,z1H+z2H+z3H+z4H)),
        room(7,"Master Bedroom",R(0,z1H+z2H+z3H+z4H,bed1W,H),A(0,z1H+z2H+z3H+z4H,bed1W,H)),
        room(8,"Master Bathroom",R(bed1W,z1H+z2H+z3H+z4H,W,H),A(bed1W,z1H+z2H+z3H+z4H,W,H)),
    ]
    y2 = z1H+z2H; y3 = y2+z3H; y4 = y3+z4H
    d = [
        door(1,"wooden","Main Entrance",seg(rn(W*0.25),0,rn(W*0.25+2.0),0),1,"exterior"),
        door(2,"wooden","Ent to Kitchen",seg(rn(W*0.2),z1H,rn(W*0.2+0.9),z1H),1,2),
        door(3,"wooden","Ent to Dining",seg(rn(kW+0.3),z1H,rn(kW+1.2),z1H),1,3),
        door(4,"wooden","Kitchen to Living",seg(rn(kW*0.3),y2,rn(kW*0.3+0.9),y2),2,4),
        door(5,"wooden","Dining to Living",seg(rn(kW+0.3),y2,rn(kW+1.2),y2),3,4),
        door(6,"wooden","Living to Bed1",seg(rn(bed1W*0.3),y3,rn(bed1W*0.3+0.9),y3),4,5),
        door(7,"wooden","Living to Bath1",seg(rn(bed1W+0.2),y3,rn(bed1W+1.1),y3),4,6),
        door(8,"wooden","Bed1 to Master",seg(rn(bed1W*0.3),y4,rn(bed1W*0.3+0.9),y4),5,7),
        door(9,"wooden","Bath1 to Master Bath",seg(rn(bed1W+0.2),y4,rn(bed1W+1.1),y4),6,8),
        door(10,"wooden","Master to MBath",seg(bed1W,rn(y4+z5H*0.4),bed1W,rn(y4+z5H*0.4+0.9)),7,8),
    ]
    w = [
        win(1,"casement","Entrance S Win",seg(rn(W*0.5),0,rn(W-0.5),0),1),
        win(2,"casement","Kitchen W Win",seg(0,rn(z1H+z2H*0.3),0,rn(z1H+z2H*0.7)),2),
        win(3,"casement","Dining E Win",seg(W,rn(z1H+z2H*0.3),W,rn(z1H+z2H*0.7)),3),
        win(4,"sliding","Living W Win",seg(0,rn(y2+z3H*0.25),0,rn(y2+z3H*0.75)),4),
        win(5,"sliding","Living E Win",seg(W,rn(y2+z3H*0.25),W,rn(y2+z3H*0.75)),4),
        win(6,"casement","Bed1 W Win",seg(0,rn(y3+z4H*0.3),0,rn(y3+z4H*0.7)),5),
        win(7,"awning","Bath1 E Win",seg(W,rn(y3+z4H*0.3),W,rn(y3+z4H*0.6)),6),
        win(8,"casement","Master W Win",seg(0,rn(y4+z5H*0.25),0,rn(y4+z5H*0.65)),7),
        win(9,"casement","Master N Win",seg(0.5,H,rn(bed1W-0.5),H),7),
        win(10,"awning","MBath N Win",seg(rn(bed1W+0.2),H,rn(W-0.2),H),8),
    ]
    f = [
        furn(1,"Shoe Rack",R(0.2,0.2,rn(W*0.4),0.6),1),
        furn(2,"Washing Machine",R(rn(W*0.5),0.2,rn(W*0.5+0.7),0.9),1),
        furn(3,"Kitchen Counter W",R(0.2,rn(z1H+0.2),0.8,rn(y2-0.2)),2),
        furn(4,"Kitchen Counter N",R(0.2,rn(y2-0.8),rn(kW-0.2),rn(y2-0.2)),2),
        furn(5,"Refrigerator",R(rn(kW-1),rn(z1H+0.2),rn(kW-0.3),rn(z1H+0.9)),2),
        furn(6,"Dining Table",R(rn(kW+0.2),rn(z1H+0.3),rn(W-0.2),rn(y2-0.3)),3),
        furn(7,"Sofa",R(0.3,rn(y2+0.4),rn(W-0.3),rn(y2+z3H*0.55)),4),
        furn(8,"Coffee Table",R(0.8,rn(y2+z3H*0.55),rn(W-0.8),rn(y2+z3H*0.7)),4),
        furn(9,"TV Stand",R(0.3,rn(y3-0.5),rn(W-0.3),rn(y3-0.1)),4),
        furn(10,"Double Bed",R(0.3,rn(y3+0.4),rn(bed1W-0.3),rn(y3+z4H*0.75)),5),
        furn(11,"Wardrobe",R(0.3,rn(y4-1.2),rn(bed1W-0.3),rn(y4-0.2)),5),
        furn(12,"Toilet",R(rn(bed1W+0.2),rn(y3+0.2),rn(bed1W+0.6),rn(y3+0.85)),6),
        furn(13,"Sink",R(rn(bed1W+0.8),rn(y3+0.2),rn(W-0.2),rn(y3+0.65)),6),
        furn(14,"Shower",R(rn(bed1W+0.2),rn(y4-1.4),rn(W-0.2),rn(y4-0.2)),6),
        furn(15,"King Bed",R(0.3,rn(y4+0.4),rn(bed1W-0.3),rn(y4+z5H*0.7)),7),
        furn(16,"Dresser",R(0.3,rn(H-1.5),rn(bed1W*0.5),rn(H-0.2)),7),
        furn(17,"Toilet M",R(rn(bed1W+0.2),rn(y4+0.2),rn(bed1W+0.6),rn(y4+0.85)),8),
        furn(18,"Sink M",R(rn(bed1W+0.8),rn(y4+0.2),rn(W-0.2),rn(y4+0.65)),8),
        furn(19,"Shower M",R(rn(bed1W+0.2),rn(H-1.5),rn(W-0.2),rn(H-0.2)),8),
    ]
    m = [
        mep(1,"Living AC",R(0.2,rn(y3-0.35),0.9,rn(y3-0.1)),"hvac"),
        mep(2,"Electrical Panel",R(rn(W/2-0.3),rn(y2+0.1),rn(W/2+0.3),rn(y2+0.4)),"electrical"),
        mep(3,"Water Heater",R(rn(W-0.8),rn(H-0.4),rn(W-0.2),rn(H-0.1)),"plumbing"),
        mep(4,"Kitchen Exhaust",R(rn(kW*0.5),rn(y2-0.35),rn(kW*0.5+0.8),rn(y2-0.1)),"hvac"),
    ]
    s = [
        wall(1,"South Wall",seg(0,0,W,0),"load-bearing"),
        wall(2,"East Wall",seg(W,0,W,H),"load-bearing"),
        wall(3,"North Wall",seg(0,H,W,H),"load-bearing"),
        wall(4,"West Wall",seg(0,0,0,H),"load-bearing"),
        wall(5,"Ent-Kit Wall",seg(0,z1H,W,z1H),"load-bearing"),
        wall(6,"Kit-Din Wall",seg(kW,z1H,kW,y2),"partition"),
        wall(7,"Kit-Living Wall",seg(0,y2,W,y2),"load-bearing"),
        wall(8,"Living-Bed1 Wall",seg(0,y3,W,y3),"load-bearing"),
        wall(9,"Bed1-Bath1 Wall",seg(bed1W,y3,bed1W,y4),"partition"),
        wall(10,"Bed-Master Wall",seg(0,y4,W,y4),"load-bearing"),
        wall(11,"Master-MBath Wall",seg(bed1W,y4,bed1W,H),"partition"),
    ]
    return {"layoutId":f"Layout-RES-{idx:03d}","outline":R(0,0,W,H),"rooms":r,"doors":d,"windows":w,"furniture":f,"mep":m,"structure":s}

# ── Blueprint E: Open plan 2-bed ─────────────────────────────────────────────
def gen_openplan(idx, W=12.0, H=9.0):
    W,H = rn(W),rn(H)
    openH = rn(H*0.55); bed1W = rn(W*0.5); batW = rn(W*0.18); bed2W = rn(W-bed1W-batW)

    r = [
        room(1,"Open Plan Living Kitchen",R(0,0,W,openH),A(0,0,W,openH)),
        room(2,"Master Bedroom",R(0,openH,bed1W,H),A(0,openH,bed1W,H)),
        room(3,"Bathroom",R(bed1W,openH,bed1W+batW,H),A(bed1W,openH,bed1W+batW,H)),
        room(4,"Bedroom 2",R(bed1W+batW,openH,W,H),A(bed1W+batW,openH,W,H)),
    ]
    northH = rn(H - openH)
    d = [
        door(1,"sliding","Main Entrance",seg(rn(W/2-1),0,rn(W/2+1),0),1,"exterior"),
        door(2,"wooden","Open to Master",seg(rn(bed1W*0.3),openH,rn(bed1W*0.3+0.9),openH),1,2),
        door(3,"wooden","Open to Bathroom",seg(rn(bed1W+0.2),openH,rn(bed1W+1.1),openH),1,3),
        door(4,"wooden","Open to Bed2",seg(rn(bed1W+batW+bed2W*0.3),openH,rn(bed1W+batW+bed2W*0.3+0.9),openH),1,4),
        door(5,"wooden","Master to Bathroom",seg(bed1W,rn(openH+northH*0.4),bed1W,rn(openH+northH*0.4+0.9)),2,3),
    ]
    w = [
        win(1,"sliding","South Win 1",seg(0.5,0,2,0),1),
        win(2,"sliding","South Win 2",seg(rn(W/2-0.5),0,rn(W/2+1),0),1),
        win(3,"sliding","South Win 3",seg(rn(W-2.5),0,rn(W-1),0),1),
        win(4,"casement","West Win",seg(0,rn(openH*0.3),0,rn(openH*0.7)),1),
        win(5,"casement","East Win",seg(W,rn(openH*0.3),W,rn(openH*0.7)),1),
        win(6,"casement","Master N Win",seg(0.5,H,rn(bed1W-0.5),H),2),
        win(7,"casement","Master W Win",seg(0,rn(openH+northH*0.25),0,rn(openH+northH*0.65)),2),
        win(8,"awning","Bath N Win",seg(rn(bed1W+0.2),H,rn(bed1W+batW-0.2),H),3),
        win(9,"casement","Bed2 N Win",seg(rn(bed1W+batW+0.5),H,rn(W-0.5),H),4),
        win(10,"casement","Bed2 E Win",seg(W,rn(openH+northH*0.25),W,rn(openH+northH*0.65)),4),
    ]
    f = [
        furn(1,"Kitchen Counter S",R(0.2,0.2,rn(W*0.4),0.8),1),
        furn(2,"Kitchen Counter W",R(0.2,0.2,0.8,rn(openH*0.5)),1),
        furn(3,"Refrigerator",R(rn(W*0.4),0.2,rn(W*0.4+0.7),0.9),1),
        furn(4,"Kitchen Island",R(rn(W*0.35),rn(openH*0.25),rn(W*0.65),rn(openH*0.45)),1),
        furn(5,"Sofa",R(rn(W*0.5),rn(openH*0.5),rn(W-0.3),rn(openH*0.85)),1),
        furn(6,"Coffee Table",R(rn(W*0.6),rn(openH*0.85),rn(W-0.8),rn(openH-0.5)),1),
        furn(7,"TV Stand",R(rn(W*0.5),rn(openH-0.5),rn(W-0.3),rn(openH-0.1)),1),
        furn(8,"Dining Table",R(rn(W*0.55),0.3,rn(W-0.3),rn(openH*0.3)),1),
        furn(9,"King Bed",R(0.4,rn(openH+0.4),rn(bed1W-0.3),rn(openH+northH*0.7)),2),
        furn(10,"Wardrobe",R(0.4,rn(H-1.3),rn(bed1W*0.6),rn(H-0.2)),2),
        furn(11,"Toilet",R(rn(bed1W+0.2),rn(openH+0.2),rn(bed1W+0.6),rn(openH+0.85)),3),
        furn(12,"Sink",R(rn(bed1W+0.8),rn(openH+0.2),rn(bed1W+batW-0.2),rn(openH+0.65)),3),
        furn(13,"Shower",R(rn(bed1W+0.2),rn(H-1.5),rn(bed1W+batW-0.2),rn(H-0.2)),3),
        furn(14,"Double Bed",R(rn(bed1W+batW+0.3),rn(openH+0.4),rn(W-0.3),rn(openH+northH*0.7)),4),
        furn(15,"Desk",R(rn(bed1W+batW+0.3),rn(H-1.2),rn(W-0.3),rn(H-0.2)),4),
    ]
    m = [
        mep(1,"Open Plan AC",R(0.2,rn(openH-0.35),0.9,rn(openH-0.1)),"hvac"),
        mep(2,"Electrical Panel",R(rn(bed1W-0.3),rn(openH+0.1),rn(bed1W+0.3),rn(openH+0.4)),"electrical"),
        mep(3,"Water Heater",R(rn(bed1W+0.2),rn(H-0.4),rn(bed1W+0.8),rn(H-0.1)),"plumbing"),
        mep(4,"Kitchen Exhaust",R(rn(W*0.3),rn(openH-0.35),rn(W*0.3+0.8),rn(openH-0.1)),"hvac"),
    ]
    s = [
        wall(1,"South Wall",seg(0,0,W,0),"load-bearing"),
        wall(2,"East Wall",seg(W,0,W,H),"load-bearing"),
        wall(3,"North Wall",seg(0,H,W,H),"load-bearing"),
        wall(4,"West Wall",seg(0,0,0,H),"load-bearing"),
        wall(5,"Open-Priv Wall",seg(0,openH,W,openH),"load-bearing"),
        wall(6,"Master-Bath Wall",seg(bed1W,openH,bed1W,H),"partition"),
        wall(7,"Bath-Bed2 Wall",seg(bed1W+batW,openH,bed1W+batW,H),"partition"),
    ]
    return {"layoutId":f"Layout-RES-{idx:03d}","outline":R(0,0,W,H),"rooms":r,"doors":d,"windows":w,"furniture":f,"mep":m,"structure":s}

# ── Blueprint F: L-shaped outline (2 rectangular zones) ──────────────────────
def gen_l_outline(idx, W1=14.0, H1=8.0, W2=8.0, H2=5.0):
    # Bottom zone: x=0..W1, y=0..H1
    # Top-left extension: x=0..W2, y=H1..H1+H2
    W1,H1,W2,H2 = rn(W1),rn(H1),rn(W2),rn(H2)
    TH = rn(H1+H2)
    outline = close([[0,0],[W1,0],[W1,H1],[W2,H1],[W2,TH],[0,TH]])

    southH = rn(H1*0.5); corH = 1.0
    livW = rn(W1*0.42); entW = rn(W1*0.14); kitW = rn(W1-livW-entW)
    # North of bottom zone: corridor + small rooms
    northH1 = rn(H1 - southH - corH)
    bed1W = rn(W1*0.35); bat1W = rn(W1*0.15); bed2W = rn(W1-bed1W-bat1W)

    r = [
        room(1,"Living Room",R(0,0,livW,southH),A(0,0,livW,southH)),
        room(2,"Entrance Hall",R(livW,0,livW+entW,southH),A(livW,0,livW+entW,southH)),
        room(3,"Kitchen",R(livW+entW,0,W1,southH),A(livW+entW,0,W1,southH)),
        room(4,"Corridor",R(0,southH,W1,southH+corH),A(0,southH,W1,southH+corH)),
        room(5,"Bedroom 2",R(0,southH+corH,bed1W,H1),A(0,southH+corH,bed1W,H1)),
        room(6,"Bathroom",R(bed1W,southH+corH,bed1W+bat1W,H1),A(bed1W,southH+corH,bed1W+bat1W,H1)),
        room(7,"Bedroom 3",R(bed1W+bat1W,southH+corH,W1,H1),A(bed1W+bat1W,southH+corH,W1,H1)),
        room(8,"Master Bedroom",R(0,H1,W2,TH),A(0,H1,W2,TH)),
    ]
    d = [
        door(1,"wooden","Main Entrance",seg(rn(livW+0.2),0,rn(livW+2.2),0),2,"exterior"),
        door(2,"glass","Entrance to Living",seg(livW,rn(southH*0.35),livW,rn(southH*0.35+0.9)),1,2),
        door(3,"wooden","Entrance to Kitchen",seg(livW+entW,rn(southH*0.35),livW+entW,rn(southH*0.35+0.9)),2,3),
        door(4,"wooden","Living to Corridor",seg(rn(livW*0.3),southH,rn(livW*0.3+0.9),southH),1,4),
        door(5,"wooden","Kitchen to Corridor",seg(rn(livW+entW+kitW*0.4),southH,rn(livW+entW+kitW*0.4+0.9),southH),3,4),
        door(6,"wooden","Corridor to Bed2",seg(rn(bed1W*0.3),southH+corH,rn(bed1W*0.3+0.9),southH+corH),4,5),
        door(7,"wooden","Corridor to Bath",seg(rn(bed1W+0.2),southH+corH,rn(bed1W+1.1),southH+corH),4,6),
        door(8,"wooden","Corridor to Bed3",seg(rn(bed1W+bat1W+bed2W*0.3),southH+corH,rn(bed1W+bat1W+bed2W*0.3+0.9),southH+corH),4,7),
        door(9,"wooden","Corridor to Master",seg(rn(W2*0.3),H1,rn(W2*0.3+0.9),H1),4,8),
    ]
    w = [
        win(1,"casement","Living S Win",seg(0.5,0,2,0),1),
        win(2,"casement","Living S Win 2",seg(3,0,4.5,0),1),
        win(3,"casement","Living W Win",seg(0,rn(southH*0.3),0,rn(southH*0.7)),1),
        win(4,"casement","Kitchen S Win",seg(rn(livW+entW+1),0,rn(livW+entW+2.5),0),3),
        win(5,"casement","Kitchen E Win",seg(W1,rn(southH*0.3),W1,rn(southH*0.7)),3),
        win(6,"casement","Bed2 N Win",seg(0.5,H1,rn(bed1W-0.5),H1),5),
        win(7,"awning","Bath N Win",seg(rn(bed1W+0.2),H1,rn(bed1W+bat1W-0.2),H1),6),
        win(8,"casement","Bed3 N Win",seg(rn(bed1W+bat1W+0.5),H1,rn(W1-0.5),H1),7),
        win(9,"casement","Master N Win",seg(0.5,TH,rn(W2-0.5),TH),8),
        win(10,"casement","Master W Win",seg(0,rn(H1+H2*0.3),0,rn(H1+H2*0.7)),8),
    ]
    f = [
        furn(1,"Sofa",R(0.4,rn(southH*0.35),rn(livW*0.6),rn(southH*0.75)),1),
        furn(2,"Coffee Table",R(rn(livW*0.2),rn(southH*0.77),rn(livW*0.65),rn(southH-0.5)),1),
        furn(3,"TV Stand",R(rn(livW*0.6),rn(southH-0.5),rn(livW-0.2),rn(southH-0.1)),1),
        furn(4,"Dining Table",R(0.3,0.3,rn(livW*0.55),rn(southH*0.3)),1),
        furn(5,"Shoe Rack",R(rn(livW+0.2),0.2,rn(livW+entW-0.2),0.6),2),
        furn(6,"Kitchen Counter S",R(rn(livW+entW+0.2),0.2,rn(W1-0.2),0.8),3),
        furn(7,"Kitchen Counter E",R(rn(W1-0.7),0.2,rn(W1-0.1),rn(southH-0.2)),3),
        furn(8,"Refrigerator",R(rn(livW+entW+0.2),0.9,rn(livW+entW+0.9),1.6),3),
        furn(9,"Double Bed",R(0.4,rn(southH+corH+0.4),rn(bed1W-0.3),rn(H1-0.5)),5),
        furn(10,"Wardrobe",R(0.3,rn(H1-1.3),rn(bed1W*0.7),rn(H1-0.2)),5),
        furn(11,"Toilet",R(rn(bed1W+0.2),rn(southH+corH+0.2),rn(bed1W+0.6),rn(southH+corH+0.85)),6),
        furn(12,"Sink",R(rn(bed1W+0.8),rn(southH+corH+0.2),rn(bed1W+bat1W-0.2),rn(southH+corH+0.65)),6),
        furn(13,"Shower",R(rn(bed1W+0.2),rn(H1-1.4),rn(bed1W+bat1W-0.2),rn(H1-0.2)),6),
        furn(14,"Single Bed",R(rn(bed1W+bat1W+0.3),rn(southH+corH+0.4),rn(W1-0.3),rn(H1-0.5)),7),
        furn(15,"King Bed",R(0.4,rn(H1+0.4),rn(W2-0.3),rn(H1+H2*0.65)),8),
        furn(16,"Wardrobe Master",R(0.3,rn(TH-1.3),rn(W2*0.65),rn(TH-0.2)),8),
        furn(17,"Dresser",R(rn(W2*0.65),rn(TH-1.3),rn(W2-0.3),rn(TH-0.2)),8),
    ]
    m = [
        mep(1,"Living AC",R(0.2,rn(southH-0.35),0.9,rn(southH-0.1)),"hvac"),
        mep(2,"Electrical Panel",R(rn(W1/2-0.3),rn(southH+0.1),rn(W1/2+0.3),rn(southH+0.4)),"electrical"),
        mep(3,"Water Heater",R(rn(bed1W+0.2),rn(H1-0.4),rn(bed1W+0.8),rn(H1-0.1)),"plumbing"),
        mep(4,"Kitchen Exhaust",R(rn(W1-2.5),rn(southH-0.35),rn(W1-1.7),rn(southH-0.1)),"hvac"),
    ]
    s = [
        wall(1,"South Wall",seg(0,0,W1,0),"load-bearing"),
        wall(2,"East Bottom Wall",seg(W1,0,W1,H1),"load-bearing"),
        wall(3,"Step Wall",seg(W2,H1,W1,H1),"load-bearing"),
        wall(4,"West Top Wall",seg(W2,H1,W2,TH),"load-bearing"),
        wall(5,"North Top Wall",seg(0,TH,W2,TH),"load-bearing"),
        wall(6,"West Wall",seg(0,0,0,TH),"load-bearing"),
        wall(7,"Liv-Ent Wall",seg(livW,0,livW,southH),"partition"),
        wall(8,"Ent-Kit Wall",seg(livW+entW,0,livW+entW,southH),"partition"),
        wall(9,"Corr S Wall",seg(0,southH,W1,southH),"load-bearing"),
        wall(10,"Corr N Wall",seg(0,southH+corH,W1,southH+corH),"load-bearing"),
        wall(11,"Bed2-Bath Wall",seg(bed1W,southH+corH,bed1W,H1),"partition"),
        wall(12,"Bath-Bed3 Wall",seg(bed1W+bat1W,southH+corH,bed1W+bat1W,H1),"partition"),
    ]
    return {"layoutId":f"Layout-RES-{idx:03d}","outline":outline,"rooms":r,"doors":d,"windows":w,"furniture":f,"mep":m,"structure":s}

# ── Blueprint G: 5-bed grand ──────────────────────────────────────────────────
def gen_5bed(idx, W=20.0, H=11.0):
    W,H = rn(W),rn(H)
    southH = rn(H*0.45); corH = 1.0; northH = rn(H-southH-corH)
    livW = rn(W*0.35); entW = rn(W*0.1); kitW = rn(W-livW-entW)
    # North: master+bath | bed2 | bath2 | bed3 | bed4 | bed5
    mBW = rn(W*0.22); mBatW = rn(W*0.1); b2W = rn(W*0.17); batW = rn(W*0.1)
    b3W = rn(W*0.15); b4W = rn(W*0.13); b5W = rn(W-mBW-mBatW-b2W-batW-b3W-b4W)

    r = [
        room(1,"Living and Dining",R(0,0,livW,southH),A(0,0,livW,southH)),
        room(2,"Entrance Hall",R(livW,0,livW+entW,southH),A(livW,0,livW+entW,southH)),
        room(3,"Kitchen",R(livW+entW,0,W,southH),A(livW+entW,0,W,southH)),
        room(4,"Corridor",R(0,southH,W,southH+corH),A(0,southH,W,southH+corH)),
        room(5,"Master Suite",R(0,southH+corH,mBW,H),A(0,southH+corH,mBW,H)),
        room(6,"Master Bathroom",R(mBW,southH+corH,mBW+mBatW,H),A(mBW,southH+corH,mBW+mBatW,H)),
        room(7,"Bedroom 2",R(mBW+mBatW,southH+corH,mBW+mBatW+b2W,H),A(mBW+mBatW,southH+corH,mBW+mBatW+b2W,H)),
        room(8,"Bathroom 2",R(mBW+mBatW+b2W,southH+corH,mBW+mBatW+b2W+batW,H),A(mBW+mBatW+b2W,southH+corH,mBW+mBatW+b2W+batW,H)),
        room(9,"Bedroom 3",R(mBW+mBatW+b2W+batW,southH+corH,mBW+mBatW+b2W+batW+b3W,H),A(mBW+mBatW+b2W+batW,southH+corH,mBW+mBatW+b2W+batW+b3W,H)),
        room(10,"Bedroom 4",R(mBW+mBatW+b2W+batW+b3W,southH+corH,mBW+mBatW+b2W+batW+b3W+b4W,H),A(mBW+mBatW+b2W+batW+b3W,southH+corH,mBW+mBatW+b2W+batW+b3W+b4W,H)),
        room(11,"Bedroom 5",R(mBW+mBatW+b2W+batW+b3W+b4W,southH+corH,W,H),A(mBW+mBatW+b2W+batW+b3W+b4W,southH+corH,W,H)),
    ]
    x5 = mBW+mBatW+b2W+batW+b3W+b4W
    d = [
        door(1,"wooden","Main Entrance",seg(rn(livW+0.2),0,rn(livW+2.2),0),2,"exterior"),
        door(2,"glass","Ent to Living",seg(livW,rn(southH*0.35),livW,rn(southH*0.35+0.9)),1,2),
        door(3,"wooden","Ent to Kitchen",seg(livW+entW,rn(southH*0.35),livW+entW,rn(southH*0.35+0.9)),2,3),
        door(4,"sliding","Living to Corr",seg(rn(livW*0.2),southH,rn(livW*0.2+1.0),southH),1,4),
        door(5,"wooden","Kitchen to Corr",seg(rn(livW+entW+kitW*0.4),southH,rn(livW+entW+kitW*0.4+0.9),southH),3,4),
        door(6,"wooden","Corr to Master",seg(rn(mBW*0.2),southH+corH,rn(mBW*0.2+0.9),southH+corH),4,5),
        door(7,"wooden","Master to Bath",seg(mBW,rn(southH+corH+northH*0.4),mBW,rn(southH+corH+northH*0.4+0.9)),5,6),
        door(8,"wooden","Corr to Bed2",seg(rn(mBW+mBatW+b2W*0.2),southH+corH,rn(mBW+mBatW+b2W*0.2+0.9),southH+corH),4,7),
        door(9,"wooden","Bed2 to Bath2",seg(rn(mBW+mBatW+b2W),rn(southH+corH+northH*0.4),rn(mBW+mBatW+b2W),rn(southH+corH+northH*0.4+0.9)),7,8),
        door(10,"wooden","Corr to Bed3",seg(rn(mBW+mBatW+b2W+batW+b3W*0.2),southH+corH,rn(mBW+mBatW+b2W+batW+b3W*0.2+0.9),southH+corH),4,9),
        door(11,"wooden","Corr to Bed4",seg(rn(mBW+mBatW+b2W+batW+b3W+b4W*0.2),southH+corH,rn(mBW+mBatW+b2W+batW+b3W+b4W*0.2+0.9),southH+corH),4,10),
        door(12,"wooden","Corr to Bed5",seg(rn(x5+b5W*0.2),southH+corH,rn(x5+b5W*0.2+0.9),southH+corH),4,11),
    ]
    w = [
        win(1,"sliding","Living S 1",seg(0.5,0,2,0),1),
        win(2,"sliding","Living S 2",seg(3.5,0,5,0),1),
        win(3,"casement","Living W",seg(0,rn(southH*0.3),0,rn(southH*0.65)),1),
        win(4,"casement","Kitchen S 1",seg(rn(livW+entW+1),0,rn(livW+entW+2.5),0),3),
        win(5,"casement","Kitchen S 2",seg(rn(W-3.5),0,rn(W-2),0),3),
        win(6,"casement","Kitchen E",seg(W,rn(southH*0.3),W,rn(southH*0.65)),3),
        win(7,"casement","Master N",seg(0.8,H,rn(mBW-0.8),H),5),
        win(8,"casement","Master W",seg(0,rn(southH+corH+northH*0.25),0,rn(southH+corH+northH*0.65)),5),
        win(9,"awning","MBath N",seg(rn(mBW+0.1),H,rn(mBW+mBatW-0.1),H),6),
        win(10,"casement","Bed2 N",seg(rn(mBW+mBatW+0.3),H,rn(mBW+mBatW+b2W-0.3),H),7),
        win(11,"casement","Bed3 N",seg(rn(mBW+mBatW+b2W+batW+0.3),H,rn(mBW+mBatW+b2W+batW+b3W-0.3),H),9),
        win(12,"casement","Bed4 N",seg(rn(mBW+mBatW+b2W+batW+b3W+0.2),H,rn(mBW+mBatW+b2W+batW+b3W+b4W-0.2),H),10),
        win(13,"casement","Bed5 N",seg(rn(x5+0.3),H,rn(W-0.3),H),11),
        win(14,"casement","Bed5 E",seg(W,rn(southH+corH+northH*0.3),W,rn(southH+corH+northH*0.7)),11),
    ]
    f = [
        furn(1,"Large Sofa",R(0.4,rn(southH*0.3),rn(livW*0.7),rn(southH*0.75)),1),
        furn(2,"Coffee Table",R(rn(livW*0.2),rn(southH*0.77),rn(livW*0.65),rn(southH-0.5)),1),
        furn(3,"TV Stand",R(rn(livW*0.65),rn(southH-0.5),rn(livW-0.2),rn(southH-0.1)),1),
        furn(4,"Dining Table",R(0.3,0.3,rn(livW*0.6),rn(southH*0.28)),1),
        furn(5,"Shoe Rack",R(rn(livW+0.2),0.2,rn(livW+entW-0.2),0.6),2),
        furn(6,"Kitchen Counter S",R(rn(livW+entW+0.2),0.2,rn(W-0.2),0.8),3),
        furn(7,"Kitchen Counter E",R(rn(W-0.7),0.2,rn(W-0.1),rn(southH-0.5)),3),
        furn(8,"Refrigerator",R(rn(livW+entW+0.2),0.9,rn(livW+entW+0.9),1.6),3),
        furn(9,"Kitchen Island",R(rn(livW+entW+1.5),rn(southH*0.45),rn(livW+entW+4.5),rn(southH*0.45+0.7)),3),
        furn(10,"King Bed",R(0.4,rn(southH+corH+0.4),rn(mBW*0.65),rn(southH+corH+northH*0.7)),5),
        furn(11,"Wardrobe",R(rn(mBW*0.65),rn(southH+corH+0.3),rn(mBW-0.2),rn(southH+corH+northH*0.8)),5),
        furn(12,"Toilet",R(rn(mBW+0.2),rn(southH+corH+0.2),rn(mBW+0.6),rn(southH+corH+0.85)),6),
        furn(13,"Sink",R(rn(mBW+0.8),rn(southH+corH+0.2),rn(mBW+mBatW-0.2),rn(southH+corH+0.65)),6),
        furn(14,"Shower",R(rn(mBW+0.2),rn(H-1.4),rn(mBW+mBatW-0.2),rn(H-0.2)),6),
        furn(15,"Queen Bed",R(rn(mBW+mBatW+0.3),rn(southH+corH+0.4),rn(mBW+mBatW+b2W*0.65),rn(southH+corH+northH*0.7)),7),
        furn(16,"Toilet B2",R(rn(mBW+mBatW+b2W+0.2),rn(southH+corH+0.2),rn(mBW+mBatW+b2W+0.6),rn(southH+corH+0.85)),8),
        furn(17,"Sink B2",R(rn(mBW+mBatW+b2W+0.8),rn(southH+corH+0.2),rn(mBW+mBatW+b2W+batW-0.2),rn(southH+corH+0.65)),8),
        furn(18,"Single Bed 3",R(rn(mBW+mBatW+b2W+batW+0.3),rn(southH+corH+0.4),rn(mBW+mBatW+b2W+batW+b3W-0.3),rn(southH+corH+northH*0.65)),9),
        furn(19,"Single Bed 4",R(rn(mBW+mBatW+b2W+batW+b3W+0.2),rn(southH+corH+0.4),rn(mBW+mBatW+b2W+batW+b3W+b4W-0.2),rn(southH+corH+northH*0.65)),10),
        furn(20,"Single Bed 5",R(rn(x5+0.3),rn(southH+corH+0.4),rn(W-0.3),rn(southH+corH+northH*0.65)),11),
        furn(21,"Wardrobe Bed5",R(rn(x5+0.3),rn(H-1.3),rn(W-0.3),rn(H-0.2)),11),
    ]
    x2 = mBW+mBatW; x3 = x2+b2W; x4 = x3+batW; x5b = x4+b3W; x6 = x5b+b4W
    m = [
        mep(1,"Living AC",R(0.2,rn(southH-0.35),0.9,rn(southH-0.1)),"hvac"),
        mep(2,"Electrical Panel",R(rn(W/2-0.3),rn(southH+0.1),rn(W/2+0.3),rn(southH+0.4)),"electrical"),
        mep(3,"Water Heater",R(rn(mBW+0.2),rn(H-0.4),rn(mBW+0.8),rn(H-0.1)),"plumbing"),
        mep(4,"Kitchen Exhaust",R(rn(W-3),rn(southH-0.35),rn(W-2.2),rn(southH-0.1)),"hvac"),
    ]
    s = [
        wall(1,"South Wall",seg(0,0,W,0),"load-bearing"),
        wall(2,"East Wall",seg(W,0,W,H),"load-bearing"),
        wall(3,"North Wall",seg(0,H,W,H),"load-bearing"),
        wall(4,"West Wall",seg(0,0,0,H),"load-bearing"),
        wall(5,"Liv-Ent Wall",seg(livW,0,livW,southH),"partition"),
        wall(6,"Ent-Kit Wall",seg(livW+entW,0,livW+entW,southH),"partition"),
        wall(7,"Corr S Wall",seg(0,southH,W,southH),"load-bearing"),
        wall(8,"Corr N Wall",seg(0,southH+corH,W,southH+corH),"load-bearing"),
        wall(9,"Master-MBath",seg(mBW,southH+corH,mBW,H),"partition"),
        wall(10,"MBath-Bed2",seg(x2,southH+corH,x2,H),"partition"),
        wall(11,"Bed2-Bath2",seg(x3,southH+corH,x3,H),"partition"),
        wall(12,"Bath2-Bed3",seg(x4,southH+corH,x4,H),"partition"),
        wall(13,"Bed3-Bed4",seg(x5b,southH+corH,x5b,H),"partition"),
        wall(14,"Bed4-Bed5",seg(x6,southH+corH,x6,H),"partition"),
    ]
    return {"layoutId":f"Layout-RES-{idx:03d}","outline":R(0,0,W,H),"rooms":r,"doors":d,"windows":w,"furniture":f,"mep":m,"structure":s}

# ── Blueprint H: with garage ──────────────────────────────────────────────────
def gen_garage(idx, W=18.0, H=10.0):
    W,H = rn(W),rn(H)
    gW = rn(W*0.33); southH = rn(H*0.5); corH = 1.0; northH = rn(H-southH-corH)
    entW = rn((W-gW)*0.2); livW = rn((W-gW)*0.45); kitW = rn(W-gW-entW-livW)
    bed1W = rn((W)*0.3); bat1W = rn(W*0.12); bed2W = rn(W-bed1W-bat1W)

    r = [
        room(1,"Garage",R(0,0,gW,southH),A(0,0,gW,southH)),
        room(2,"Entrance Hall",R(gW,0,gW+entW,southH),A(gW,0,gW+entW,southH)),
        room(3,"Living Room",R(gW+entW,0,gW+entW+livW,southH),A(gW+entW,0,gW+entW+livW,southH)),
        room(4,"Kitchen",R(gW+entW+livW,0,W,southH),A(gW+entW+livW,0,W,southH)),
        room(5,"Corridor",R(0,southH,W,southH+corH),A(0,southH,W,southH+corH)),
        room(6,"Master Bedroom",R(0,southH+corH,bed1W,H),A(0,southH+corH,bed1W,H)),
        room(7,"Master Bathroom",R(bed1W,southH+corH,bed1W+bat1W,H),A(bed1W,southH+corH,bed1W+bat1W,H)),
        room(8,"Bedroom 2",R(bed1W+bat1W,southH+corH,W,H),A(bed1W+bat1W,southH+corH,W,H)),
    ]
    d = [
        door(1,"wooden","Main Entrance",seg(rn(gW+0.2),0,rn(gW+2.2),0),2,"exterior"),
        door(2,"sliding","Garage Door",seg(rn(gW*0.1),0,rn(gW*0.1+2.5),0),1,"exterior"),
        door(3,"wooden","Garage to Entrance",seg(gW,rn(southH*0.35),gW,rn(southH*0.35+0.9)),1,2),
        door(4,"glass","Entrance to Living",seg(gW+entW,rn(southH*0.35),gW+entW,rn(southH*0.35+0.9)),2,3),
        door(5,"wooden","Entrance to Kitchen",seg(gW+entW,rn(southH*0.65),gW+entW,rn(southH*0.65+0.9)),2,4),
        door(6,"wooden","Living to Corridor",seg(rn(gW+entW+livW*0.3),southH,rn(gW+entW+livW*0.3+0.9),southH),3,5),
        door(7,"wooden","Kitchen to Corridor",seg(rn(gW+entW+livW+kitW*0.3),southH,rn(gW+entW+livW+kitW*0.3+0.9),southH),4,5),
        door(8,"wooden","Garage to Corridor",seg(rn(gW*0.3),southH,rn(gW*0.3+0.9),southH),1,5),
        door(9,"wooden","Corr to Master",seg(rn(bed1W*0.25),southH+corH,rn(bed1W*0.25+0.9),southH+corH),5,6),
        door(10,"wooden","Master to Bath",seg(bed1W,rn(southH+corH+northH*0.4),bed1W,rn(southH+corH+northH*0.4+0.9)),6,7),
        door(11,"wooden","Corr to Bed2",seg(rn(bed1W+bat1W+bed2W*0.2),southH+corH,rn(bed1W+bat1W+bed2W*0.2+0.9),southH+corH),5,8),
    ]
    w = [
        win(1,"casement","Garage S Win",seg(rn(gW*0.15),0,rn(gW*0.45),0),1),
        win(2,"casement","Living S Win",seg(rn(gW+entW+0.5),0,rn(gW+entW+2),0),3),
        win(3,"casement","Kitchen S Win",seg(rn(gW+entW+livW+0.5),0,rn(W-0.5),0),4),
        win(4,"casement","Kitchen E Win",seg(W,rn(southH*0.3),W,rn(southH*0.65)),4),
        win(5,"casement","Master N Win",seg(0.5,H,rn(bed1W-0.5),H),6),
        win(6,"casement","Master W Win",seg(0,rn(southH+corH+northH*0.25),0,rn(southH+corH+northH*0.65)),6),
        win(7,"awning","Bath N Win",seg(rn(bed1W+0.1),H,rn(bed1W+bat1W-0.1),H),7),
        win(8,"casement","Bed2 N Win",seg(rn(bed1W+bat1W+0.5),H,rn(W-0.5),H),8),
        win(9,"casement","Bed2 E Win",seg(W,rn(southH+corH+northH*0.3),W,rn(southH+corH+northH*0.7)),8),
    ]
    f = [
        furn(1,"Car Space 1",R(0.3,0.5,rn(gW*0.48),rn(southH-0.5)),1),
        furn(2,"Car Space 2",R(rn(gW*0.52),0.5,rn(gW-0.3),rn(southH-0.5)),1),
        furn(3,"Shoe Rack",R(rn(gW+0.2),0.2,rn(gW+entW-0.2),0.6),2),
        furn(4,"Bench",R(rn(gW+0.2),rn(southH*0.55),rn(gW+entW-0.2),rn(southH*0.55+0.4)),2),
        furn(5,"Sofa",R(rn(gW+entW+0.3),rn(southH*0.35),rn(gW+entW+livW*0.65),rn(southH*0.75)),3),
        furn(6,"Coffee Table",R(rn(gW+entW+0.5),rn(southH*0.77),rn(gW+entW+livW*0.6),rn(southH-0.5)),3),
        furn(7,"TV Stand",R(rn(gW+entW+livW*0.65),rn(southH-0.5),rn(gW+entW+livW-0.2),rn(southH-0.1)),3),
        furn(8,"Kitchen Counter S",R(rn(gW+entW+livW+0.2),0.2,rn(W-0.2),0.8),4),
        furn(9,"Kitchen Counter E",R(rn(W-0.7),0.2,rn(W-0.1),rn(southH-0.3)),4),
        furn(10,"Refrigerator",R(rn(gW+entW+livW+0.2),0.9,rn(gW+entW+livW+0.9),1.6),4),
        furn(11,"King Bed",R(0.4,rn(southH+corH+0.4),rn(bed1W*0.62),rn(southH+corH+northH*0.7)),6),
        furn(12,"Wardrobe",R(rn(bed1W*0.65),rn(southH+corH+0.3),rn(bed1W-0.2),rn(southH+corH+northH*0.8)),6),
        furn(13,"Toilet",R(rn(bed1W+0.2),rn(southH+corH+0.2),rn(bed1W+0.6),rn(southH+corH+0.85)),7),
        furn(14,"Sink",R(rn(bed1W+0.8),rn(southH+corH+0.2),rn(bed1W+bat1W-0.2),rn(southH+corH+0.65)),7),
        furn(15,"Shower",R(rn(bed1W+0.2),rn(H-1.4),rn(bed1W+bat1W-0.2),rn(H-0.2)),7),
        furn(16,"Queen Bed",R(rn(bed1W+bat1W+0.3),rn(southH+corH+0.4),rn(W-0.3),rn(southH+corH+northH*0.65)),8),
        furn(17,"Wardrobe Bed2",R(rn(bed1W+bat1W+0.3),rn(H-1.3),rn(W-0.3),rn(H-0.2)),8),
    ]
    m = [
        mep(1,"Living AC",R(rn(gW+entW+0.2),rn(southH-0.35),rn(gW+entW+1),rn(southH-0.1)),"hvac"),
        mep(2,"Electrical Panel",R(rn(W/2-0.3),rn(southH+0.1),rn(W/2+0.3),rn(southH+0.4)),"electrical"),
        mep(3,"Water Heater",R(rn(bed1W+0.2),rn(H-0.4),rn(bed1W+0.8),rn(H-0.1)),"plumbing"),
        mep(4,"Kitchen Exhaust",R(rn(W-2.5),rn(southH-0.35),rn(W-1.7),rn(southH-0.1)),"hvac"),
    ]
    s = [
        wall(1,"South Wall",seg(0,0,W,0),"load-bearing"),
        wall(2,"East Wall",seg(W,0,W,H),"load-bearing"),
        wall(3,"North Wall",seg(0,H,W,H),"load-bearing"),
        wall(4,"West Wall",seg(0,0,0,H),"load-bearing"),
        wall(5,"Garage-Ent Wall",seg(gW,0,gW,southH),"partition"),
        wall(6,"Ent-Liv Wall",seg(gW+entW,0,gW+entW,southH),"partition"),
        wall(7,"Liv-Kit Wall",seg(gW+entW+livW,0,gW+entW+livW,southH),"partition"),
        wall(8,"Corr S Wall",seg(0,southH,W,southH),"load-bearing"),
        wall(9,"Corr N Wall",seg(0,southH+corH,W,southH+corH),"load-bearing"),
        wall(10,"Master-Bath Wall",seg(bed1W,southH+corH,bed1W,H),"partition"),
        wall(11,"Bath-Bed2 Wall",seg(bed1W+bat1W,southH+corH,bed1W+bat1W,H),"partition"),
    ]
    return {"layoutId":f"Layout-RES-{idx:03d}","outline":R(0,0,W,H),"rooms":r,"doors":d,"windows":w,"furniture":f,"mep":m,"structure":s}

# ── Schedule: which blueprint, which params ───────────────────────────────────
# Each entry: (blueprint_fn, kwargs_dict)
def make_schedule():
    S = []

    # Compact (blueprint A): houses with small footprint
    for W,H in [(10,9),(11,8),(9,10),(10,10),(12,8),(11,9),(10,8),(9,9)]:
        S.append((gen_compact, dict(W=W, H=H)))

    # 3-bed rectangle (B): varied sizes
    dims_3bed = [(13,10),(14,11),(15,10),(12,11),(16,10),(14,12),(13,11),(15,11),
                 (12,10),(14,10),(16,11),(13,12),(15,12),(11,11),(12,12)]
    for W,H in dims_3bed:
        S.append((gen_3bed, dict(W=W, H=H)))

    # 4-bed (C): larger
    dims_4bed = [(18,12),(20,11),(19,12),(17,12),(21,11),(18,13),(20,12),(16,13),
                 (22,11),(19,11),(17,13),(21,12),(20,13)]
    for W,H in dims_4bed:
        S.append((gen_4bed, dict(W=W, H=H)))

    # Townhouse (D):
    for W,H in [(6,20),(7,20),(6,22),(7,22),(6,18),(8,18),(7,18),(6,24),(7,24),(8,20)]:
        S.append((gen_townhouse, dict(W=W, H=H)))

    # Open plan (E):
    for W,H in [(12,9),(13,8),(11,10),(14,9),(12,10),(13,9),(11,9),(14,8)]:
        S.append((gen_openplan, dict(W=W, H=H)))

    # L-outline (F):
    for W1,H1,W2,H2 in [(14,8,8,5),(16,9,9,5),(15,8,9,6),(12,8,7,5),
                          (14,9,8,6),(16,8,10,5),(13,8,8,5),(15,9,9,5)]:
        S.append((gen_l_outline, dict(W1=W1, H1=H1, W2=W2, H2=H2)))

    # 5-bed grand (G):
    for W,H in [(20,11),(22,11),(21,12),(20,12),(22,12),(21,11),(24,11),(20,13)]:
        S.append((gen_5bed, dict(W=W, H=H)))

    # With garage (H):
    for W,H in [(18,10),(20,10),(19,10),(18,11),(20,11),(17,10),(21,10),(19,11)]:
        S.append((gen_garage, dict(W=W, H=H)))

    return S

def write_house(idx, layout):
    path = os.path.join(OUT, f"house_{idx:03d}.json")
    with open(path, "w") as f:
        json.dump(layout, f, indent=2)
    print(f"Generated house_{idx:03d}.json")

if __name__ == "__main__":
    schedule = make_schedule()
    # Houses 001-008 replacements
    replace_indices = list(range(1, 9))
    # Houses 021-100
    new_indices = list(range(21, 101))
    all_indices = replace_indices + new_indices  # 88 total

    for i, idx in enumerate(all_indices):
        fn, kwargs = schedule[i % len(schedule)]
        layout = fn(idx, **kwargs)
        write_house(idx, layout)

    print(f"\nDone. Generated {len(all_indices)} files.")
