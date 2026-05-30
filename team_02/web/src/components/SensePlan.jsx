import { useEffect, useMemo, useState } from "react";
import * as api from "../api/client.js";
import { SC, scoreOpacity } from "../lib/constants.js";
import { TRANSMISSIVE } from "../lib/senseModel.js";
import { useSelection } from "../lib/selection.jsx";
import SenseSignature from "./SenseSignature.jsx";

/*
 * SensePlan — the floor plan as one bespoke SVG data-canvas.
 *
 * Full architecture (rooms/walls/doors+swing/windows/furniture/compass) + toggleable
 * data LAYERS (controlled by the `layers` prop, one loud at a time + auto-dim):
 *   - fill        : room fill by active lens (hue + intensity = health)
 *   - signatures  : per-room calm sense-signature (focused room blooms slightly)
 *   - flow        : transmissive bleed across doors (acoustic/olfactory/thermal)
 *   - topology    : room-graph (centroid edges) + metric pills (hub/bridges/isolated)
 * Interaction: hover = CSS-only; click = pin focus (bus activeRoom).
 */
function polyPoints(geo, fy) { return geo.map(([x, y]) => `${x},${fy(y)}`).join(" "); }
function centroid(geo) {
  const pts = geo.length > 1 && geo[0][0] === geo.at(-1)[0] && geo[0][1] === geo.at(-1)[1] ? geo.slice(0, -1) : geo;
  let x = 0, y = 0; pts.forEach(p => { x += p[0]; y += p[1]; });
  return [x / pts.length, y / pts.length];
}
function dims(geo) {
  let x0 = Infinity, y0 = Infinity, x1 = -Infinity, y1 = -Infinity;
  geo.forEach(([x, y]) => { x0 = Math.min(x0, x); y0 = Math.min(y0, y); x1 = Math.max(x1, x); y1 = Math.max(y1, y); });
  return { w: x1 - x0, h: y1 - y0, top: y1, cx: (x0 + x1) / 2 };
}
function swingPath(A, B, fy) {
  const r = Math.hypot(B[0] - A[0], B[1] - A[1]);
  const t0 = Math.atan2(B[1] - A[1], B[0] - A[0]);
  const n = 12, pts = [];
  for (let i = 0; i <= n; i++) { const t = t0 + (Math.PI / 2) * (i / n); pts.push([A[0] + r * Math.cos(t), A[1] + r * Math.sin(t)]); }
  return polyPoints(pts, fy);
}

const DEFAULT_LAYERS = { fill: true, signatures: true, flow: false, topology: false };

export default function SensePlan({ rooms, layoutId, layers = DEFAULT_LAYERS, graphData = null }) {
  const [layout, setLayout] = useState(null);
  const [err, setErr] = useState("");
  const { focusSense, activeRoom, setActiveRoom } = useSelection();

  useEffect(() => {
    let alive = true;
    api.getLayout()
      .then(d => { if (alive) { setLayout(d.layout || null); setErr(d.layout ? "" : "no layout loaded yet"); } })
      .catch(() => { if (alive) setErr("could not load layout"); });
    return () => { alive = false; };
  }, [layoutId]);

  const scoredByName = useMemo(() => {
    const m = {}; (rooms || []).forEach(r => { m[r.roomName] = r; }); return m;
  }, [rooms]);

  const view = useMemo(() => {
    if (!layout) return null;
    const all = (layout.rooms || []).flatMap(r => r.geometry || []);
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
    (layout?.rooms || []).forEach(r => {
      const geo = r.geometry || [];
      if (geo.length >= 3) m[r.id] = { name: r.name, c: centroid(geo), scored: scoredByName[r.name] };
    });
    return m;
  }, [layout, scoredByName]);

  if (err) return <div className="ap-empty">{err}</div>;
  if (!layout || !view) return <div className="ap-empty">loading plan…</div>;

  const { fy, span } = view;
  const u = span * 0.012;
  const failingT = (sc) => TRANSMISSIVE.filter(s => (sc?.comfortScores?.[s] ?? 1) < 0.5);

  return (
    <svg className="sense-plan" viewBox={view.vb} preserveAspectRatio="xMidYMid meet">
      {(layout.outline || []).length > 1 && (
        <polyline className="spln-wall-ext" points={polyPoints(layout.outline, fy)} fill="none" strokeLinejoin="round" vectorEffect="non-scaling-stroke" />
      )}
      {(layout.structure || []).map((w, i) => {
        const g = w.geometry || [];
        return g.length > 1 ? <polyline key={"st" + i} className="spln-wall-in" points={polyPoints(g, fy)} fill="none" vectorEffect="non-scaling-stroke" /> : null;
      })}

      {/* rooms */}
      {(layout.rooms || []).map(room => {
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
      })}

      {/* doors */}
      {(layout.doors || []).map((d, i) => {
        const g = d.geometry || [];
        if (g.length < 2) return null;
        const A = g[0], B = g[g.length - 1];
        const arc = swingPath(A, B, fy);
        const arcEnd = arc.split(" ").at(-1).split(",");
        return (
          <g key={"dr" + i} className="spln-door">
            <line className="spln-door-gap" x1={A[0]} y1={fy(A[1])} x2={B[0]} y2={fy(B[1])} vectorEffect="non-scaling-stroke" />
            <polyline className="spln-door-swing" points={arc} fill="none" vectorEffect="non-scaling-stroke" />
            <line className="spln-door-swing" x1={A[0]} y1={fy(A[1])} x2={arcEnd[0]} y2={arcEnd[1]} vectorEffect="non-scaling-stroke" />
          </g>
        );
      })}

      {/* windows */}
      {(layout.windows || []).map((wn, i) => {
        const g = wn.geometry || [];
        return g.length > 1 ? <polyline key={"wn" + i} className="spln-window" points={polyPoints(g, fy)} fill="none" vectorEffect="non-scaling-stroke" /> : null;
      })}

      {/* furniture */}
      {(layout.furniture || []).map((f, i) => {
        const g = f.geometry || [];
        if (g.length < 3) return null;
        const a = f.attributes || {};
        const { cx, w, h } = dims(g);
        const [, fcy] = centroid(g);
        return (
          <g key={"fn" + i} className="spln-furn">
            <polygon className="spln-furn-fill" points={polyPoints(g, fy)} vectorEffect="non-scaling-stroke" />
            {a.type && (w >= 0.8 || h >= 0.8) && (
              <text className="spln-furn-label" x={cx} y={fy(fcy)} textAnchor="middle" dominantBaseline="central" fontSize={u * 0.85}>{a.type}</text>
            )}
          </g>
        );
      })}

      {/* LAYER: transmissive flow across doors */}
      {layers.flow && (layout.doors || []).map((d, i) => {
        const g = d.geometry || [];
        if (g.length < 2) return null;
        const A = g[0], B = g[g.length - 1];
        const conn = d.attributes?.connectsRooms || [];
        const failing = [...new Set([...failingT(roomById[conn[0]]?.scored), ...failingT(roomById[conn[1]]?.scored)])];
        const dx = B[0] - A[0], dy = (fy(B[1]) - fy(A[1])); const len = Math.hypot(dx, dy) || 1;
        const px = -dy / len, py = dx / len;
        return failing.map((s, k) => {
          const off = (k - (failing.length - 1) / 2) * u * 1.1;
          const loud = !focusSense || focusSense === s;
          return (
            <line key={"fl" + i + s} x1={A[0] + px * off} y1={fy(A[1]) + py * off} x2={B[0] + px * off} y2={fy(B[1]) + py * off}
              stroke={SC[s]} strokeOpacity={loud ? 0.8 : 0.15} strokeWidth={focusSense === s ? 4.5 : 3}
              strokeLinecap="round" vectorEffect="non-scaling-stroke" />
          );
        });
      })}

      {/* LAYER: topology (centroid graph) */}
      {layers.topology && (layout.doors || []).map((d, i) => {
        const conn = d.attributes?.connectsRooms || [];
        const a = roomById[conn[0]], b = roomById[conn[1]];
        if (!a || !b) return null;
        const conflict = [...failingT(a.scored), ...failingT(b.scored)];
        const col = conflict.length ? SC[conflict[0]] : "rgba(var(--fg-rgb),0.3)";
        return <line key={"tp" + i} x1={a.c[0]} y1={fy(a.c[1])} x2={b.c[0]} y2={fy(b.c[1])}
          stroke={col} strokeOpacity={0.55} strokeWidth={2.5} vectorEffect="non-scaling-stroke" />;
      })}
      {layers.topology && Object.values(roomById).map((rm, i) => (
        <circle key={"tn" + i} cx={rm.c[0]} cy={fy(rm.c[1])} r={u * 0.7}
          fill="rgb(var(--fg-rgb))" fillOpacity={0.5} stroke="rgb(var(--fg-rgb))" strokeOpacity={0.3} vectorEffect="non-scaling-stroke" />
      ))}

      {/* compass */}
      <g className="spln-compass" transform={`translate(${view.x1 - u * 1.2}, ${fy(view.y1) + u * 2.2})`}>
        <text textAnchor="middle" fontSize={u * 1.1} y={-u * 1.3}>N</text>
        <polygon points={`0,${-u} ${-u * 0.5},${u} 0,${u * 0.5} ${u * 0.5},${u}`} />
      </g>
    </svg>
  );
}
