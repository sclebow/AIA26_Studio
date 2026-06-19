import { SC, scoreColor, scoreOpacity } from "../lib/constants.js";
import { polyPoints, centroid, dims, ringAnchor } from "../lib/geometry.js";

// Rooms. Split across the two tiers:
//   plan    → wall outline + label + an invisible hit area (click / hover)
//   comfort → fill tint (hue + intensity = health) + a corner COMFORT RING
//             (overall score as an animated arc + readable number)
// The ring sits in the room's top-right corner (off the furniture) and animates
// its fill when the displayed score changes (sense solo) via pathLength + a CSS
// stroke-dasharray transition. Hovering a room raises its attributes (onHover).
export default function RoomsLayer({ rooms = [], scoredByName, plan, comfort, activeRoom, setActiveRoom, focusRoom, setHoverRoom, focusSense, changedRooms = new Set(), pulseKey = 0, fy, u, onHover }) {
  return rooms.map((room) => {
    const geo = room.geometry || [];
    if (geo.length < 3) return null;
    const name = room.name;
    const r = scoredByName[name];
    // focusRoom = hoverRoom ?? activeRoom — so a chat-message hover lights the plan too
    const isFocus = name === (focusRoom ?? activeRoom);
    const pts = polyPoints(geo, fy);
    const { w, h, top, cx } = dims(geo);
    const [, cy] = centroid(geo);

    const lensScore = !r ? null : (focusSense ? (r.comfortScores?.[focusSense] ?? null) : (r.overallScore ?? null));
    const fillOp = lensScore == null ? 0.02 : scoreOpacity(lensScore) * 0.4;
    const score = comfort ? lensScore : null;
    const arcColor = focusSense ? SC[focusSense] : scoreColor(score ?? 0);
    const ringR = Math.max(u * 1.5, Math.min(w, h) * 0.13) * (isFocus ? 1.12 : 1);
    // Ideal top-right corner inset — correct for rectangular rooms. For concave
    // (L-shaped) rooms this bbox corner can land in a neighbour's cell, so snap it
    // back inside the actual polygon (ringAnchor; screen space = x, fy(y)).
    const screenPts = geo.map(([x, y]) => [x, fy(y)]);
    const [rx, ry] = ringAnchor(
      screenPts,
      [cx + w / 2 - ringR - u * 0.5, fy(top) + ringR + u * 0.5],
      ringR,
    );

    const hoverPayload = (e) => onHover && onHover({
      x: e.clientX, y: e.clientY, kind: "room", title: name,
      attrs: room.attributes || {}, score: r?.overallScore,
    });

    return (
      <g key={name} className={"spln-room" + (isFocus ? " is-focus" : "")}
        onClick={() => setActiveRoom(activeRoom === name ? null : name)}
        onMouseEnter={() => setHoverRoom && setHoverRoom(name)}
        onMouseMove={hoverPayload}
        onMouseLeave={() => { onHover && onHover(null); setHoverRoom && setHoverRoom(null); }}>
        {/* hit area + comfort tint */}
        {comfort
          ? <polygon className="spln-room-fill" points={pts} fill={focusSense ? SC[focusSense] : "rgb(var(--fg-rgb))"} fillOpacity={fillOp} />
          : plan ? <polygon points={pts} fill="transparent" /> : null}
        {plan && <polygon className="spln-room-wall" points={pts} fill="none" vectorEffect="non-scaling-stroke" />}
        {plan && <text className="spln-room-label" x={cx} y={fy(top) + u * 1.4} textAnchor="middle" fontSize={u * 1.1}>{name}</text>}

        {/* score-changed pulse — a brief expanding ring so an edit's effect is felt.
            Keyed by pulseKey so it remounts (replays) on each new edit turn. */}
        {comfort && score != null && changedRooms.has(name) && (
          <circle key={`pulse-${name}-${pulseKey}`} cx={rx} cy={ry} r={ringR} fill="none"
            stroke={arcColor} strokeWidth={u * 0.18} opacity={0}>
            <animate attributeName="r" values={`${ringR};${ringR * 2.7}`} dur="1.25s" begin="0s" repeatCount="2" fill="freeze" />
            <animate attributeName="opacity" values="0.85;0" dur="1.25s" begin="0s" repeatCount="2" fill="freeze" />
          </circle>
        )}

        {comfort && score != null && (
          <g className="spln-score">
            {/* full faint track */}
            <circle cx={rx} cy={ry} r={ringR} fill="rgba(13,13,13,0.66)" stroke="rgba(var(--fg-rgb),0.16)" strokeWidth={u * 0.16} />
            {/* solid progress arc — pathLength=1 so dasharray is the score fraction
                (no non-scaling-stroke: it would force dasharray into pixels and dot the ring) */}
            <circle className="spln-score-arc" cx={rx} cy={ry} r={ringR} pathLength="1" fill="none"
              stroke={arcColor} strokeWidth={u * 0.32} strokeLinecap="round"
              strokeDasharray={`${Math.max(0.0001, Math.min(1, score))} 1`}
              transform={`rotate(-90 ${rx} ${ry})`} />
            <text x={rx} y={ry} textAnchor="middle" dominantBaseline="central"
              fontFamily="var(--font-mono)" fontSize={ringR * 0.6} fill={arcColor}>{score.toFixed(2)}</text>
          </g>
        )}
      </g>
    );
  });
}
