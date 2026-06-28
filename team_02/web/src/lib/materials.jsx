// Material → colour lookup for the floor plan. Each material maps to a colour, used to
// tint walls (WallsLayer) and to glow the room in its new finish when a material change
// lands (EditFocusLayer) — in Sensi's soft glowing idiom, never a wall-to-wall fill.

const PALETTE = {
  wood:      "#b07a47",
  oak:       "#b88a52",
  hardwood:  "#a9743f",
  laminate:  "#c79a63",
  natural:   "#a98f6b",
  cork:      "#c08a55",
  ceramic:   "#cdd6dc",
  tile:      "#c4d0d8",
  porcelain: "#d2dadf",
  marble:    "#e2e5ea",
  stone:     "#a8a8a0",
  concrete:  "#9a9a9a",
  carpet:    "#9a86a0",
  fabric:    "#9a8d80",
  vinyl:     "#b9b2a6",
  plaster:   "#d8d2c8",
  brick:     "#b5613f",
  default:   "#9aa0a6",
};

const SYNONYMS = { timber: "wood", parquet: "wood", "engineered wood": "wood", granite: "stone", terrazzo: "stone", rug: "carpet", linoleum: "vinyl" };

export function materialKey(material) {
  if (!material) return "default";
  const raw = String(material).trim().toLowerCase();
  if (PALETTE[raw]) return raw;
  if (SYNONYMS[raw]) return SYNONYMS[raw];
  const hit = Object.keys(PALETTE).find((k) => k !== "default" && raw.includes(k));
  return hit || "default";
}

export function materialColor(material) {
  return PALETTE[materialKey(material)];
}

export function materialLabel(material) {
  if (!material || material === "unset") return "—";
  return String(material);
}
