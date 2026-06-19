import { memo, useMemo } from "react";
import { deriveWalls } from "../lib/walls.js";
import { materialColor, materialLabel } from "../lib/materials.jsx";

// Structural shell as luminous CAD walls. Walls are DERIVED from the room polygons +
// outline (the `structure` array is sparse), then each unique segment is rendered as a
// band: a wide low-opacity "mass" stroke whose width is in MODEL units (so it scales
// with zoom = real wall thickness) UNDER a crisp non-scaling centerline. Each wall is an
// addressable <g data-wall-id> so edit tools can target it. Door/window gaps are knocked
// out by the bg-coloured masks painted on top in OpeningsLayer.
//
// When a segment carries a wall MATERIAL (room.attributes.wallMaterial, set by the
// change_wall_material tool), its mass stroke is softly TINTED by that material — the same
// subtle glowing idiom as the edit-guide (focus pull, EditFocusLayer), never a heavy fill.
// The wall that just changed also emits a slow ripple from its midpoint.
//
// NOTE: never put vectorEffect="non-scaling-stroke" on the mass stroke — that would lock
// it to pixels and the wall would stop reading as thickness.
const BAND = { ext: 0.12, in: 0.08 }; // model metres

function WallsLayer({ outline = [], rooms = [], structure = [], fy, u = 0.1, diffs = [], onHover }) {
  const { segments } = useMemo(
    () => deriveWalls({ outline, rooms, structure }),
    [outline, rooms, structure],
  );

  // Rooms whose wall material changed this turn → pulse any wall segment they touch.
  const changedRoomIds = useMemo(() => {
    const s = new Set();
    for (const d of diffs) if (d?.attribute === "wallMaterial" && d.room_id) s.add(d.room_id);
    return s;
  }, [diffs]);

  return (
    <g className="spln-walls">
      {segments.map((s) => {
        const ext = s.kind === "ext";
        const x1 = s.x1, y1 = fy(s.y1), x2 = s.x2, y2 = fy(s.y2);
        const tint = s.material ? materialColor(s.material) : null;
        const changed = !!(s.rooms && s.rooms.some((r) => changedRoomIds.has(r)));
        const mx = (x1 + x2) / 2, my = (y1 + y2) / 2;

        const hover = onHover
          ? (e) => onHover({
              x: e.clientX, y: e.clientY, kind: "wall",
              title: ext ? "exterior wall" : "interior wall",
              material: materialLabel(s.material),
              sides: (s.materials || []).map((m) => materialLabel(m.material)),
            })
          : undefined;

        return (
          <g key={s.id} data-wall-id={s.id} data-kind={s.kind}
            onMouseMove={hover} onMouseLeave={() => onHover && onHover(null)}>
            <line className={ext ? "spln-wall-ext-mass" : "spln-wall-in-mass"}
              x1={x1} y1={y1} x2={x2} y2={y2}
              strokeWidth={ext ? BAND.ext : BAND.in} strokeLinecap="round"
              {...(tint ? { stroke: tint, style: { opacity: 0.5 } } : {})} />
            <line className={ext ? "spln-wall-ext" : "spln-wall-in"}
              x1={x1} y1={y1} x2={x2} y2={y2} vectorEffect="non-scaling-stroke" />

            {/* change ripple — only the wall(s) that just changed material */}
            {changed && tint && (
              <>
                <circle cx={mx} cy={my} r={u * 0.5} fill={tint} opacity={0.9} />
                <circle cx={mx} cy={my} r={u * 0.5} fill="none" stroke={tint} strokeWidth={u * 0.1}>
                  <animate attributeName="r" values={`${u * 0.5};${u * 2.4}`} dur="2.6s" repeatCount="indefinite" />
                  <animate attributeName="opacity" values="0.5;0" dur="2.6s" repeatCount="indefinite" />
                </circle>
              </>
            )}
          </g>
        );
      })}
    </g>
  );
}

// Pure + props stable across hover (refs from `layout`, `fy`/`diffs` memoized) → skip the
// per-mousemove re-render that SensePlan's hover state would otherwise trigger.
export default memo(WallsLayer);
