import { useEffect, useMemo, useState } from "react";
import * as api from "../api/client.js";
import { useSelection } from "../lib/selection.jsx";
import { centroid } from "../lib/geometry.js";
import WallsLayer from "./WallsLayer.jsx";
import RoomsLayer from "./RoomsLayer.jsx";
import OpeningsLayer from "./OpeningsLayer.jsx";
import FurnitureLayer from "./FurnitureLayer.jsx";
import RoomGraph from "./RoomGraph.jsx";
import FlowLayer from "./FlowLayer.jsx";
import TopologyLayer from "./TopologyLayer.jsx";

/*
 * SensePlan — the floor plan as one bespoke SVG data-canvas, in two tiers:
 *   BASE   : the architecture (walls / rooms / openings / furniture), gated by
 *            `layers.plan` — turn it off to isolate a graph lens. Hovering a
 *            room or furniture piece raises its attributes.
 *   LENSES : comfort (fill + score ring), and the mutually-exclusive graph
 *            lenses flow / topology, drawn on the shared RoomGraph node substrate.
 *   When a graph lens is active the base dims so the graph reads as its own thing.
 */
const DEFAULT_LAYERS = { plan: true, comfort: true, flow: false, topology: false };

function PlanTooltip({ info }) {
  if (!info) return null;
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
  const { focusSense, activeRoom, setActiveRoom } = useSelection();

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
  const graphActive = layers.flow || layers.topology;

  return (
    <>
      <svg className="sense-plan" viewBox={view.vb} preserveAspectRatio="xMidYMid meet">
        <g opacity={graphActive ? 0.4 : 1}>
          {layers.plan && <WallsLayer outline={layout.outline} structure={layout.structure} fy={fy} />}
          <RoomsLayer rooms={layout.rooms} scoredByName={scoredByName} plan={layers.plan} comfort={layers.comfort}
            activeRoom={activeRoom} setActiveRoom={setActiveRoom} focusSense={focusSense} fy={fy} u={u} onHover={setHover} />
          {layers.plan && <OpeningsLayer doors={layout.doors} windows={layout.windows} fy={fy} />}
          {layers.plan && <FurnitureLayer furniture={layout.furniture} fy={fy} u={u} onHover={setHover} />}
        </g>
        {graphActive && <RoomGraph roomById={roomById} graphData={layers.topology ? graphData : null} showLabels={!layers.plan} fy={fy} u={u} />}
        {layers.flow && <FlowLayer doors={layout.doors} roomById={roomById} focusSense={focusSense} fy={fy} u={u} />}
        {layers.topology && <TopologyLayer doors={layout.doors} roomById={roomById} graphData={graphData} fy={fy} />}
      </svg>
      <PlanTooltip info={hover} />
    </>
  );
}
