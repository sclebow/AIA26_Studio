// Client-side biophilic richness — computed LIVE from the layout so the green lens
// updates instantly after an edit (add a plant → the room's richness ticks up, no
// server round-trip). Mirrors nodes/insights/biophilic_audit.py.
//
// The 5 "leaves" are the Terrapin "14 Patterns of Biophilic Design" subset Sensi can
// honestly measure from a floor plan. Each carries its documented benefit (the research
// micro-copy shown in the fingerprint).

const NATURAL_MATERIALS = new Set(["wood", "cork", "stone", "natural", "bamboo", "rattan", "oak"]);
const SUNNY = new Set(["S", "SE", "SW", "E", "W"]);

export const LEAVES = [
  { key: "greenery",  label: "greenery",         benefit: "lowers stress, lifts mood" },
  { key: "daylight",  label: "daylight",         benefit: "sharper focus, better sleep" },
  { key: "freshAir",  label: "fresh air",        benefit: "more alertness" },
  { key: "materials", label: "natural material", benefit: "calming, lowers BP" },
  { key: "view",      label: "view / prospect",  benefit: "mental restoration" },
];

// Weights sum to 1.0; greenery leads (it's the core biophilic signal).
const WEIGHT = { greenery: 0.30, daylight: 0.20, freshAir: 0.20, materials: 0.15, view: 0.15 };

function furnitureByRoom(layout) {
  const m = {};
  for (const f of layout.furniture || []) {
    const rid = f.attributes?.roomId;
    if (rid) (m[rid] ||= []).push(f.attributes || {});
  }
  return m;
}

// → { byId: {roomId: rec}, byName: {name: rec} }
//   rec = { id, name, richness, status, plantCount, patterns: {key: {level, value}} }
export function biophilicProfile(layout) {
  if (!layout || !layout.rooms) return { byId: {}, byName: {} };
  const fbr = furnitureByRoom(layout);
  const byId = {}, byName = {};

  for (const room of layout.rooms) {
    const a = room.attributes || {};
    const glaz  = Number(a.glazingRatio || 0);
    const vent  = (a.ventilationType || "").toLowerCase();
    const floor = (a.floorMaterial || "").toLowerCase();
    const wall  = (a.wallMaterial || "").toLowerCase();
    const orient = (a.orientation || "").toUpperCase();
    const furn  = fbr[room.id] || [];
    const plantCount = furn.filter((f) =>
      (f.type || "").toLowerCase() === "plant" || (f.material || "").toLowerCase() === "natural").length;
    const naturalFloor = NATURAL_MATERIALS.has(floor);
    const naturalWall  = NATURAL_MATERIALS.has(wall);
    const naturalFurn  = furn.some((f) => NATURAL_MATERIALS.has((f.material || "").toLowerCase()));
    const hasNatural   = naturalFloor || naturalWall || naturalFurn;

    const patterns = {
      greenery:  { level: plantCount >= 2 ? 1 : plantCount === 1 ? 0.6 : 0,
                   value: plantCount ? `${plantCount} plant${plantCount > 1 ? "s" : ""}` : "none" },
      daylight:  { level: glaz >= 0.25 ? 1 : glaz >= 0.10 ? 0.5 : 0,
                   value: `${Math.round(glaz * 100)}%` },
      freshAir:  { level: vent === "natural" ? 1 : vent === "mixed" ? 0.5 : 0,
                   value: vent || "none" },
      materials: { level: hasNatural ? 1 : 0,
                   value: naturalFloor ? floor : naturalWall ? wall : naturalFurn ? "natural" : (floor || "—") },
      view:      { level: (glaz >= 0.15 && SUNNY.has(orient)) ? 1 : glaz >= 0.10 ? 0.6 : glaz > 0 ? 0.3 : 0,
                   value: glaz > 0 ? (orient || "window") : "none" },
    };

    let richness = 0;
    for (const k of Object.keys(WEIGHT)) richness += WEIGHT[k] * patterns[k].level;
    richness = Math.round(richness * 100) / 100;
    const status = richness >= 0.66 ? "thriving" : richness >= 0.40 ? "moderate" : "thirsty";

    const rec = { id: room.id, name: room.name, richness, status, plantCount, patterns };
    byId[room.id] = rec;
    if (room.name) byName[room.name] = rec;
  }
  return { byId, byName };
}

// Layout-wide biophilic headline (mean richness) for the lens banner.
export function biophilicHeadline(profile) {
  const recs = Object.values(profile.byId || {});
  if (!recs.length) return null;
  return Math.round((recs.reduce((s, r) => s + r.richness, 0) / recs.length) * 100) / 100;
}
