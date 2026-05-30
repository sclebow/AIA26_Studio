import { useEffect, useRef, useState } from "react";
import Plotly from "plotly.js-dist-min";
import * as api from "../api/client.js";
import { SC, SI } from "../lib/constants.js";

// Status palette (matches constants.js STATUS) for comfort coloring.
const STATUS = { fail: [224, 82, 74], warn: [224, 169, 46], pass: [63, 185, 122] };
function statusRgb(v) {
  if (v == null) return "240,237,232";
  const c = v < 0.5 ? STATUS.fail : v < 0.65 ? STATUS.warn : STATUS.pass;
  return c.join(",");
}
// Score for a room under the active lens ("overall" or a single sense).
function roomScore(r, lens) {
  if (!r) return null;
  if (lens && lens !== "overall") {
    const cs = r.comfortScores || {};
    return cs[lens] != null ? cs[lens] : null;
  }
  return r.overallScore != null ? r.overallScore : null;
}
function centroid(poly) {
  const pts = poly.length > 1 && poly[0][0] === poly[poly.length - 1][0] && poly[0][1] === poly[poly.length - 1][1]
    ? poly.slice(0, -1) : poly;
  let x = 0, y = 0; pts.forEach(p => { x += p[0]; y += p[1]; });
  return [x / pts.length, y / pts.length];
}
function bbox(poly) {
  let x0 = Infinity, y0 = Infinity, x1 = -Infinity, y1 = -Infinity;
  poly.forEach(p => { x0 = Math.min(x0, p[0]); x1 = Math.max(x1, p[0]); y0 = Math.min(y0, p[1]); y1 = Math.max(y1, p[1]); });
  return [x0, y0, x1, y1];
}
function insetPoly(poly, c, f) { return poly.map(p => [c[0] + (p[0] - c[0]) * f, c[1] + (p[1] - c[1]) * f]); }
function swingArc(A, B, n) {
  const r = Math.hypot(B[0] - A[0], B[1] - A[1]);
  const t0 = Math.atan2(B[1] - A[1], B[0] - A[0]);
  const xs = [], ys = [];
  for (let i = 0; i <= n; i++) { const t = t0 + (Math.PI / 2) * (i / n); xs.push(A[0] + r * Math.cos(t)); ys.push(A[1] + r * Math.sin(t)); }
  return [xs, ys];
}

const WALL = "rgba(240,237,232,0.92)";
const WALL_IN = "rgba(240,237,232,0.62)";
const FURN_LINE = "rgba(240,237,232,0.42)";
const FURN_FILL = "rgba(240,237,232,0.05)";
const GLASS = "rgba(70,150,220,1.0)";
const BG = "#0D0D0D";

export default function LayoutPlan({
  rooms, selectedRoom, onSelect, layoutId,
  layoutDiff, biophilicData, showMode,
  showGraph, graphData, lens = "overall",
}) {
  const ref = useRef(null);
  const [layout, setLayout] = useState(null);
  const [err, setErr] = useState("");
  const [pulsingRoom, setPulsingRoom] = useState(null);

  useEffect(() => {
    let alive = true;
    api.getLayout()
      .then(d => { if (alive) { setLayout(d.layout || null); setErr(d.layout ? "" : "no layout loaded yet"); } })
      .catch(() => { if (alive) setErr("could not load layout"); });
    return () => { alive = false; };
  }, [layoutId]);

  useEffect(() => {
    if (!layoutDiff || !layoutDiff.room_id) return;
    setPulsingRoom(layoutDiff.room_id);
    const t = setTimeout(() => setPulsingRoom(null), 2800);
    return () => clearTimeout(t);
  }, [layoutDiff]);

  useEffect(() => {
    if (!ref.current || !layout) return;

    const roomByName = {};
    (rooms || []).forEach(r => { roomByName[r.roomName] = r; });
    const bioByName = {};
    if (biophilicData && biophilicData.rooms) biophilicData.rooms.forEach(r => { bioByName[r.name] = r.richness_score; });
    const diffRoomName = layoutDiff && layoutDiff.room_name;
    const hasComfort = (rooms || []).length > 0;

    const traces = [];
    const annotations = [];
    const centroidByName = {};
    const centroidById = {};

    (layout.rooms || []).forEach(room => {
      const geo = room.geometry || [];
      if (geo.length < 3) return;
      const c = centroid(geo);
      centroidByName[room.name] = c;
      if (room.id != null) centroidById[room.id] = c;
    });

    const ringX = [], ringY = [], ringLine = [];

    // ── Rooms: fill (hover/click target) + comfort glow + labels ──
    (layout.rooms || []).forEach(room => {
      const geo = room.geometry || [];
      if (geo.length < 3) return;
      const name = room.name;
      const a = room.attributes || {};
      const r = roomByName[name];
      const isSel = !showGraph && name === selectedRoom;
      const isDiff = !showGraph && name === diffRoomName;

      const score = showMode === "biophilic" ? bioByName[name] : roomScore(r, lens);
      const rgb = statusRgb(score);
      const showComfort = !showGraph && hasComfort && score != null;
      const lensLabel = lens === "overall" ? "overall" : lens;

      let hov = "<b>" + name + "</b>";
      hov += "<br>" + (a.roomType || "room") + (a.area != null ? " · " + a.area + " m²" : "");
      const matBits = [];
      if (a.floorMaterial) matBits.push(a.floorMaterial + " floor");
      if (a.orientation) matBits.push("faces " + a.orientation);
      if (a.height) matBits.push(a.height + "m ceiling");
      if (a.ventilationType) matBits.push(a.ventilationType + " ventilation");
      if (a.glazingRatio != null) matBits.push("glazing " + Math.round(a.glazingRatio * 100) + "%");
      if (matBits.length) hov += "<br>" + matBits.join(" · ");
      if (showComfort) hov += "<br>" + lensLabel + ": " + score.toFixed(2);

      const fillOp = showGraph ? 0.03 : !showComfort ? 0.02 : isDiff ? 0.14 : isSel ? 0.10 : 0.06;
      traces.push({
        x: geo.map(p => p[0]), y: geo.map(p => p[1]),
        mode: "lines", fill: "toself",
        fillcolor: "rgba(" + rgb + "," + fillOp + ")",
        line: { width: 0, color: "rgba(0,0,0,0)" },
        hoveron: "fills", hoverinfo: showGraph ? "skip" : "text",
        text: hov,
        customdata: showGraph ? undefined : geo.map(() => name),
        showlegend: false, name: "",
      });

      if (showComfort) {
        const cc = centroidByName[name];
        const ins = insetPoly(geo, cc, 0.92);
        const glowOp = isDiff ? 0.85 : isSel ? 0.70 : 0.45;
        const glowW = isDiff ? 7 : isSel ? 6 : 5;
        traces.push({
          x: ins.map(p => p[0]), y: ins.map(p => p[1]),
          mode: "lines",
          line: { color: "rgba(" + rgb + "," + glowOp + ")", width: glowW },
          hoverinfo: "skip", showlegend: false,
        });
        const bb = bbox(geo);
        ringX.push(bb[2] - 0.55); ringY.push(bb[3] - 0.55); ringLine.push("rgb(" + rgb + ")");
        annotations.push({
          x: bb[2] - 0.55, y: bb[3] - 0.55, text: score.toFixed(2), showarrow: false,
          font: { family: "IBM Plex Mono, monospace", size: 11, color: "rgb(" + rgb + ")" },
        });
      }

      if (!showGraph) {
        const cc = centroidByName[name];
        const bb = bbox(geo); const roomH = bb[3] - bb[1];
        const lblY = bb[3] - 0.45; // anchor labels near top of room
        annotations.push({
          x: cc[0], y: lblY, text: name, showarrow: false,
          font: { family: "IBM Plex Sans, sans-serif", size: roomH < 1.5 ? 10 : 12, color: "rgba(240,237,232,0.85)" },
        });
        if (a.area != null && roomH >= 1.5) annotations.push({
          x: cc[0], y: lblY - 0.40, text: a.area + " m²", showarrow: false,
          font: { family: "IBM Plex Mono, monospace", size: 11, color: "rgba(240,237,232,0.40)" },
        });
        if (showComfort && lens === "overall" && r) {
          const failing = Object.entries(r.comfortScores || {}).filter(([, v]) => v < 0.5).map(([s]) => s);
          if (failing.length) annotations.push({
            x: cc[0], y: cc[1] - 0.62,
            text: failing.map(s => SI[s] || s.slice(0, 3)).join("  "), showarrow: false,
            font: { family: "IBM Plex Mono, monospace", size: 11, color: "rgba(" + statusRgb(0.3) + ",0.85)" },
          });
        }
        if (isDiff && layoutDiff) annotations.push({
          x: cc[0], y: cc[1] - 1.05,
          text: layoutDiff.old_value + " → " + layoutDiff.new_value, showarrow: false,
          font: { family: "IBM Plex Mono, monospace", size: 11, color: "rgba(240,237,232,0.80)" },
          bgcolor: "rgba(30,30,30,0.75)", borderpad: 3,
        });
      }
    });

    // ── Furniture (neutral + type label + hover) ──
    if (!showGraph) {
      (layout.furniture || []).forEach(f => {
        const g = f.geometry || [];
        if (g.length < 3) return;
        const a = f.attributes || {};
        let hov = "<b>" + (f.name || "furniture") + "</b>";
        if (a.type || a.material) hov += "<br>" + [a.type, a.material].filter(Boolean).join(" · ");
        traces.push({
          x: g.map(p => p[0]), y: g.map(p => p[1]),
          mode: "lines", fill: "toself",
          fillcolor: FURN_FILL, line: { color: FURN_LINE, width: 1.2 },
          hoveron: "fills", hoverinfo: "text", text: hov, showlegend: false, name: "",
        });
        if (a.type) {
          const c = centroid(g);
          const fb = bbox(g); const fw = fb[2]-fb[0], fh = fb[3]-fb[1];
          if (fw >= 0.8 || fh >= 0.8) annotations.push({
            x: c[0], y: c[1], text: a.type, showarrow: false,
            font: { family: "IBM Plex Mono, monospace", size: 11, color: "rgba(240,237,232,0.50)" },
          });
        }
      });
    }

    // ── Walls: always white (exterior thick, interior thin) ──
    const wExtW = showGraph ? 1.5 : 5;
    const wInW = showGraph ? 0.8 : 2.5;
    const wExtC = showGraph ? "rgba(240,237,232,0.22)" : WALL;
    const wInC = showGraph ? "rgba(240,237,232,0.12)" : WALL_IN;
    if ((layout.outline || []).length > 1) {
      const o = layout.outline;
      traces.push({ x: o.map(p => p[0]), y: o.map(p => p[1]), mode: "lines", line: { color: wExtC, width: wExtW }, hoverinfo: "skip", showlegend: false });
    }
    (layout.rooms || []).forEach(room => {
      const g = room.geometry || [];
      if (g.length < 2) return;
      traces.push({ x: g.map(p => p[0]), y: g.map(p => p[1]), mode: "lines", line: { color: wInC, width: wInW }, hoverinfo: "skip", showlegend: false });
    });
    (layout.structure || []).forEach(w => {
      const g = w.geometry || [];
      if (g.length < 2) return;
      traces.push({ x: g.map(p => p[0]), y: g.map(p => p[1]), mode: "lines", line: { color: wInC, width: wInW }, hoverinfo: "skip", showlegend: false });
    });

    // ── Doors (gap + swing arc) & windows (glass line) ──
    if (!showGraph) {
      (layout.doors || []).forEach(d => {
        const g = d.geometry || [];
        if (g.length < 2) return;
        const A = g[0], B = g[g.length - 1];
        const a = d.attributes || {};
        const hov = "<b>" + (d.name || "door") + "</b><br>door" + (a.width ? " · " + a.width + "m" : "");
        traces.push({ x: [A[0], B[0]], y: [A[1], B[1]], mode: "lines", line: { color: BG, width: 6 }, hoverinfo: "skip", showlegend: false });
        const [ax, ay] = swingArc(A, B, 14);
        traces.push({ x: ax, y: ay, mode: "lines", line: { color: "rgba(240,237,232,0.40)", width: 1 }, hoverinfo: "text", text: ax.map(() => hov), showlegend: false });
        traces.push({ x: [A[0], ax[ax.length - 1]], y: [A[1], ay[ay.length - 1]], mode: "lines", line: { color: "rgba(240,237,232,0.40)", width: 1 }, hoverinfo: "skip", showlegend: false });
      });
      (layout.windows || []).forEach(wn => {
        const g = wn.geometry || [];
        if (g.length < 2) return;
        const a = wn.attributes || {};
        const hov = "<b>" + (wn.name || "window") + "</b><br>" + [a.glazingType ? a.glazingType + " glazing" : null, a.orientation ? "faces " + a.orientation : null].filter(Boolean).join(" · ");
        traces.push({ x: g.map(p => p[0]), y: g.map(p => p[1]), mode: "lines", line: { color: BG, width: 9 }, hoverinfo: "skip", showlegend: false, name: "" });
        traces.push({ x: g.map(p => p[0]), y: g.map(p => p[1]), mode: "lines", line: { color: "rgba(70,150,220,0.22)", width: 14 }, hoverinfo: "skip", showlegend: false, name: "" });
        traces.push({ x: g.map(p => p[0]), y: g.map(p => p[1]), mode: "lines", line: { color: GLASS, width: 5 }, hoverinfo: "text", text: g.map(() => hov), showlegend: false, name: "" });
      });
    }

    // ── Graph overlay (room network) ──
    if (showGraph && graphData && graphData.nodes && graphData.nodes.length) {
      const idToName = {};
      (graphData.nodes || []).forEach(n => { idToName[n.id] = n.name; });
      const conflictsByName = {};
      (rooms || []).forEach(r => { conflictsByName[r.roomName] = new Set(Object.entries(r.comfortScores || {}).filter(([, v]) => v < 0.5).map(([s]) => s)); });
      (graphData.edges || []).forEach(e => {
        const srcC = centroidById[e.source] || centroidByName[idToName[e.source]];
        const tgtC = centroidById[e.target] || centroidByName[idToName[e.target]];
        if (!srcC || !tgtC) return;
        const sf = conflictsByName[idToName[e.source]] || new Set();
        const tf = conflictsByName[idToName[e.target]] || new Set();
        const leaking = ["acoustic", "olfactory", "thermal"].filter(s => sf.has(s) || tf.has(s));
        if (leaking.length) leaking.forEach(sn => {
          traces.push({ x: [srcC[0], tgtC[0]], y: [srcC[1], tgtC[1]], mode: "lines", line: { color: SC[sn], width: 2.5 }, hoverinfo: "skip", showlegend: false });
        });
        else traces.push({ x: [srcC[0], tgtC[0]], y: [srcC[1], tgtC[1]], mode: "lines", line: { color: "rgba(240,237,232,0.18)", width: 1.5 }, hoverinfo: "skip", showlegend: false });
      });
      const nodes = (graphData.nodes || []).map(n => {
        const c = centroidById[n.id] || centroidByName[n.name];
        const r = roomByName[n.name];
        const fail = conflictsByName[n.name] || new Set();
        return { c, score: r ? r.overallScore : null, fail, name: n.name };
      }).filter(n => n.c);
      if (nodes.length) traces.push({
        x: nodes.map(n => n.c[0]), y: nodes.map(n => n.c[1]), mode: "markers+text",
        marker: {
          color: nodes.map(n => "rgba(" + statusRgb(n.score) + ",0.75)"),
          size: nodes.map(n => 24 + n.fail.size * 10),
          line: { color: nodes.map(n => "rgb(" + statusRgb(n.score) + ")"), width: 2 }, symbol: "circle",
        },
        text: nodes.map(n => n.name), textposition: "bottom center",
        textfont: { family: "IBM Plex Mono, monospace", size: 11, color: "rgba(240,237,232,0.85)" },
        customdata: nodes.map(n => n.name), hoverinfo: "text",
      });
    }

    // ── Corner rings (on top) ──
    if (ringX.length) {
      traces.push({
        x: ringX, y: ringY, mode: "markers",
        marker: { symbol: "circle", size: 30, color: BG, line: { color: ringLine, width: 2 } },
        hoverinfo: "skip", showlegend: false,
      });
    }

    const plLayout = {
      margin: { l: 8, r: 8, t: 8, b: 8 },
      paper_bgcolor: "rgba(0,0,0,0)", plot_bgcolor: "rgba(0,0,0,0)",
      xaxis: { visible: false, scaleanchor: "y", scaleratio: 1 },
      yaxis: { visible: false },
      showlegend: false, annotations, dragmode: "pan",
      hoverlabel: { bgcolor: "rgba(20,20,20,0.95)", bordercolor: "rgba(240,237,232,0.2)", font: { family: "IBM Plex Mono, monospace", size: 11, color: "rgba(240,237,232,0.9)" } },
    };
    Plotly.react(ref.current, traces, plLayout, { displayModeBar: false, responsive: true, scrollZoom: true });

    const div = ref.current;
    const handler = e => {
      const pt = e.points && e.points[0];
      if (!pt) return;
      let nm = pt.customdata;
      if (nm == null && pt.data && pt.data.customdata) nm = pt.data.customdata[pt.pointIndex];
      if (Array.isArray(nm)) nm = nm[0];
      if (nm && onSelect) onSelect(nm);
    };
    div.on && div.on("plotly_click", handler);
    return () => { try { div.removeAllListeners && div.removeAllListeners("plotly_click"); } catch (e) { /* noop */ } };
  }, [layout, rooms, selectedRoom, layoutDiff, biophilicData, showMode, onSelect, showGraph, graphData, lens]);

  if (err) return <div className="ap-empty">{err}</div>;
  return (
    <div style={{ position: "relative", width: "100%", height: "100%" }}>
      <div ref={ref} style={{ width: "100%", height: "100%" }} />
      {pulsingRoom && (
        <div className="layout-pulse-overlay" key={pulsingRoom}>
          <div className="layout-pulse-ring" />
        </div>
      )}
      {/* North compass */}
      <div style={{ position:"absolute", bottom:20, right:20, display:"flex", flexDirection:"column",
        alignItems:"center", pointerEvents:"none", zIndex:10, opacity:0.72 }}>
        <span style={{ fontFamily:"IBM Plex Mono,monospace", fontSize:11,
          color:"rgba(240,237,232,0.9)", letterSpacing:1, marginBottom:4 }}>N</span>
        <svg width="18" height="32" viewBox="0 0 18 32">
          <polygon points="9,0 3,18 9,13 15,18" fill="rgba(240,237,232,0.85)" />
          <polygon points="9,32 3,14 9,19 15,14" fill="none"
            stroke="rgba(240,237,232,0.35)" strokeWidth="1" />
        </svg>
      </div>
    </div>
  );
}
