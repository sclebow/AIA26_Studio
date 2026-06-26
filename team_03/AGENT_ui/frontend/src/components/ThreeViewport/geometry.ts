/**
 * Shared layout → geometry rules for the 3D viewport AND the OBJ exporter.
 *
 * Everything here works in RAW layout coordinates (metres, [x, y] with origin
 * bottom-left, Z = height) and is Three.js-agnostic, so the renderer
 * (`FloorPlanRenderer.tsx`) and the exporter (`utils/objExporter.ts`) build the
 * exact same walls / openings / heights and can never drift apart.
 */
import type { LayoutJSON } from '../../types';

// ── Element dimensions (single source of truth for walls + openings) ───────
export const WALL_HEIGHT = 3.0;
export const WALL_THICKNESS = 0.2;
export const DOOR_HEIGHT = 2.2;
export const DOOR_THICKNESS = 0.08;
export const WIN_BOTTOM = 1.0;
export const WIN_HEIGHT = 1.0;
export const WIN_THICKNESS = 0.06;

export type Pt = [number, number];
export type Opening = { t1: number; t2: number; kind: 'door' | 'window' };
export type WallPiece = { rect: Pt[]; zBottom: number; depth: number };

// ── Height lookup ──────────────────────────────────────────────────────────
export const KEYWORD_HEIGHTS: Record<string, number> = {
  shelf: 1.6, rack: 1.6, shelving: 1.6,
  table: 0.85, desk: 0.85, counter: 0.85, workbench: 0.85, bench: 0.85,
  machine: 1.0, cnc: 1.2, conveyor: 0.7, press: 1.3,
  assembly: 0.9, packaging: 0.9, labeling: 0.85,
  toilet: 0.45, sink: 0.85, urinal: 0.6,
  hvac: 0.6, panel: 1.8, riser: 2.0, duct: 0.4,
  bin: 1.2,
};

export function resolveHeight(name: string, attrs: Record<string, unknown>, fallback: number): number {
  if (typeof attrs.height === 'number') return attrs.height;
  const lower = name.toLowerCase();
  for (const [kw, h] of Object.entries(KEYWORD_HEIGHTS)) {
    if (lower.includes(kw)) return h;
  }
  return fallback;
}

// ── Wall geometry helpers ────────────────────────────────────────────────
/** Compute the four corners of a wall segment given a centerline + thickness. */
export function wallRectFromLine(p1: Pt, p2: Pt, thickness: number): Pt[] {
  const dx = p2[0] - p1[0];
  const dy = p2[1] - p1[1];
  const len = Math.sqrt(dx * dx + dy * dy);
  if (len === 0) return [p1, p2, p2, p1];
  const nx = (-dy / len) * thickness / 2;
  const ny = (dx / len) * thickness / 2;
  return [
    [p1[0] + nx, p1[1] + ny],
    [p2[0] + nx, p2[1] + ny],
    [p2[0] - nx, p2[1] - ny],
    [p1[0] - nx, p1[1] - ny],
  ];
}

export function wallAxis(p1: Pt, p2: Pt) {
  const dx = p2[0] - p1[0], dy = p2[1] - p1[1];
  const len = Math.hypot(dx, dy) || 1;
  return { dir: [dx / len, dy / len] as Pt, len };
}

/** Signed projection of q onto the wall axis (distance along wall from p1). */
export function projParam(q: Pt, p1: Pt, dir: Pt) {
  return (q[0] - p1[0]) * dir[0] + (q[1] - p1[1]) * dir[1];
}

/** Perpendicular distance of q from the wall's infinite centerline. */
export function perpDist(q: Pt, p1: Pt, dir: Pt) {
  const t = projParam(q, p1, dir);
  const px = p1[0] + dir[0] * t, py = p1[1] + dir[1] * t;
  return Math.hypot(q[0] - px, q[1] - py);
}

/** Assign every door/window opening to the wall it lies on (collinear +
 *  overlapping), returning a map of wallId → openings (in wall-local 1D coords). */
export function assignOpenings(
  walls: LayoutJSON['structure'],
  doors: LayoutJSON['doors'],
  windows: LayoutJSON['windows'],
): Map<string, Opening[]> {
  const map = new Map<string, Opening[]>();
  const segs: { geo: Pt[]; kind: 'door' | 'window' }[] = [
    ...doors.map(d => ({ geo: d.geometry as Pt[], kind: 'door' as const })),
    ...windows.map(w => ({ geo: w.geometry as Pt[], kind: 'window' as const })),
  ];
  for (const s of segs) {
    if (!s.geo || s.geo.length < 2) continue;
    const [q1, q2] = s.geo;
    let best: { wallId: string; t1: number; t2: number } | null = null;
    let bestDist = Infinity;
    for (const w of walls) {
      const [p1, p2] = w.geometry as Pt[];
      const { dir, len } = wallAxis(p1, p2);
      const d1 = perpDist(q1, p1, dir), d2 = perpDist(q2, p1, dir);
      if (Math.max(d1, d2) > WALL_THICKNESS * 1.5) continue;   // not on this wall line
      let t1 = projParam(q1, p1, dir), t2 = projParam(q2, p1, dir);
      if (t1 > t2) { const tmp = t1; t1 = t2; t2 = tmp; }
      if (t2 < 0 || t1 > len) continue;                         // no overlap with extent
      const avg = (d1 + d2) / 2;
      if (avg < bestDist) {
        bestDist = avg;
        best = { wallId: w.id, t1: Math.max(0, t1), t2: Math.min(len, t2) };
      }
    }
    if (best) {
      if (!map.has(best.wallId)) map.set(best.wallId, []);
      map.get(best.wallId)!.push({ t1: best.t1, t2: best.t2, kind: s.kind });
    }
  }
  return map;
}

/** Decompose a wall into extrudable pieces: full-height solid segments between
 *  openings, plus sill/lintel blocks so each opening is a real void at its own
 *  height band (doors: gap up to DOOR_HEIGHT + lintel; windows: sill + band + lintel). */
export function buildWallPieces(p1: Pt, p2: Pt, openings: Opening[]): WallPiece[] {
  const { dir, len } = wallAxis(p1, p2);
  const pt = (t: number): Pt => [p1[0] + dir[0] * t, p1[1] + dir[1] * t];
  const piece = (a: Pt, b: Pt, zBottom: number, depth: number): WallPiece =>
    ({ rect: wallRectFromLine(a, b, WALL_THICKNESS), zBottom, depth });
  const pieces: WallPiece[] = [];

  // Merge opening spans for the full-height solid complement.
  const spans = openings
    .map(o => [Math.max(0, Math.min(o.t1, o.t2)), Math.min(len, Math.max(o.t1, o.t2))] as Pt)
    .filter(([a, b]) => b - a > 1e-3)
    .sort((a, b) => a[0] - b[0]);
  const merged: Pt[] = [];
  for (const sp of spans) {
    const last = merged[merged.length - 1];
    if (last && sp[0] <= last[1] + 1e-6) last[1] = Math.max(last[1], sp[1]);
    else merged.push([sp[0], sp[1]]);
  }
  let cursor = 0;
  for (const [a, b] of merged) {
    if (a - cursor > 1e-3) pieces.push(piece(pt(cursor), pt(a), 0, WALL_HEIGHT));
    cursor = Math.max(cursor, b);
  }
  if (len - cursor > 1e-3) pieces.push(piece(pt(cursor), pt(len), 0, WALL_HEIGHT));

  // Sill / lintel blocks above & below each opening band.
  for (const o of openings) {
    const a = Math.max(0, Math.min(o.t1, o.t2)), b = Math.min(len, Math.max(o.t1, o.t2));
    if (b - a <= 1e-3) continue;
    if (o.kind === 'door') {
      if (WALL_HEIGHT > DOOR_HEIGHT) pieces.push(piece(pt(a), pt(b), DOOR_HEIGHT, WALL_HEIGHT - DOOR_HEIGHT));
    } else {
      if (WIN_BOTTOM > 0) pieces.push(piece(pt(a), pt(b), 0, WIN_BOTTOM));
      const top = WIN_BOTTOM + WIN_HEIGHT;
      if (WALL_HEIGHT > top) pieces.push(piece(pt(a), pt(b), top, WALL_HEIGHT - top));
    }
  }
  return pieces;
}
