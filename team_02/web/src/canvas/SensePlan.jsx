import { useEffect, useMemo, useState } from "react";
import * as api from "../api/client.js";
import { SI } from "../lib/constants.js";
import { useSelection } from "../lib/selection.jsx";
import { centroid, dims } from "../lib/geometry.js";
import { VALENCE } from "../lib/relationships.js";
import WallsLayer from "./WallsLayer.jsx";
import RoomsLayer from "./RoomsLayer.jsx";
import OpeningsLayer from "./OpeningsLayer.jsx";
import FurnitureLayer from "./FurnitureLayer.jsx";
import RoomGraph from "./RoomGraph.jsx";
import GraphEdges from "./GraphEdges.jsx";
import SenseHub from "./SenseHub.jsx";

/*
 * SensePlan — the floor plan as one bespoke SVG data-canvas, in two tiers:
 *   BASE  : architecture (walls / rooms / openings / furniture), gated by
 *           `layers.plan`. Turn it off to isolate the graph. Hover raises attributes.
 *   LENSES: comfort (fill + score ring); and `graph` — ONE unified room
 *           relationship graph: unified edges (GraphEdges) + nodes (RoomGraph) +
 *           per-room sense constellations (SenseHub), click a node to toggle its
 *           constellation, hover to preview.
 */
const DEFAULT_LAYERS = { plan: true, comfort: true, graph: false };

function PlanTooltip({ info }) {
  if (!info) return null;
  // a sense→sense adjustment inside a room's hub
  if (info.kind === "edge") {
    const { adj, sign } = info;
    return (
      <div className="plan-tooltip" style={{ left: info.x + 14, top: info.y + 14, maxWidth: 210 }}>
        <div className="plan-tooltip-title">{adj.from} → {adj.sense}</div>
        <div className="plan-tooltip-row"><span>effect</span><span style={{ color: VALENCE[sign].tint }}>{VALENCE[sign].label} {adj.delta > 0 ? "+" : ""}{adj.delta}</span></div>
        <div className="plan-tooltip-row"><span>basis</span><span>{adj.basis}</span></div>
        {adj.mechanism && <div className="plan-tooltip-why">{adj.mechanism}</div>}
      </div>
    );
  }
  // a room→room transmissive bleed edge
  if (info.kind === "bleed") {
    return (
      <div className="plan-tooltip" style={{ left: info.x + 14, top: info.y + 14, maxWidth: 210 }}>
        <div className="plan-tooltip-title">{info.src.name} → {info.tgt.name}</div>
        {info.sev.map(({ s, worse }) => (
          <div className="plan-tooltip-row" key={s}><span>{SI[s]} {s}</span><span>{worse.toFixed(2)}</span></div>
        ))}
        <div className="plan-tooltip-why">transmissive bleed — worse room → better</div>
      </div>
    );
  }
  // a graph room node (its topology metrics)
  if (info.kind === "node") {
    return (
      <div className="plan-tooltip" style={{ left: info.x + 14, top: info.y + 14 }}>
        <div className="plan-tooltip-title">{info.name}</div>
        {info.type && <div className="plan-tooltip-row"><span>type</span><span>{info.type}</span></div>}
        <div className="plan-tooltip-row"><span>doors</span><span>{info.degree}</span></div>
        <div className="plan-tooltip-row"><span>circulation</span><span>{info.betweenness}</span></div>
        {info.role && <div className="plan-tooltip-row"><span>role</span><span>{info.role}</span></div>}
      </div>
    );
  }
  const a = info.attrs || {};
  const pct = (v) => (v != null ? `${Math.round(v * 100)}%` : null);
  const rows = info.kind === "room"
    ? [["type", a.roomType], ["area", a.area && `${a.area} m²`], ["ceiling", a.ceilingHeight && `${a.ceilingHeight} m`],
       ["facing", a.orientation], ["glazing", pct(a.glazingRatio)], ["vent", a.ventilationType],
       ["floor", a.floorMaterial], ["score", info.score != null ? info.score.toFixed(2) : null]]
    : [["type", a.type], ["material", a.material]];
  return (
    <div className="plan-tooltip" style={{ left: info.x + 14, top: info.y + 14 }}>
      <div className="plan-tooltip-title">{info.title}</div>
      {rows.filter(([, v]) => v).map(([k, v]) => (
        <div className="plan-tooltip-row" key={k}><span>{k}</span><span>{v}</span></div>
      ))}
    </div>
  );
}

export default function SensePlan({ rooms, layoutId, layers = DEFAULT_LAYERS, graphData = null }) {
  const [layout, setLayout] = useState(null);
  const [err, setErr] = useState("");
  const [hover, setHover] = useState(null);
  const [hoverEdge, setHoverEdge] = useState(null);
  const [hoverRoom, setHoverRoom] = useState(null);
  const [expandedRooms, setExpandedRooms] = useState(() => new Set());
  const { focusSense, activeSense, toggleSense, activeRoom, setActiveRoom } = useSelection();

  useEffect(() => {
    let alive = true;
    api.getLayout()
      .then((d) => { if (alive) { setLayout(d.layout || null); setErr(d.layout ? "" : "no layout loaded yet"); } })
      .catch(() => { if (alive) setErr("could not load layout"); });
    return () => { alive = false; };
  }, [layoutId]);

  const scoredByName = useMemo(() => {
    const m = {}; (rooms || []).forEach((r) => { m[r.roomName] = r; }); return m;
  }, [rooms]);

  const view = useMemo(() => {
    if (!layout) return null;
    const all = (layout.rooms || []).flatMap((r) => r.geometry || []);
    if (all.length < 2) return null;
    let x0 = Infinity, y0 = Infinity, x1 = -Infinity, y1 = -Infinity;
    all.forEach(([x, y]) => { x0 = Math.min(x0, x); y0 = Math.min(y0, y); x1 = Math.max(x1, x); y1 = Math.max(y1, y); });
    const span = Math.max(x1 - x0, y1 - y0);
    const pad = span * 0.07 + 0.5;
    return { vb: `${x0 - pad} ${y0 - pad} ${(x1 - x0) + 2 * pad} ${(y1 - y0) + 2 * pad}`,
             fy: (y) => (y0 + y1) - y, span };
  }, [layout]);

  const roomById = useMemo(() => {
    const m = {};
    (layout?.rooms || []).forEach((r) => {
      const geo = r.geometry || [];
      if (geo.length >= 3) m[r.id] = { name: r.name, c: centroid(geo), scored: scoredByName[r.name] };
    });
    return m;
  }, [layout, scoredByName]);

  if (err) return <div className="ap-empty">{err}</div>;
  if (!layout || !view) return <div className="ap-empty">loading plan…</div>;

  const { fy, span } = view;
  const u = span * 0.012;

  const toggleRoom = (name) => setExpandedRooms((prev) => {
    const n = new Set(prev); n.has(name) ? n.delete(name) : n.add(name); return n;
  });
  const handleHoverNode = (info) => { setHover(info || null); setHoverRoom(info?.name || null); };

  // every room whose constellation should show: clicked-expanded ∪ hovered
  const hubNames = [...new Set([...expandedRooms, hoverRoom].filter(Boolean))];

  return (
    <>
      <svg className="sense-plan" viewBox={view.vb} preserveAspectRatio="xMidYMid meet">
        <g opacity={layers.graph ? 0.4 : 1}>
          {layers.plan && <WallsLayer outline={layout.outline} structure={layout.structure} fy={fy} />}
          <RoomsLayer rooms={layout.rooms} scoredByName={scoredByName} plan={layers.plan} comfort={layers.comfort}
            activeRoom={activeRoom} setActiveRoom={setActiveRoom} focusSense={focusSense} fy={fy} u={u} onHover={setHover} />
          {layers.plan && <OpeningsLayer doors={layout.doors} windows={layout.windows} fy={fy} />}
          {layers.plan && <FurnitureLayer furniture={layout.furniture} fy={fy} u={u} onHover={setHover} />}
        </g>

        {layers.graph && <>
          <GraphEdges roomById={roomById} graphData={graphData} doors={layout.doors} focusSense={focusSense} u={u} fy={fy} onHoverEdge={setHoverEdge} />
          <RoomGraph roomById={roomById} graphData={graphData} showLabels={!layers.plan}
            expandedRooms={expandedRooms} onToggleRoom={toggleRoom} onHoverNode={handleHoverNode} fy={fy} u={u} />
          {hubNames.map((name) => {
            const rm = (layout.rooms || []).find((r) => r.name === name && (r.geometry || []).length >= 3);
            const sc = scoredByName[name];
            if (!rm || !sc) return null;
            const c = centroid(rm.geometry);
            const { w, h } = dims(rm.geometry);
            const R = Math.max(u * 3.5, Math.min(Math.min(w, h) * 0.36, u * 7));
            const preview = !expandedRooms.has(name);
            return (
              <g key={"hub" + name} opacity={preview ? 0.7 : 1}>
                <SenseHub room={sc} cx={c[0]} cy={fy(c[1])} R={R} u={u}
                  activeSense={activeSense} onSelectSense={toggleSense} onHoverEdge={setHoverEdge} />
              </g>
            );
          })}
        </>}
      </svg>
      {layers.graph && (
        <button className="graph-expand-all"
          onClick={() => setExpandedRooms((prev) => prev.size ? new Set() : new Set(Object.values(roomById).map((r) => r.name)))}>
          {expandedRooms.size ? "collapse all" : "expand all"}
        </button>
      )}
      <PlanTooltip info={hoverEdge || hover} />
    </>
  );
}
