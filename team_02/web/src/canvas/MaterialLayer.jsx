import { SC } from "../lib/constants.js";
import { centroid, dims } from "../lib/geometry.js";
import { materialColor, materialLabel, materialOrbFill } from "../lib/materials.jsx";

// MaterialLayer — one soft 3D material orb floating in each room (Sensi's galaxy
// idiom), instead of wall-to-wall fills. At rest an orb is just the material
// (sphere + faint halo + faint mono label). When the latest edit changed THIS
// room's material, the orb emits a slow ripple and an affected-sense satellite
// orbits it. Full old → new detail shows on hover via the plan tooltip.
export default function MaterialLayer({ rooms = [], fy, u, diff = null, onHover }) {
  const changedIsMaterial = diff && /material/i.test(diff.attribute || "");
  const changedId = diff?.room_id, changedName = diff?.room_name;

  return rooms.map((room) => {
    const geo = room.geometry || [];
    if (geo.length < 3) return null;
    const mat = room.attributes?.floorMaterial;
    const c = centroid(geo);
    const cx = c[0], cy = fy(c[1]);
    const { w, h } = dims(geo);
    const R = Math.max(u * 1.4, Math.min(Math.min(w, h) * 0.12, u * 2.6));

    const isChanged = changedIsMaterial && ((changedId && room.id === changedId) || (changedName && room.name === changedName));
    const sense = isChanged ? diff.sense_affected : null;
    const senseColor = (sense && SC[sense]) || materialColor(mat);

    const hover = (e) => onHover && onHover({
      x: e.clientX, y: e.clientY, kind: "material", title: room.name,
      material: materialLabel(mat),
      changed: isChanged,
      from: isChanged ? materialLabel(diff.old_value) : null,
      to: isChanged ? materialLabel(diff.new_value) : null,
      sense,
    });

    return (
      <g key={"mat-" + (room.id || room.name)} className="mat-orb"
        onMouseMove={hover} onMouseLeave={() => onHover && onHover(null)}>
        {/* faint halo */}
        <circle cx={cx} cy={cy} r={R * 1.9} fill={materialColor(mat)} opacity={0.07} />

        {/* change ripple — slow, subtle */}
        {isChanged && (
          <circle cx={cx} cy={cy} r={R} fill="none" stroke={senseColor} strokeWidth={u * 0.1} opacity={0.5}>
            <animate attributeName="r" values={`${R};${R * 3}`} dur="2.6s" repeatCount="indefinite" />
            <animate attributeName="opacity" values="0.45;0" dur="2.6s" repeatCount="indefinite" />
          </circle>
        )}

        {/* the orb */}
        <circle cx={cx} cy={cy} r={R} fill={materialOrbFill(mat)}
          stroke="rgba(var(--fg-rgb),0.18)" strokeWidth={u * 0.04} />
        {/* specular highlight */}
        <ellipse cx={cx - R * 0.34} cy={cy - R * 0.4} rx={R * 0.26} ry={R * 0.16}
          fill="#ffffff" opacity={0.45} />

        {/* affected-sense satellite — only when this room's material just changed */}
        {sense && (
          <g>
            <circle cx={cx + R * 1.7} cy={cy} r={u * 0.5} fill={senseColor} />
            <animateTransform attributeName="transform" type="rotate"
              from={`0 ${cx} ${cy}`} to={`360 ${cx} ${cy}`} dur="6s" repeatCount="indefinite" />
          </g>
        )}

        {/* faint material label */}
        <text x={cx} y={cy + R + u * 1.15} textAnchor="middle"
          fontFamily="var(--font-mono)" fontSize={u * 0.82} fill="rgba(var(--fg-rgb),0.5)">
          {materialLabel(mat)}
        </text>
      </g>
    );
  });
}
