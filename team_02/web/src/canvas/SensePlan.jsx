import { useEffect, useMemo, useState } from "react";
import * as api from "../api/client.js";
import { useSelection } from "../lib/selection.jsx";
import { centroid } from "../lib/geometry.js";
import WallsLayer from "./WallsLayer.jsx";
import RoomsLayer from "./RoomsLayer.jsx";
import OpeningsLayer from "./OpeningsLayer.jsx";
import FurnitureLayer from "./FurnitureLayer.jsx";
import FlowLayer from "./FlowLayer.jsx";
import TopologyLayer from "./TopologyLayer.jsx";
import Compass from "./Compass.jsx";

/*
 * SensePlan — the floor plan as one bespoke SVG data-canvas.
 *
 * This is now a thin CONTAINER: it loads the layout, derives the view transform
 * + per-room lookups, and composes the presentational LAYER components below.
 * Each layer owns one concern and is gated by the `layers` toggle prop:
 *   - WallsLayer / OpeningsLayer / FurnitureLayer : the architecture
 *   - RoomsLayer       : room fill (hue + intensity = health) + sense signatures
 *   - FlowLayer        : transmissive bleed across doors (acoustic/olfactory/thermal)
 *   - TopologyLayer    : room-graph (centroid edges) + nodes
 * Interaction: hover = CSS-only; click = pin focus (bus activeRoom).
 */
const DEFAULT_LAYERS = { fill: true, signatures: true, flow: false, topology: false };

export default function SensePlan({ rooms, layoutId, layers = DEFAULT_LAYERS }) {
  const [layout, setLayout] = useState(null);
  const [err, setErr] = useState("");
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
             fy: (y) => (y0 + y1) - y, span, x1, y1 };
  }, [layout]);

  // id → { name, centroid (layout coords), scored }
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

  return (
    <svg className="sense-plan" viewBox={view.vb} preserveAspectRatio="xMidYMid meet">
      <WallsLayer outline={layout.outline} structure={layout.structure} fy={fy} />
      <RoomsLayer rooms={layout.rooms} scoredByName={scoredByName} activeRoom={activeRoom}
        setActiveRoom={setActiveRoom} focusSense={focusSense} layers={layers} fy={fy} u={u} />
      <OpeningsLayer doors={layout.doors} windows={layout.windows} fy={fy} />
      <FurnitureLayer furniture={layout.furniture} fy={fy} u={u} />
      {layers.flow && <FlowLayer doors={layout.doors} roomById={roomById} focusSense={focusSense} fy={fy} u={u} />}
      {layers.topology && <TopologyLayer doors={layout.doors} roomById={roomById} fy={fy} u={u} />}
      <Compass x1={view.x1} y1={view.y1} fy={fy} u={u} />
    </svg>
  );
}
