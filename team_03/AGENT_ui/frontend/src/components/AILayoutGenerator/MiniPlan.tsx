import React from 'react';
import type { LayoutJSON } from '../../types';

interface MiniPlanProps {
  layout: LayoutJSON;
  width?: number;
  height?: number;
  roomColor: string;
  outlineColor: string;
  bg: string;
}

/** Tiny 2D SVG thumbnail of a layout: outline + room polygons, scaled to fit.
 *  Architectural Y is up, so we flip Y for screen space. */
const MiniPlan: React.FC<MiniPlanProps> = ({
  layout,
  width = 124,
  height = 96,
  roomColor,
  outlineColor,
  bg,
}) => {
  const outline = (layout.outline ?? []) as [number, number][];
  const rooms = layout.rooms ?? [];
  const pts: [number, number][] =
    outline.length > 0
      ? outline
      : (rooms.flatMap(r => (r.geometry ?? []) as [number, number][]));

  if (pts.length === 0) {
    return <div style={{ width, height, background: bg, borderRadius: 6 }} />;
  }

  let minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity;
  for (const [x, y] of pts) {
    if (x < minX) minX = x;
    if (y < minY) minY = y;
    if (x > maxX) maxX = x;
    if (y > maxY) maxY = y;
  }
  const w = maxX - minX || 1;
  const h = maxY - minY || 1;
  const pad = 6;
  const scale = Math.min((width - 2 * pad) / w, (height - 2 * pad) / h);
  const ox = (width - w * scale) / 2;
  const oy = (height - h * scale) / 2;
  const tx = (x: number) => ox + (x - minX) * scale;
  const ty = (y: number) => height - (oy + (y - minY) * scale);
  const toPoints = (geo: [number, number][]) =>
    geo.map(([x, y]) => `${tx(x).toFixed(1)},${ty(y).toFixed(1)}`).join(' ');

  return (
    <svg width={width} height={height} style={{ display: 'block', background: bg, borderRadius: 6 }}>
      {rooms.map((r, i) =>
        (r.geometry ?? []).length > 0 ? (
          <polygon
            key={r.id ?? i}
            points={toPoints(r.geometry as [number, number][])}
            fill={roomColor}
            fillOpacity={0.32}
            stroke={outlineColor}
            strokeWidth={0.6}
            strokeOpacity={0.5}
          />
        ) : null
      )}
      {outline.length > 0 ? (
        <polyline points={toPoints(outline)} fill="none" stroke={outlineColor} strokeWidth={1.3} />
      ) : null}
    </svg>
  );
};

export default React.memo(MiniPlan);
