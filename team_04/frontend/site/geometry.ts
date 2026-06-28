/** 2D geometry helpers for the plan canvas (pure, no React). */
import type { Polygon } from '../api/types';

export interface BBox {
  minX: number;
  minY: number;
  maxX: number;
  maxY: number;
}

/** Bounding box over many polygons; returns a unit box if there is no geometry. */
export function computeBBox(polygons: Array<Polygon | null | undefined>): BBox {
  let minX = Infinity;
  let minY = Infinity;
  let maxX = -Infinity;
  let maxY = -Infinity;
  for (const poly of polygons) {
    if (!poly) continue;
    for (const p of poly) {
      const x = Number(p[0]);
      const y = Number(p[1]);
      if (Number.isNaN(x) || Number.isNaN(y)) continue;
      if (x < minX) minX = x;
      if (y < minY) minY = y;
      if (x > maxX) maxX = x;
      if (y > maxY) maxY = y;
    }
  }
  if (!Number.isFinite(minX)) return { minX: 0, minY: 0, maxX: 1, maxY: 1 };
  return { minX, minY, maxX, maxY };
}

export type Project = (p: number[]) => [number, number];

/**
 * Build a projector from world coords → SVG pixel coords.
 * Y is flipped so the plan reads north-up (world +y points up the screen).
 * Uniform scale preserves the building shapes' aspect ratio.
 */
export function makeProjector(bbox: BBox, width: number, height: number, pad = 24): Project {
  const w = Math.max(1e-6, bbox.maxX - bbox.minX);
  const h = Math.max(1e-6, bbox.maxY - bbox.minY);
  const scale = Math.min((width - 2 * pad) / w, (height - 2 * pad) / h);
  // Centre the drawing inside the viewport.
  const offX = pad + (width - 2 * pad - w * scale) / 2;
  const offY = pad + (height - 2 * pad - h * scale) / 2;
  return (p: number[]) => {
    const x = offX + (Number(p[0]) - bbox.minX) * scale;
    const y = height - (offY + (Number(p[1]) - bbox.minY) * scale); // flip Y
    return [x, y];
  };
}

/** SVG path "M … L … Z" for a closed polygon. */
export function polygonToPath(poly: Polygon, project: Project): string {
  if (!poly || poly.length === 0) return '';
  const pts = poly.map((p) => {
    const [x, y] = project(p);
    return `${x.toFixed(2)},${y.toFixed(2)}`;
  });
  return `M ${pts.join(' L ')} Z`;
}

/** Centroid of a polygon in world coords (vertex average — matches the backend). */
export function centroidOf(poly: Polygon): [number, number] {
  if (!poly || poly.length === 0) return [0, 0];
  let sx = 0;
  let sy = 0;
  for (const p of poly) {
    sx += Number(p[0]);
    sy += Number(p[1]);
  }
  return [sx / poly.length, sy / poly.length];
}

/** Stable fill colour per building footprint family. */
export const BUILDING_TYPE_COLORS: Record<string, string> = {
  I: '#3498db',
  L: '#e67e22',
  T: '#9b59b6',
  U: '#16a085',
  H: '#e74c3c',
  Y: '#f1c40f',
  X: '#1abc9c',
  O: '#34495e',
};

export function buildingColor(buildingType: string | null | undefined): string {
  if (!buildingType) return '#7f8c8d';
  return BUILDING_TYPE_COLORS[buildingType.toUpperCase()] ?? '#7f8c8d';
}
