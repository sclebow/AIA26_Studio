import { useEffect, useRef, useState } from "react";
import Plotly from "plotly.js-dist-min";
import * as api from "../api/client.js";
import { SC, SI, SENSES } from "../lib/constants.js";

function scoreRgb(v) {
  if (v == null) return "240,237,232";
  return v < 0.5 ? "232,131,106" : v < 0.65 ? "212,185,106" : "139,184,138";
}

function centroid(poly) {
  const pts = poly.length > 1 && poly[0][0] === poly[poly.length-1][0] && poly[0][1] === poly[poly.length-1][1]
    ? poly.slice(0, -1) : poly;
  let x = 0, y = 0;
  pts.forEach(p => { x += p[0]; y += p[1]; });
  return [x / pts.length, y / pts.length];
}

export default function LayoutPlan({
  rooms, selectedRoom, onSelect, layoutId,
  layoutDiff, biophilicData, showMode,
  showGraph, graphData,
}) {
  const ref      = useRef(null);
  const [layout, setLayout] = useState(null);
  const [err,    setErr]    = useState("");
  const [pulsingRoom, setPulsingRoom] = useState(null);

  useEffect(() => {
    let alive = true;
    api.getLayout()
      .then(d => {
        if (alive) {
          setLayout(d.layout || null);
          if (d.layout) {
            setErr("");
          } else {
            setErr("no layout loaded yet");
          }
        }
      })
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

    const scoreByName    = {};
    const conflictsByName = {};
    const bioByName      = {};
    const diffRoomName   = layoutDiff?.room_name;

    (rooms || []).forEach(r => {
      scoreByName[r.roomName] = r.overallScore;
      const failing = new Set(
        Object.entries(r.comfortScores || {}).filter(([,v]) => v < 0.5).map(([s]) => s)
      );
      conflictsByName[r.roomName] = failing;
    });

    if (biophilicData?.rooms) {
      biophilicData.rooms.forEach(r => { bioByName[r.name] = r.richness_score; });
    }

    const traces      = [];
    const annotations = [];

    // Build centroid maps once
    const centroidByName = {};
    const centroidById   = {};
    (layout.rooms || []).forEach(room => {
      const geo = room.geometry || [];
      if (geo.length < 3) return;
      const c = centroid(geo);
      centroidByName[room.name] = c;
      if (room.id != null) centroidById[room.id] = c;
    });

    // ── Room polygons ──────────────────────────────────────────────────────────
    (layout.rooms || []).forEach(room => {
      const geo    = room.geometry || [];
      if (geo.length < 3) return;
      const name   = room.name;
      const isSel  = !showGraph && name === selectedRoom;
      const isDiff = !showGraph && name === diffRoomName;

      const score = showMode === "biophilic" ? bioByName[name] : scoreByName[name];
      const rgb   = scoreRgb(score);

      const fillOp = showGraph ? 0.04 : isDiff ? 0.65 : isSel ? 0.42 : 0.20;
      const lineOp = showGraph ? 0.12 : isDiff ? 1.00 : isSel ? 0.95 : 0.55;
      const lineW  = showGraph ? 0.8  : isDiff ? 3.5  : isSel ? 2.5  : 1.2;

      traces.push({
        x: geo.map(p => p[0]), y: geo.map(p => p[1]),
        mode: "lines", fill: "toself",
        fillcolor: `rgba(${rgb},${fillOp})`,
        line: { color: `rgba(${rgb},${lineOp})`, width: lineW },
        name, text: name, hoverinfo: showGraph ? "skip" : "text",
        customdata: showGraph ? undefined : [name],
      });

      if (!showGraph) {
        const [cx, cy] = centroidByName[name] || [0, 0];
        const scoreLabel = score != null ? score.toFixed(2) : "";
        const failing    = conflictsByName[name] || new Set();
        const badges     = [...failing].map(s => SI[s] || s.slice(0,3)).join(" ");

        if (scoreLabel) {
          annotations.push({
            x: cx, y: cy + 0.25, text: scoreLabel, showarrow: false,
            font: { family: "IBM Plex Mono, monospace", size: 11, color: `rgba(${rgb},0.95)` },
          });
        }
        if (badges) {
          annotations.push({
            x: cx, y: cy - 0.30, text: badges, showarrow: false,
            font: { family: "IBM Plex Mono, monospace", size: 8, color: `rgba(${rgb},0.70)` },
          });
        }
        if (isDiff && layoutDiff) {
          annotations.push({
            x: cx, y: cy - 0.80,
            text: `${layoutDiff.old_value} → ${layoutDiff.new_value}`,
            showarrow: false,
            font: { family: "IBM Plex Mono, monospace", size: 7, color: "rgba(240,237,232,0.80)" },
            bgcolor: "rgba(30,30,30,0.70)", borderpad: 3,
          });
        }
      }
    });

    // ── Walls ──────────────────────────────────────────────────────────────────
    (layout.structure || []).forEach(w => {
      const g = w.geometry || [];
      if (g.length < 2) return;
      traces.push({
        x: g.map(p=>p[0]), y: g.map(p=>p[1]),
        mode: "lines",
        line: { color: showGraph ? "rgba(20,20,20,0.25)" : "rgba(20,20,20,0.95)", width: showGraph ? 1.5 : 3 },
        hoverinfo: "skip", showlegend: false,
      });
    });

    // ── Doors / Windows / Furniture (comfort mode only) ────────────────────────
    if (!showGraph) {
      (layout.doors || []).forEach(d => {
        const g = d.geometry || [];
        if (g.length < 2) return;
        traces.push({
          x: g.map(p=>p[0]), y: g.map(p=>p[1]),
          mode: "lines",
          line: { color: "rgba(232,131,106,0.80)", width: 2, dash: "dash" },
          hoverinfo: "skip", showlegend: false,
        });
        const mid = g[Math.floor(g.length / 2)];
        traces.push({
          x: [mid[0]], y: [mid[1]], mode: "markers",
          marker: { color: "rgba(232,131,106,0.70)", size: 5, symbol: "diamond" },
          hoverinfo: "skip", showlegend: false,
        });
      });

      (layout.windows || []).forEach(wn => {
        const g = wn.geometry || [];
        if (g.length < 2) return;
        traces.push({
          x: g.map(p=>p[0]), y: g.map(p=>p[1]), mode: "lines",
          line: { color: "rgba(106,184,200,0.95)", width: 4 },
          hoverinfo: "skip", showlegend: false,
        });
        traces.push({
          x: g.map(p=>p[0]), y: g.map(p=>p[1]), mode: "lines",
          line: { color: "rgba(200,240,248,0.45)", width: 1.5 },
          hoverinfo: "skip", showlegend: false,
        });
      });

      (layout.furniture || []).forEach(f => {
        const g = f.geometry || [];
        if (g.length < 3) return;
        traces.push({
          x: g.map(p=>p[0]), y: g.map(p=>p[1]),
          mode: "lines", fill: "toself",
          fillcolor: "rgba(139,184,138,0.12)",
          line: { color: "rgba(139,184,138,0.45)", width: 1 },
          hoverinfo: "skip", showlegend: false,
        });
      });
    }

    // ── Graph overlay ──────────────────────────────────────────────────────────
    if (showGraph && graphData?.nodes?.length) {
      const idToName = {};
      (graphData.nodes || []).forEach(n => { idToName[n.id] = n.name; });

      (graphData.edges || []).forEach(e => {
        const srcC = centroidById[e.source] || centroidByName[idToName[e.source]];
        const tgtC = centroidById[e.target] || centroidByName[idToName[e.target]];
        if (!srcC || !tgtC) return;

        const srcName  = idToName[e.source];
        const tgtName  = idToName[e.target];
        const srcFail  = conflictsByName[srcName] || new Set();
        const tgtFail  = conflictsByName[tgtName] || new Set();
        const leaking  = ["acoustic", "olfactory", "thermal"].filter(s => srcFail.has(s) || tgtFail.has(s));

        if (leaking.length > 0) {
          leaking.forEach(sense => {
            traces.push({
              x: [srcC[0], tgtC[0]], y: [srcC[1], tgtC[1]],
              mode: "lines",
              line: { color: SC[sense], width: 2.5 },
              hoverinfo: "skip", showlegend: false,
            });
          });
        } else {
          traces.push({
            x: [srcC[0], tgtC[0]], y: [srcC[1], tgtC[1]],
            mode: "lines",
            line: { color: "rgba(240,237,232,0.18)", width: 1.5 },
            hoverinfo: "skip", showlegend: false,
          });
        }
      });

      const nodeItems = (graphData.nodes || [])
        .map(n => {
          const c       = centroidById[n.id] || centroidByName[n.name];
          const score   = scoreByName[n.name];
          const failing = conflictsByName[n.name] || new Set();
          return { c, score, failing, name: n.name };
        })
        .filter(n => n.c);

      if (nodeItems.length) {
        traces.push({
          x:    nodeItems.map(n => n.c[0]),
          y:    nodeItems.map(n => n.c[1]),
          mode: "markers+text",
          marker: {
            color:  nodeItems.map(n => `rgba(${scoreRgb(n.score)},0.75)`),
            size:   nodeItems.map(n => 24 + n.failing.size * 10),
            line:   { color: nodeItems.map(n => `rgba(${scoreRgb(n.score)},1)`), width: 2 },
            symbol: "circle",
          },
          text:         nodeItems.map(n => n.name),
          textposition: "bottom center",
          textfont:     { family: "IBM Plex Mono, monospace", size: 9, color: "rgba(240,237,232,0.85)" },
          customdata:   nodeItems.map(n => [n.name]),
          hoverinfo:    "text",
        });
      }
    }

    const plLayout = {
      margin: { l:8, r:8, t:8, b:8 },
      paper_bgcolor: "rgba(0,0,0,0)",
      plot_bgcolor:  "rgba(0,0,0,0)",
      xaxis: { visible: false, scaleanchor: "y", scaleratio: 1, fixedrange: false },
      yaxis: { visible: false, fixedrange: false },
      showlegend: false,
      annotations,
      dragmode: "pan",
    };

    Plotly.react(ref.current, traces, plLayout, {
      displayModeBar: false,
      responsive:     true,
      scrollZoom:     true,
    });

    const div     = ref.current;
    const handler = e => {
      const pt   = e.points?.[0];
      const name = pt?.customdata?.[0] ?? pt?.data?.customdata?.[0];
      if (name && onSelect) onSelect(name);
    };
    div.on?.("plotly_click", handler);
    return () => { try { div.removeAllListeners?.("plotly_click"); } catch {} };
  }, [layout, rooms, selectedRoom, layoutDiff, biophilicData, showMode, onSelect, showGraph, graphData]);

  if (err) return <div className="ap-empty">{err}</div>;
  return (
    <div style={{ position:"relative", width:"100%", height:"100%" }}>
      <div ref={ref} style={{ width:"100%", height:"100%" }} />
      {pulsingRoom && (
        <div className="layout-pulse-overlay" key={pulsingRoom}>
          <div className="layout-pulse-ring" />
        </div>
      )}
    </div>
  );
}
