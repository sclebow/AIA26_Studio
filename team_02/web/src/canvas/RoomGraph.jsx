// Shared room-graph node substrate, used by BOTH graph lenses (flow + topology).
// Rooms are nodes at their centroids; the edges on top are lens-specific. When
// backend graph_data is supplied (topology), nodes encode connectivity:
//   size = degree · dashed halo = structural/bridge · hollow = isolated.
// `showLabels` draws room names (turned on when the plan base is hidden, so an
// isolated graph stays legible).
export default function RoomGraph({ roomById, graphData = null, showLabels = false, fy, u }) {
  const meta = {};
  (graphData?.nodes || []).forEach((n) => { meta[n.id] = n; });
  const maxDeg = Math.max(1, ...Object.values(meta).map((n) => n.degree || 0));

  return Object.entries(roomById).map(([id, rm], i) => {
    const m = meta[id];
    const r = u * (0.6 + 0.5 * ((m?.degree || 0) / maxDeg));
    const isolated = m?.isolated, bridge = m?.is_bridge;
    const x = rm.c[0], y = fy(rm.c[1]);
    return (
      <g key={"node" + i}>
        {bridge && (
          <circle cx={x} cy={y} r={r + u * 0.55} fill="none" stroke="rgb(var(--fg-rgb))"
            strokeOpacity={0.4} strokeWidth={1} strokeDasharray="2 2" vectorEffect="non-scaling-stroke" />
        )}
        <circle cx={x} cy={y} r={r}
          fill={isolated ? "none" : "rgb(var(--fg-rgb))"} fillOpacity={isolated ? 0 : 0.5}
          stroke="rgb(var(--fg-rgb))" strokeOpacity={isolated ? 0.6 : 0.3}
          strokeWidth={isolated ? 1.5 : 1} strokeDasharray={isolated ? "2 2" : undefined}
          vectorEffect="non-scaling-stroke" />
        {showLabels && (
          <text className="spln-node-label" x={x} y={y - r - u * 0.5} textAnchor="middle" fontSize={u * 0.95}>{rm.name}</text>
        )}
      </g>
    );
  });
}
