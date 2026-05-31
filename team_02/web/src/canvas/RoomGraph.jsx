// Shared room-graph node substrate. Surfaces ALL the topology-node data so none
// is buried:  size = degree · dashed halo = structural/bridge · hollow = isolated
// · soft glow = betweenness (circulation importance) · fill = connected-component
// zone (when the plan splits into >1). CLICK a node to toggle its sense
// constellation (multi); HOVER reveals its metrics (degree/betweenness/role/type).
const ZONE_COLORS = ["#5B7FA6", "#A6735B", "#6FA65B", "#8A5BA6", "#A6A05B"]; // muted, distinct from sense hues

export default function RoomGraph({ roomById, graphData = null, showLabels = false, expandedRooms, onToggleRoom, onHoverNode, fy, u }) {
  const meta = {};
  (graphData?.nodes || []).forEach((n) => { meta[n.id] = n; });
  const maxDeg = Math.max(1, ...Object.values(meta).map((n) => n.degree || 0));
  const components = graphData?.metrics?.components || [];
  const zoneOf = {};
  if (components.length > 1) components.forEach((names, zi) => names.forEach((nm) => { zoneOf[nm] = zi; }));

  return Object.entries(roomById).map(([id, rm], i) => {
    const m = meta[id] || {};
    const r = u * (0.6 + 0.5 * ((m.degree || 0) / maxDeg));
    const bet = m.betweenness || 0;
    const isolated = m.isolated, bridge = m.is_bridge;
    const zi = zoneOf[rm.name];
    const zoneCol = zi != null ? ZONE_COLORS[zi % ZONE_COLORS.length] : null;
    const fill = zoneCol || "rgb(var(--fg-rgb))";
    const expanded = expandedRooms?.has?.(rm.name);
    const role = bridge ? "structural" : isolated ? "isolated" : "";
    const x = rm.c[0], y = fy(rm.c[1]);
    const hoverInfo = (e) => onHoverNode && onHoverNode({
      x: e.clientX, y: e.clientY, kind: "node", name: rm.name, type: m.room_type,
      degree: m.degree ?? 0, betweenness: bet.toFixed(2), role,
    });
    return (
      <g key={"node" + i} className="spln-gnode" style={onToggleRoom ? { cursor: "pointer" } : undefined}
        onClick={() => onToggleRoom && onToggleRoom(rm.name)} onMouseMove={hoverInfo} onMouseLeave={() => onHoverNode && onHoverNode(null)}>
        {bet > 0 && <circle cx={x} cy={y} r={r + u * (0.8 + bet * 3)} fill={fill} fillOpacity={0.08 + bet * 0.3} />}
        {bridge && <circle cx={x} cy={y} r={r + u * 0.55} fill="none" stroke="rgb(var(--fg-rgb))" strokeOpacity={0.4} strokeWidth={1} strokeDasharray="2 2" vectorEffect="non-scaling-stroke" />}
        <circle cx={x} cy={y} r={r + u * 1.1} fill="transparent" />
        <circle cx={x} cy={y} r={r} fill={isolated ? "none" : fill} fillOpacity={isolated ? 0 : (expanded ? 0.9 : 0.55)}
          stroke={zoneCol || "rgb(var(--fg-rgb))"} strokeOpacity={expanded ? 1 : (isolated ? 0.6 : 0.4)}
          strokeWidth={expanded ? 2.2 : 1} strokeDasharray={isolated ? "2 2" : undefined} vectorEffect="non-scaling-stroke" />
        {(showLabels || expanded) && (
          <text className="spln-node-label" x={x} y={y - r - u * 0.8} textAnchor="middle" fontSize={u * 0.95}>{rm.name}</text>
        )}
      </g>
    );
  });
}
