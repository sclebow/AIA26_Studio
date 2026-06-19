import { memo } from "react";
import { SC, SI } from "../lib/constants.js";
import { centroid, dims } from "../lib/geometry.js";
import { materialColor } from "../lib/materials.jsx";

// EditFocusLayer — the edit-guide as a FOCUS PULL. NOT a marker: when the agent edits
// the layout, the rest of the plan steps into shadow (a scrim) and a soft pool of light
// warms exactly where the change landed. The changed element itself lights up inside the
// pool (the new window's glass, added furniture's contour, a removed door's ghost-gap);
// room-wide edits (floor/wall material, ventilation) light the whole room — material edits
// glow in the actual finish colour. A breathing focal iris frames it, a sense glyph names
// the dimension, and per-sense life drifts within (air wafts motes, light glints). Detail
// (old → new + sense + impact) shows on hover; click opens the room. Nothing at rest;
// persists for the turn, clears on the next. See web/DESIGN_SYSTEM.md.

const CHANNEL = {
  floorMaterial: "floor · material", wallMaterial: "wall · material", furnitureMaterial: "object · material",
  furniture: "object", glazingRatio: "light", window: "light", windowPosition: "light",
  ventilationType: "air", door: "threshold",
};
const MATERIAL_ATTRS = new Set(["floorMaterial", "wallMaterial", "furnitureMaterial"]);
const ROOM_WIDE = new Set(["floorMaterial", "wallMaterial", "ventilationType", "glazingRatio"]);

// "visual+thermal" → [coreHue, ringHue]; both are real sense keys.
function senseHues(sense) {
  const parts = String(sense || "").split("+").map((s) => s.trim()).filter(Boolean);
  const core = SC[parts[0]] || "rgba(var(--fg-rgb),0.6)";
  return [core, SC[parts[1]] || core, parts[0]];
}

// build an SVG path from screen-space points (segment → open line, polygon → closed).
const elPath = (pts) => pts.map((p, i) => `${i ? "L" : "M"} ${p[0].toFixed(2)} ${p[1].toFixed(2)}`).join(" ") + (pts.length > 2 ? " Z" : "");

const FOCUS_CSS =
  ".efx-scrim{animation:efx-dim .7s ease forwards}" +
  "@keyframes efx-dim{from{opacity:0}to{opacity:var(--efx-scrim,0.2)}}" +
  // pool: bloom in, then breathe forever — the main "alive" beat
  ".efx-pool{transform-box:fill-box;transform-origin:center;animation:efx-bloom .8s cubic-bezier(.2,.7,.2,1) both,efx-poolbr 4.8s ease-in-out .9s infinite}" +
  "@keyframes efx-bloom{from{transform:scale(.25);opacity:0}to{transform:scale(1);opacity:1}}" +
  "@keyframes efx-poolbr{0%,100%{transform:scale(1);opacity:.88}50%{transform:scale(1.08);opacity:1}}" +
  // iris: a clearly visible breath (opacity + a touch of scale)
  ".efx-iris{transform-box:fill-box;transform-origin:center;animation:efx-fade .8s ease both,efx-irisbr 4.8s ease-in-out .8s infinite}" +
  "@keyframes efx-irisbr{0%,100%{opacity:.3;transform:scale(.97)}50%{opacity:.72;transform:scale(1.05)}}" +
  ".efx-elem{stroke-dasharray:1 1;stroke-dashoffset:1;animation:efx-draw .85s cubic-bezier(.4,0,.2,1) both,efx-elembr 4.6s ease-in-out .85s infinite}" +
  "@keyframes efx-draw{to{stroke-dashoffset:0}}" +
  "@keyframes efx-elembr{0%,100%{opacity:.6}50%{opacity:1}}" +
  ".efx-glyph{animation:efx-fade .8s ease .3s both,efx-glyphbr 5.4s ease-in-out .9s infinite}" +
  "@keyframes efx-glyphbr{0%,100%{opacity:.8}50%{opacity:1}}" +
  ".efx-mote{animation:efx-mote 3.6s ease-out infinite}" +
  "@keyframes efx-mote{0%{transform:translateY(0);opacity:0}25%{opacity:.65}100%{transform:translateY(-2.4px);opacity:0}}" +
  "@keyframes efx-fade{from{opacity:0}to{opacity:1}}" +
  "@media (prefers-reduced-motion:reduce){.efx-scrim,.efx-pool,.efx-iris,.efx-elem,.efx-glyph,.efx-mote{animation:none}.efx-elem{stroke-dasharray:none;stroke-dashoffset:0}.efx-pool,.efx-iris,.efx-glyph{opacity:1}}";

function EditFocusLayer({ layout, vb, fy, u = 0.1, diffs = [], onHover, onSelectRoom, senseScore, pulseKey = 0 }) {
  if (!diffs.length || !vb) return null;
  const rooms = layout?.rooms || [];
  const byId = new Map(), byName = new Map();
  for (const r of rooms) { if (r?.id) byId.set(r.id, r); if (r?.name) byName.set(r.name, r); }

  // resolve each diff to a focus (dedupe by room+channel — keep last).
  const focuses = new Map();
  for (const d of diffs) {
    if (!d || !d.attribute) continue;
    const room = (d.room_id && byId.get(d.room_id)) || (d.room_name && byName.get(d.room_name));
    if (!room || (room.geometry || []).length < 3) continue;
    const channel = CHANNEL[d.attribute] || "edit";
    focuses.set((room.id || room.name) + ":" + channel, { room, d, channel });
  }

  const scrimHoles = [], overlays = [];
  let i = 0;
  for (const { room, d, channel } of focuses.values()) {
    const [coreHue, , primary] = senseHues(d.sense_affected);
    const roomWide = ROOM_WIDE.has(d.attribute) || !d.el;

    // focus geometry — element-precise when we have it, else the room.
    let cx, cy, R, elScreen = null;
    if (d.el && d.el.length >= 2 && !roomWide) {
      elScreen = d.el.map(([x, y]) => [x, fy(y)]);
      const xs = elScreen.map((p) => p[0]), ys = elScreen.map((p) => p[1]);
      const span = Math.max(Math.max(...xs) - Math.min(...xs), Math.max(...ys) - Math.min(...ys));
      const a = d.at ? [d.at[0], fy(d.at[1])] : centroid(d.el).map((v, k) => (k ? fy(v) : v));
      cx = a[0]; cy = a[1];
      R = Math.max(span * 0.95 + u * 4, u * 6);
    } else {
      const c = centroid(room.geometry);
      cx = c[0]; cy = fy(c[1]);
      const { w, h } = dims(room.geometry);
      R = Math.max(w, h) * 0.58;
    }
    const key = `${pulseKey}:${room.id || room.name}:${channel}`;

    scrimHoles.push(<circle key={key} cx={cx} cy={cy} r={R * 1.06} fill="url(#efx-hole)" />);

    const score = senseScore && senseScore(room.name, primary);
    const hover = (e) => onHover && onHover({
      x: e.clientX, y: e.clientY, kind: "change", title: room.name,
      channel, from: d.old_value, to: d.new_value, sense: d.sense_affected, impact: score,
    });

    overlays.push(
      <g key={key}>
        {/* the soft pool of light at the change */}
        <circle className="efx-pool" cx={cx} cy={cy} r={R} fill={`url(#efx-pool-${i})`} style={{ mixBlendMode: "screen" }} />
        {/* room-wide wash, clipped to the room (material edits glow in the finish) */}
        {roomWide && (
          <g style={{ mixBlendMode: "screen" }} clipPath={`url(#efx-room-${i})`}>
            <circle cx={cx} cy={cy} r={R * 1.3} fill={`url(#efx-pool-${i})`} opacity={0.7} />
          </g>
        )}
        {/* the focal iris */}
        <circle className="efx-iris" cx={cx} cy={cy} r={R * 0.8} fill="none" stroke={coreHue} strokeWidth={u * 0.06} />
        {/* the changed element, lit precisely */}
        {elScreen && (
          <g style={{ mixBlendMode: "screen" }}>
            <path d={elPath(elScreen)} fill="none" stroke={coreHue} strokeWidth={u * 0.5} strokeLinecap="round" opacity={0.22} />
            <path className="efx-elem" d={elPath(elScreen)} pathLength="1" fill="none" stroke={coreHue} strokeWidth={u * 0.14}
              strokeLinecap="round" strokeDasharray={d.attribute === "door" ? `${u * 0.3} ${u * 0.25}` : undefined} />
          </g>
        )}
        {/* per-sense life: air wafts motes, light glints */}
        {d.attribute === "ventilationType" && [0, 1, 2].map((m) => (
          <circle key={m} className="efx-mote" style={{ animationDelay: `${m * 1.1}s`, mixBlendMode: "screen" }}
            cx={cx + (m - 1) * u * 0.5} cy={cy - u * 0.6} r={u * 0.18} fill={coreHue} />
        ))}
        {(channel === "light") && (
          <g className="efx-glyph" style={{ mixBlendMode: "screen" }}>
            <line x1={cx - u * 0.7} y1={cy - u * 0.9} x2={cx - u * 0.95} y2={cy - u * 1.5} stroke={coreHue} strokeWidth={u * 0.08} strokeLinecap="round" />
            <line x1={cx + u * 0.7} y1={cy - u * 0.9} x2={cx + u * 0.95} y2={cy - u * 1.5} stroke={coreHue} strokeWidth={u * 0.08} strokeLinecap="round" />
          </g>
        )}
        {/* the sense-glyph cue, near-white with a dark contrast halo */}
        <text className="efx-glyph" x={cx} y={cy + u * 0.5} textAnchor="middle" fontFamily="var(--font-mono)"
          fontSize={u * 1.5} fill="#FFF4E6" stroke="rgba(13,13,13,0.6)" strokeWidth={u * 0.06}
          paintOrder="stroke" style={{ paintOrder: "stroke" }}>{SI[primary] || ""}</text>
        {/* hover/click hit area — the one thing in the layer that takes the mouse */}
        <circle cx={cx} cy={cy} r={R * 0.75} fill="transparent" style={{ cursor: "pointer", pointerEvents: "all" }}
          onMouseMove={hover} onMouseLeave={() => onHover && onHover(null)}
          onClick={() => onSelectRoom && onSelectRoom(room.name)} />
      </g>
    );
    i += 1;
  }

  // per-focus gradient + room-clip defs (so the pool tint / room wash render).
  const defs = [];
  i = 0;
  for (const { room, d } of focuses.values()) {
    const [coreHue] = senseHues(d.sense_affected);
    const poolColor = MATERIAL_ATTRS.has(d.attribute) ? materialColor(d.new_value) : coreHue;
    defs.push(
      <radialGradient key={`pg${i}`} id={`efx-pool-${i}`} cx="50%" cy="50%" r="50%">
        <stop offset="0%" stopColor={poolColor} stopOpacity={0.36} />
        <stop offset="70%" stopColor={poolColor} stopOpacity={0.1} />
        <stop offset="100%" stopColor={poolColor} stopOpacity={0} />
      </radialGradient>
    );
    if (ROOM_WIDE.has(d.attribute) || !d.el) {
      const room2 = (d.room_id && byId.get(d.room_id)) || byName.get(d.room_name) || room;
      defs.push(
        <clipPath key={`rc${i}`} id={`efx-room-${i}`}>
          <path d={elPath(room2.geometry.map(([x, y]) => [x, fy(y)])) + " Z"} />
        </clipPath>
      );
    }
    i += 1;
  }

  return (
    // pointer-events:none so the dimmed plan beneath stays fully interactive (rooms
    // hover/click through it); only the focus hit-circles re-enable the mouse.
    <g className="efx-layer" style={{ pointerEvents: "none" }}>
      <style>{FOCUS_CSS}</style>
      <defs>
        <radialGradient id="efx-hole" cx="50%" cy="50%" r="50%">
          <stop offset="0%" stopColor="#000" />
          <stop offset="62%" stopColor="#000" />
          <stop offset="100%" stopColor="#fff" />
        </radialGradient>
        <mask id={`efx-mask-${pulseKey}`}>
          <rect x={vb.x} y={vb.y} width={vb.w} height={vb.h} fill="#fff" />
          {scrimHoles}
        </mask>
        {defs}
      </defs>
      {/* the rest of the plan gently recedes — light enough to stay fully readable */}
      <rect className="efx-scrim" x={vb.x} y={vb.y} width={vb.w} height={vb.h}
        fill="var(--bg)" opacity={0.2} mask={`url(#efx-mask-${pulseKey})`} />
      {overlays}
    </g>
  );
}

// Props stable across SensePlan's hover re-renders → memo skips the rebuild.
export default memo(EditFocusLayer);
