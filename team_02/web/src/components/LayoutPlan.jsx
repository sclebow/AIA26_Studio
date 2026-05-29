import { useEffect, useRef, useState } from "react";
import Plotly from "plotly.js-dist-min";
import * as api from "../api/client.js";

// Phase 4 — in-UI 2D floor plan (Plotly), colored by comfort score, clickable.
// This is the headline "see the layout inside the UI, not Rhino" feature.
function scoreColor(v) {
  if (v == null) return "rgba(240,237,232,0.25)";
  return v < 0.5 ? "232,131,106" : v < 0.65 ? "212,185,106" : "139,184,138";
}
function centroid(poly) {
  const pts = poly.slice(0, poly[0] && poly[poly.length - 1] && poly[0][0] === poly[poly.length - 1][0] && poly[0][1] === poly[poly.length - 1][1] ? -1 : poly.length);
  let x = 0, y = 0;
  pts.forEach((p) => { x += p[0]; y += p[1]; });
  return [x / pts.length, y / pts.length];
}

export default function LayoutPlan({ rooms, selectedRoom, onSelect, layoutId }) {
  const ref = useRef(null);
  const [layout, setLayout] = useState(null);
  const [err, setErr] = useState("");

  useEffect(() => {
    let alive = true;
    api.getLayout()
      .then((d) => { if (alive) { setLayout(d.layout || null); if (!d.layout) setErr("no layout loaded yet"); } })
      .catch(() => { if (alive) setErr("could not load layout"); });
    return () => { alive = false; };
  }, [layoutId]);

  useEffect(() => {
    if (!ref.current || !layout) return;
    const scoreByName = {};
    (rooms || []).forEach((r) => { scoreByName[r.roomName] = r.overallScore; });

    const traces = [];

    // rooms (filled polygons, colored by score)
    (layout.rooms || []).forEach((room) => {
      const geo = room.geometry || [];
      if (geo.length < 3) return;
      const rgb = scoreColor(scoreByName[room.name]);
      const isSel = room.name === selectedRoom;
      traces.push({
        x: geo.map((p) => p[0]), y: geo.map((p) => p[1]),
        mode: "lines", fill: "toself",
        fillcolor: `rgba(${rgb},${isSel ? 0.42 : 0.20})`,
        line: { color: `rgba(${rgb},${isSel ? 0.95 : 0.55})`, width: isSel ? 2.5 : 1.2 },
        name: room.name, text: room.name, hoverinfo: "text",
        customdata: [room.name],
      });
    });

    // walls
    (layout.structure || []).forEach((w) => {
      const g = w.geometry || [];
      if (g.length < 2) return;
      traces.push({ x: g.map((p) => p[0]), y: g.map((p) => p[1]), mode: "lines", line: { color: "rgba(20,20,20,0.95)", width: 3 }, hoverinfo: "skip", showlegend: false });
    });
    // doors
    (layout.doors || []).forEach((d) => {
      const g = d.geometry || [];
      if (g.length < 2) return;
      traces.push({ x: g.map((p) => p[0]), y: g.map((p) => p[1]), mode: "lines", line: { color: "rgba(232,131,106,0.9)", width: 3 }, hoverinfo: "skip", showlegend: false });
    });
    // windows
    (layout.windows || []).forEach((wn) => {
      const g = wn.geometry || [];
      if (g.length < 2) return;
      traces.push({ x: g.map((p) => p[0]), y: g.map((p) => p[1]), mode: "lines", line: { color: "rgba(106,184,200,0.95)", width: 3 }, hoverinfo: "skip", showlegend: false });
    });
    // furniture (light outline)
    (layout.furniture || []).forEach((f) => {
      const g = f.geometry || [];
      if (g.length < 3) return;
      traces.push({ x: g.map((p) => p[0]), y: g.map((p) => p[1]), mode: "lines", line: { color: "rgba(139,184,138,0.5)", width: 1 }, hoverinfo: "skip", showlegend: false });
    });

    // room name labels
    const annotations = (layout.rooms || []).map((room) => {
      const [cx, cy] = centroid(room.geometry || [[0, 0]]);
      return { x: cx, y: cy, text: room.name, showarrow: false, font: { family: "IBM Plex Mono, monospace", size: 9, color: "rgba(240,237,232,0.7)" } };
    });

    const plLayout = {
      margin: { l: 8, r: 8, t: 8, b: 8 },
      paper_bgcolor: "rgba(0,0,0,0)", plot_bgcolor: "rgba(0,0,0,0)",
      xaxis: { visible: false, scaleanchor: "y", scaleratio: 1 },
      yaxis: { visible: false },
      showlegend: false, annotations, hovermode: "closest",
    };
    Plotly.react(ref.current, traces, plLayout, { displayModeBar: false, responsive: true });

    const div = ref.current;
    const handler = (e) => {
      const pt = e.points && e.points[0];
      const name = pt && pt.data && pt.data.customdata && pt.data.customdata[0];
      if (name && onSelect) onSelect(name);
    };
    div.on && div.on("plotly_click", handler);
    return () => { try { div.removeAllListeners && div.removeAllListeners("plotly_click"); } catch { /* noop */ } };
  }, [layout, rooms, selectedRoom, onSelect]);

  if (err) return <div className="ap-empty">{err}</div>;
  return <div ref={ref} style={{ width: "100%", height: 320 }} />;
}
