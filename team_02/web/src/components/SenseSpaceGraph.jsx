import { useEffect, useRef, useState } from "react";
import cytoscape from "cytoscape";
import { SC, SI, SENSES } from "../lib/constants.js";

// ── helpers ──────────────────────────────────────────────────────────────────

function parseJ(s) { try { return s ? JSON.parse(s) : null; } catch { return null; } }

function scoreColor(v) {
  if (v == null) return "rgba(240,237,232,0.18)";
  return v < 0.5 ? "#E8836A" : v < 0.65 ? "#D4B96A" : "#8BB88A";
}

// Build ROOM GRAPH: rooms as nodes, sense-typed edges from adjacency + conflicts
function buildRoomGraph(graphData, scoresJson, conflictsJson) {
  const scores    = parseJ(scoresJson);
  const conflicts = parseJ(conflictsJson);
  const gd        = graphData || {};

  const roomScores    = {};
  const roomConflicts = {}; // roomId → Set of failing senses
  (scores?.rooms || []).forEach((r) => {
    roomScores[r.roomId] = r.overallScore;
    const failing = new Set(
      Object.entries(r.comfortScores || {})
        .filter(([, v]) => v < 0.5)
        .map(([s]) => s)
    );
    roomConflicts[r.roomId] = failing;
  });

  // Also index by name for when graph_data uses names
  const nameToId = {};
  (scores?.rooms || []).forEach((r) => { nameToId[r.roomName] = r.roomId; });

  const nodes = (gd.nodes || []).map((n) => {
    const score    = roomScores[n.id];
    const failing  = roomConflicts[n.id] || new Set();
    return {
      data: {
        id:       n.id,
        label:    n.name,
        score,
        issues:   failing.size,
        color:    scoreColor(score),
        size:     32 + failing.size * 10,
      },
    };
  });

  // Sense-typed edges: for each door connection, find senses that leak
  const edges = [];
  (gd.edges || []).forEach((e, i) => {
    const aFailing = roomConflicts[e.source] || new Set();
    const bFailing = roomConflicts[e.target] || new Set();
    // Acoustic always leaks through doors; olfactory leaks kitchen→others
    const leaking = SENSES.filter((s) => {
      if (s === "acoustic") return aFailing.has(s) || bFailing.has(s);
      if (s === "olfactory") return aFailing.has(s) || bFailing.has(s);
      if (s === "thermal")   return aFailing.has(s) || bFailing.has(s);
      return false;
    });

    if (leaking.length) {
      leaking.forEach((sense) => {
        edges.push({
          data: {
            id:     `${e.source}-${e.target}-${sense}-${i}`,
            source: e.source,
            target: e.target,
            sense,
            color:  SC[sense],
            label:  SI[sense] || sense,
          },
        });
      });
    } else {
      // neutral door connection (no conflict influence)
      edges.push({
        data: {
          id:     `${e.source}-${e.target}-door-${i}`,
          source: e.source,
          target: e.target,
          sense:  null,
          color:  "rgba(240,237,232,0.12)",
          label:  "",
        },
      });
    }
  });

  return { nodes, edges };
}

// Build SENSE GRAPH: senses as nodes, co-failure as edges
function buildSenseGraph(scoresJson, conflictsJson) {
  const conflicts = parseJ(conflictsJson);
  const scores    = parseJ(scoresJson);

  // Count how many rooms fail each sense
  const failCount = {};
  SENSES.forEach((s) => { failCount[s] = 0; });

  const roomFailingSenses = {}; // roomId → [senses]
  (scores?.rooms || []).forEach((r) => {
    const failing = SENSES.filter((s) => (r.comfortScores?.[s] || 0) < 0.5);
    roomFailingSenses[r.roomId] = failing;
    failing.forEach((s) => { failCount[s]++; });
  });

  const nodes = SENSES.map((s) => ({
    data: {
      id:    s,
      label: `${SI[s]} ${s}`,
      count: failCount[s],
      color: SC[s],
      size:  28 + failCount[s] * 12,
    },
  }));

  // Co-failure edges: two senses connected when they fail together in ≥1 room
  const edges = [];
  for (let i = 0; i < SENSES.length; i++) {
    for (let j = i + 1; j < SENSES.length; j++) {
      const s1 = SENSES[i], s2 = SENSES[j];
      const coFail = Object.values(roomFailingSenses)
        .filter((arr) => arr.includes(s1) && arr.includes(s2)).length;
      if (coFail > 0) {
        edges.push({
          data: {
            id:     `${s1}-${s2}`,
            source: s1,
            target: s2,
            weight: coFail,
            label:  coFail > 1 ? `${coFail} rooms` : "1 room",
          },
        });
      }
    }
  }

  return { nodes, edges };
}

// ── Cytoscape renderer ────────────────────────────────────────────────────────

function CyGraph({ nodes, edges, mode, onSelect, selectedId }) {
  const ref   = useRef(null);
  const cyRef = useRef(null);

  useEffect(() => {
    if (!ref.current || !nodes.length) return;

    const cy = cytoscape({
      container: ref.current,
      elements: { nodes, edges },
      style: [
        {
          selector: "node",
          style: {
            "background-color":   "data(color)",
            "background-opacity": 0.22,
            "border-color":       "data(color)",
            "border-width":       1.5,
            "border-opacity":     0.7,
            label:                "data(label)",
            color:                "rgba(240,237,232,0.80)",
            "font-size":          "9px",
            "font-family":        "IBM Plex Mono, monospace",
            "text-valign":        "bottom",
            "text-margin-y":      "7px",
            width:                "data(size)",
            height:               "data(size)",
          },
        },
        {
          selector: "node:selected, node.highlighted",
          style: { "background-opacity": 0.55, "border-width": 2.5 },
        },
        {
          selector: "edge",
          style: {
            width:             2,
            "line-color":      "data(color)",
            "line-opacity":    0.55,
            label:             "data(label)",
            "font-size":       "7px",
            color:             "rgba(240,237,232,0.45)",
            "font-family":     "IBM Plex Mono, monospace",
            "text-rotation":   "autorotate",
            "curve-style":     "bezier",
            "text-margin-y":   "-5px",
          },
        },
      ],
      layout: {
        name:           mode === "sense" ? "circle" : "cose",
        animate:        false,
        padding:        28,
        nodeRepulsion:  mode === "sense" ? undefined : 6000,
      },
      userZoomingEnabled:  false,
      userPanningEnabled:  false,
      boxSelectionEnabled: false,
      autoungrabify:       true,
    });

    cy.on("tap", "node", (e) => onSelect && onSelect(e.target.data("id")));
    cyRef.current = cy;
    return () => { try { cy.destroy(); } catch { /* noop */ } };
  }, [nodes, edges, mode]); // eslint-disable-line

  // Highlight selected node
  useEffect(() => {
    const cy = cyRef.current;
    if (!cy) return;
    cy.nodes().forEach((n) => {
      n.style("background-opacity", n.data("id") === selectedId ? 0.60 : 0.22);
      n.style("border-width",       n.data("id") === selectedId ? 2.5  : 1.5);
    });
  }, [selectedId]);

  if (!nodes.length) {
    return <div className="sg-empty">run analysis or topology to populate the graph</div>;
  }
  return <div ref={ref} className="sg-cy" />;
}

// ── Public component ──────────────────────────────────────────────────────────

export default function SenseSpaceGraph({
  graphData, scoresJson, conflictsJson, onSelect, selectedId,
}) {
  const [mode, setMode] = useState("room"); // "room" | "sense"
  const hasGraph = graphData && graphData.nodes && graphData.nodes.length;

  const { nodes, edges } = mode === "room"
    ? buildRoomGraph(graphData, scoresJson, conflictsJson)
    : buildSenseGraph(scoresJson, conflictsJson);

  return (
    <div className="sense-graph">
      <div className="sg-tabs">
        <button
          className={"sg-tab" + (mode === "room" ? " active" : "")}
          onClick={() => setMode("room")}
        >room graph</button>
        <button
          className={"sg-tab" + (mode === "sense" ? " active" : "")}
          onClick={() => setMode("sense")}
        >sense graph</button>
        {!hasGraph && mode === "room" && (
          <span className="sg-hint">run topology for door edges</span>
        )}
      </div>

      <CyGraph
        nodes={nodes}
        edges={edges}
        mode={mode}
        onSelect={onSelect}
        selectedId={selectedId}
      />

      {/* Legend */}
      <div className="sg-legend">
        {mode === "room" ? (
          SENSES.filter((s) => ["acoustic","olfactory","thermal"].includes(s)).map((s) => (
            <span key={s} className="sg-legend-item">
              <span className="sg-legend-dot" style={{ background: SC[s] }} />
              {s}
            </span>
          ))
        ) : (
          <span className="sg-legend-item">node size = rooms failing this sense</span>
        )}
      </div>
    </div>
  );
}
