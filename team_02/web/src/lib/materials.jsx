// Material legibility for the floor plan (Phase 0, deterministic — no AI).
//
// Materials are shown as small floating ORBS (one per room) in Sensi's galaxy/orb
// language — NOT wall-to-wall fills. Each material maps to a colour; MaterialDefs
// emits a radial gradient per material (highlight → base → shadow) so the orb reads
// as a soft 3D sphere. materialOrbFill() returns url(#mat-orb-<key>).

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

// SVG fill ref for an orb, e.g. url(#mat-orb-wood).
export function materialOrbFill(material) {
  return `url(#mat-orb-${materialKey(material)})`;
}

// ── colour helpers (lerp toward white / black for the orb's highlight + shadow) ──
function hexToRgb(hex) {
  const h = hex.replace("#", "");
  return [parseInt(h.slice(0, 2), 16), parseInt(h.slice(2, 4), 16), parseInt(h.slice(4, 6), 16)];
}
function clampByte(n) { return Math.max(0, Math.min(255, Math.round(n))); }
function toHex(r, g, b) { return "#" + [r, g, b].map((v) => clampByte(v).toString(16).padStart(2, "0")).join(""); }
function shade(hex, amt) {            // amt>0 → lighter, amt<0 → darker
  const [r, g, b] = hexToRgb(hex);
  const t = Math.abs(amt), tgt = amt > 0 ? 255 : 0;
  return toHex(r + (tgt - r) * t, g + (tgt - g) * t, b + (tgt - b) * t);
}

// One radial gradient per material, giving each orb a soft spherical shading.
// Drop <MaterialDefs/> once inside the plan SVG.
export function MaterialDefs() {
  return (
    <defs>
      {Object.entries(PALETTE).map(([key, color]) => (
        <radialGradient key={key} id={`mat-orb-${key}`} cx="36%" cy="30%" r="72%">
          <stop offset="0%" stopColor={shade(color, 0.55)} />
          <stop offset="52%" stopColor={color} />
          <stop offset="100%" stopColor={shade(color, -0.45)} />
        </radialGradient>
      ))}
    </defs>
  );
}
