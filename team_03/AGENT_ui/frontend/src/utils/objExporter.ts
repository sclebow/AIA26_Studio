/**
 * Wavefront OBJ (+ MTL) exporter for the current viewport layout.
 *
 * Output is a single ZIP file (<layoutId>_<date>.zip) containing:
 *   <baseName>.obj  — one group per visible layer, one object per element
 *   <baseName>.mtl  — one material per layer (neutral, Kd colors)
 *
 * The OBJ emits EACH LAYER'S vertices immediately before the faces that use
 * them (not all verts at the top), so Rhino / Blender split correctly by group.
 *
 * Coordinate basis — Z-up, metres, real layout origin (no centering):
 *   vertex = (layout.x, layout.y, elevation_z)
 * i.e. the floor plan lives in the XY plane, Z is vertical — matches
 * the Rhino/GH/JSON origin so re-imports land exactly right.
 */
import { strToU8, zipSync } from 'fflate';
import * as THREE from 'three';
import type { LayoutJSON, LayerVisibility } from '../types';
import {
  DOOR_HEIGHT, DOOR_THICKNESS,
  WIN_BOTTOM, WIN_HEIGHT, WIN_THICKNESS,
  type Pt,
  resolveHeight, assignOpenings, buildWallPieces, wallRectFromLine,
} from '../components/ThreeViewport/geometry';

// ── Per-layer material colors (Kd) ────────────────────────────────────
const LAYER_MTL: Record<string, { r: number; g: number; b: number; d?: number }> = {
  rooms:     { r: 0.72, g: 0.70, b: 0.79 },
  structure: { r: 0.60, g: 0.63, b: 0.68 },
  doors:     { r: 0.78, g: 0.54, b: 0.43 },
  windows:   { r: 0.56, g: 0.70, b: 0.84, d: 0.6 },
  furniture: { r: 0.62, g: 0.55, b: 0.77 },
  mep:       { r: 0.44, g: 0.68, b: 0.59 },
  outline:   { r: 0.49, g: 0.36, b: 1.00 },
};

const fv = (n: number) => (Object.is(n, -0) ? 0 : +n.toFixed(4));
const fmtV = (x: number, y: number, z: number) => `v ${fv(x)} ${fv(y)} ${fv(z)}`;

function sanitize(s: string): string {
  return (s || '').trim().replace(/\s+/g, '_').replace(/[^A-Za-z0-9_\-.]/g, '') || 'unnamed';
}

/** Strip the duplicated closing point of a closed ring (first ≈ last). */
function dedupe(poly: Pt[]): Pt[] {
  if (poly.length < 2) return poly.slice();
  const [ax, ay] = poly[0], [bx, by] = poly[poly.length - 1];
  return (Math.abs(ax - bx) < 1e-9 && Math.abs(ay - by) < 1e-9)
    ? poly.slice(0, -1) : poly.slice();
}

// ── Per-layer OBJ section builder ──────────────────────────────────────
// Vertices are emitted INSIDE each layer block (not at the global top).
// Each section is self-contained so Rhino/Blender can split by group.
class LayerBuilder {
  private lines: string[] = [];
  private vOffset: number;        // global vertex offset at the start of this layer
  private localV = 0;             // vertices added in this layer

  constructor(public readonly layerName: string, globalOffset: number) {
    this.vOffset = globalOffset;
    this.lines.push(`g ${layerName}`);
    this.lines.push(`usemtl ${layerName}`);
  }

  /** Emit one vertex; returns its 1-indexed global OBJ index. */
  private v(x: number, y: number, z: number): number {
    this.lines.push(fmtV(x, y, z));
    return this.vOffset + (++this.localV);
  }

  private face(idx: number[]) { this.lines.push(`f ${idx.join(' ')}`); }
  private lineEl(idx: number[]) { this.lines.push(`l ${idx.join(' ')}`); }

  object(name: string) { this.lines.push(`o ${name}`); }

  /** A flat horizontal polygon at elevation z (floor / cap). */
  flatFace(poly: Pt[], z: number) {
    const ring = dedupe(poly);
    if (ring.length < 3) return;
    const idx = ring.map(([x, y]) => this.v(x, y, z));
    const contour = ring.map(([x, y]) => new THREE.Vector2(x, y));
    const tris = THREE.ShapeUtils.triangulateShape(contour, []);
    for (const [a, c, d] of tris) this.face([idx[a], idx[c], idx[d]]);
  }

  /** A closed polyline at elevation z. */
  closedLine(poly: Pt[], z: number) {
    const ring = dedupe(poly);
    if (ring.length < 2) return;
    const idx = ring.map(([x, y]) => this.v(x, y, z));
    this.lineEl([...idx, idx[0]]);
  }

  /** Extrude a polygon from zBottom to zTop (closed solid with caps + sides). */
  extrude(poly: Pt[], zBottom: number, zTop: number) {
    const ring = dedupe(poly);
    if (ring.length < 3 || zTop <= zBottom) return;
    const bottom = ring.map(([x, y]) => this.v(x, y, zBottom));
    const top    = ring.map(([x, y]) => this.v(x, y, zTop));
    const contour = ring.map(([x, y]) => new THREE.Vector2(x, y));
    const tris = THREE.ShapeUtils.triangulateShape(contour, []);
    // Bottom cap (wound downward = CW for Z-up bottom-facing normal)
    for (const [a, c, d] of tris) this.face([bottom[a], bottom[d], bottom[c]]);
    // Top cap
    for (const [a, c, d] of tris) this.face([top[a], top[c], top[d]]);
    // Side quads
    const n = ring.length;
    for (let i = 0; i < n; i++) {
      const j = (i + 1) % n;
      this.face([bottom[i], bottom[j], top[j], top[i]]);
    }
  }

  /** Total vertices added in this layer (for updating the global offset). */
  get vertexCount() { return this.localV; }

  build(): string { return this.lines.join('\n') + '\n'; }
}

// ── Main export function ───────────────────────────────────────────────
export interface ObjExportResult {
  objText: string;
  mtlText: string;
  baseName: string;
  summary: { vertices: number; faces: number; layers: string[] };
}

export function layoutToObj(layout: LayoutJSON, layers: LayerVisibility): ObjExportResult {
  const baseName = `${sanitize(layout.layoutId || 'layout')}_${timestamp()}`;
  const sections: LayerBuilder[] = [];
  let globalOffset = 0;

  const beginLayer = (name: string) => {
    const lb = new LayerBuilder(name, globalOffset);
    sections.push(lb);
    return lb;
  };
  const endLayer = (lb: LayerBuilder) => { globalOffset += lb.vertexCount; };

  // ── outline ──
  if (layers.outline && (layout.outline?.length ?? 0) >= 2) {
    const lb = beginLayer('outline');
    lb.object('outline');
    lb.closedLine(layout.outline as Pt[], 0);
    endLayer(lb);
  }

  // ── rooms (flat floors) ──
  if (layers.rooms) {
    const lb = beginLayer('rooms');
    for (const room of layout.rooms || []) {
      lb.object(`${sanitize(room.id)}_${sanitize(room.name)}`);
      lb.flatFace(room.geometry as Pt[], 0);
    }
    endLayer(lb);
  }

  // ── structure (walls with openings) ──
  if (layers.structure) {
    const lb = beginLayer('structure');
    const byWall = assignOpenings(layout.structure, layout.doors, layout.windows);
    for (const wall of layout.structure || []) {
      const [p1, p2] = wall.geometry as Pt[];
      if (!p1 || !p2) continue;
      lb.object(`${sanitize(wall.id)}_${sanitize(wall.name)}`);
      for (const pc of buildWallPieces(p1, p2, byWall.get(wall.id) || []))
        lb.extrude(pc.rect, pc.zBottom, pc.zBottom + pc.depth);
    }
    endLayer(lb);
  }

  // ── doors ──
  if (layers.doors) {
    const lb = beginLayer('doors');
    for (const door of layout.doors || []) {
      const [p1, p2] = door.geometry as Pt[];
      if (!p1 || !p2) continue;
      lb.object(`${sanitize(door.id)}_${sanitize(door.name)}`);
      lb.extrude(wallRectFromLine(p1, p2, DOOR_THICKNESS), 0, DOOR_HEIGHT);
    }
    endLayer(lb);
  }

  // ── windows ──
  if (layers.windows) {
    const lb = beginLayer('windows');
    for (const win of layout.windows || []) {
      const [p1, p2] = win.geometry as Pt[];
      if (!p1 || !p2) continue;
      lb.object(`${sanitize(win.id)}_${sanitize(win.name)}`);
      lb.extrude(wallRectFromLine(p1, p2, WIN_THICKNESS), WIN_BOTTOM, WIN_BOTTOM + WIN_HEIGHT);
    }
    endLayer(lb);
  }

  // ── furniture ──
  if (layers.furniture) {
    const lb = beginLayer('furniture');
    for (const item of layout.furniture || []) {
      const h = resolveHeight(item.name, item.attributes as Record<string, unknown>, 0.9);
      lb.object(`${sanitize(item.id)}_${sanitize(item.name)}`);
      lb.extrude(item.geometry as Pt[], 0, h);
    }
    endLayer(lb);
  }

  // ── mep ──
  if (layers.mep) {
    const lb = beginLayer('mep');
    for (const item of layout.mep || []) {
      const h = resolveHeight(item.name, item.attributes as Record<string, unknown>, 0.5);
      lb.object(`${sanitize(item.id)}_${sanitize(item.name)}`);
      lb.extrude(item.geometry as Pt[], 0, h);
    }
    endLayer(lb);
  }

  const usedLayers = sections.map(s => s.layerName);
  const header =
    `# Spatial Flow — layout "${layout.layoutId}"\n` +
    `# ${new Date().toISOString()}\n` +
    `# Units: meters  Axis: Z-up  Floor in XY plane\n` +
    `# Layers: ${usedLayers.join(', ')}\n` +
    `mtllib ${baseName}.mtl\n\n`;

  const objText = header + sections.map(s => s.build()).join('\n');
  const totalVerts = globalOffset;
  const totalFaces = (objText.match(/^f /gm) || []).length;

  return {
    objText,
    mtlText: buildMtl(usedLayers, baseName),
    baseName,
    summary: { vertices: totalVerts, faces: totalFaces, layers: usedLayers },
  };
}

// ── MTL ───────────────────────────────────────────────────────────────
function buildMtl(usedLayers: string[], baseName: string): string {
  const lines = [
    `# Spatial Flow — ${baseName}`,
    `# ${new Date().toISOString()}`,
    '',
  ];
  for (const layer of usedLayers) {
    const c = LAYER_MTL[layer] || { r: 0.7, g: 0.7, b: 0.7 };
    lines.push(`newmtl ${layer}`);
    lines.push(`Ka 0.0 0.0 0.0`);
    lines.push(`Kd ${fv(c.r)} ${fv(c.g)} ${fv(c.b)}`);
    lines.push(`Ks 0.05 0.05 0.05`);
    lines.push(`Ns 16.0`);
    lines.push(`d ${fv(c.d ?? 1)}`);
    lines.push(`illum 2`);
    lines.push('');
  }
  return lines.join('\n');
}

// ── Timestamp ─────────────────────────────────────────────────────────
function timestamp(): string {
  const d = new Date();
  const p = (n: number) => String(n).padStart(2, '0');
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}_${p(d.getHours())}-${p(d.getMinutes())}`;
}

// ── ZIP + single download (fflate — already a transitive dep) ─────────
export function exportLayoutObj(layout: LayoutJSON, layers: LayerVisibility): ObjExportResult {
  const result = layoutToObj(layout, layers);
  const { objText, mtlText, baseName } = result;

  // Pack both files into one ZIP → single browser download, no user-gesture issues.
  const zip = zipSync({
    [`${baseName}.obj`]: strToU8(objText),
    [`${baseName}.mtl`]: strToU8(mtlText),
  }, { level: 6 });

  const blob = new Blob([zip], { type: 'application/zip' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = `${baseName}.zip`;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  setTimeout(() => URL.revokeObjectURL(url), 3000);

  return result;
}
