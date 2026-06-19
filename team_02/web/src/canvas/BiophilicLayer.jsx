import { memo, useMemo } from "react";
import { polyPoints, centroid, dims } from "../lib/geometry.js";
import { biophilicProfile } from "../lib/biophilic.js";

// The green lens. Each room glows green by its biophilic richness; thriving rooms grow
// a few drifting leaf particles; a plant-less room pulses a "+leaf" invite (one tap adds
// greenery via the add_plant edit tool); a room that just got greener blooms a ripple.
// Richness is computed CLIENT-SIDE from the live layout, so it updates the instant an
// edit lands — no dependency on the biophilic action having re-run.
const GREEN = "124,179,66";   // #7CB342
const LEAF  = "174,224,106";  // #AEE06A

// Deterministic leaf scatter (golden-angle) — no Math.random so it doesn't reshuffle on render.
function leaves(cx, cy, w, h, u, count) {
  const out = [];
  for (let i = 0; i < count; i++) {
    const a = i * 2.39996323;
    const px = cx + Math.cos(a) * w * 0.26;
    const py = cy + Math.sin(a * 1.3) * h * 0.26;
    const dur = 3 + (i % 3);
    out.push(
      <circle key={i} cx={px} cy={py} r={u * 0.26} fill={`rgb(${LEAF})`}>
        <animate attributeName="cy" values={`${py};${py - u * 0.7};${py}`} dur={`${dur}s`} repeatCount="indefinite" />
        <animate attributeName="opacity" values="0.35;0.9;0.35" dur={`${dur}s`} repeatCount="indefinite" />
      </circle>,
    );
  }
  return out;
}

function BiophilicLayer({ layout, fy, u = 0.1, onGreen, changedRooms = new Set(), pulseKey = 0 }) {
  const profile = useMemo(() => biophilicProfile(layout), [layout]);
  // Rendered ON TOP of the plan: the glow + particles are pointer-events:none so room
  // selection still falls through to RoomsLayer's hit area; only the +leaf invite is
  // interactive (so a bare room can be greened with one tap). Opacity is capped so the
  // furniture/window symbols underneath still read through the green wash.
  return (
    <g className="bio-layer">
      {(layout.rooms || []).map((room) => {
        const geo = room.geometry || [];
        if (geo.length < 3) return null;
        const rec = profile.byId[room.id];
        if (!rec) return null;
        const pts = polyPoints(geo, fy);
        const c = centroid(geo);
        const cx = c[0], cy = fy(c[1]);
        const { w, h } = dims(geo);
        const op = 0.05 + 0.34 * rec.richness;          // glow opacity by richness (capped)
        const thriving = rec.richness >= 0.66;
        const bare = rec.plantCount === 0;
        const changed = changedRooms.has(room.name);

        return (
          <g key={room.id} className="bio-room" style={{ pointerEvents: "none" }}>
            <polygon className="bio-fill" points={pts} fill={`rgb(${GREEN})`} fillOpacity={op} />

            {thriving && leaves(cx, cy, w, h, u, 4)}

            {bare && (
              <g className="bio-invite" style={{ cursor: "pointer", pointerEvents: "auto" }}
                onClick={(e) => { e.stopPropagation(); onGreen && onGreen(rec.name); }}>
                <circle cx={cx} cy={cy} r={u * 1.5} fill={`rgba(${GREEN},0.10)`}
                  stroke={`rgba(${GREEN},0.7)`} strokeWidth={u * 0.12}>
                  <animate attributeName="r" values={`${u * 1.5};${u * 2.1};${u * 1.5}`} dur="2.4s" repeatCount="indefinite" />
                </circle>
                <text x={cx} y={cy} textAnchor="middle" dominantBaseline="central" pointerEvents="none"
                  fontFamily="var(--font-mono)" fontSize={u * 1.6} fill={`rgb(${LEAF})`}>+</text>
              </g>
            )}

            {changed && (
              <circle key={`bloom-${room.id}-${pulseKey}`} cx={cx} cy={cy} r={u * 1.5} fill="none"
                stroke={`rgb(${LEAF})`} strokeWidth={u * 0.2} opacity={0}>
                <animate attributeName="r" values={`${u * 1.5};${u * 5}`} dur="1.6s" repeatCount="2" fill="freeze" />
                <animate attributeName="opacity" values="0.8;0" dur="1.6s" repeatCount="2" fill="freeze" />
              </circle>
            )}
          </g>
        );
      })}
    </g>
  );
}

export default memo(BiophilicLayer);
