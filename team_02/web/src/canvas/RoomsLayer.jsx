import { SC, scoreOpacity } from "../lib/constants.js";
import { polyPoints, centroid, dims } from "../lib/geometry.js";
import SenseSignature from "../components/SenseSignature.jsx";

// Room polygons: fill by active lens (hue + intensity = health), wall stroke,
// label, and the per-room sense signature (focused room blooms slightly). Click
// pins the room on the selection bus.
export default function RoomsLayer({ rooms = [], scoredByName, activeRoom, setActiveRoom, focusSense, layers, fy, u }) {
  return rooms.map((room) => {
    const geo = room.geometry || [];
    if (geo.length < 3) return null;
    const name = room.name;
    const r = scoredByName[name];
    const isFocus = name === activeRoom;
    const lensScore = !r ? null : (focusSense ? (r.comfortScores?.[focusSense] ?? null) : (r.overallScore ?? null));
    const fillOp = (!layers.fill || lensScore == null) ? 0.02 : scoreOpacity(lensScore) * 0.4;
    const { w, h, top, cx } = dims(geo);
    const [, cy] = centroid(geo);
    const size = Math.min(w, h) * 0.26 * (isFocus ? 1.18 : 1);
    return (
      <g key={name} className={"spln-room" + (isFocus ? " is-focus" : "")}
        onClick={() => setActiveRoom(activeRoom === name ? null : name)}>
        <polygon className="spln-room-fill" points={polyPoints(geo, fy)}
          fill={focusSense ? SC[focusSense] : "rgb(var(--fg-rgb))"} fillOpacity={fillOp} />
        <polygon className="spln-room-wall" points={polyPoints(geo, fy)} fill="none" vectorEffect="non-scaling-stroke" />
        <text className="spln-room-label" x={cx} y={fy(top) + u * 1.4} textAnchor="middle" fontSize={u * 1.1}>{name}</text>
        {r && layers.signatures && (
          <g opacity={layers.flow ? 0.35 : 1}>
            <SenseSignature scores={r.comfortScores} x={cx - size / 2} y={fy(cy) - size / 2} size={size}
              showGlyphs={false} activeSense={focusSense} title={name} calm={!isFocus} />
          </g>
        )}
      </g>
    );
  });
}
