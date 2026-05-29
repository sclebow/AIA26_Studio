import { useEffect, useMemo, useRef } from "react";
import cytoscape from "cytoscape";
import { SC, SI, SENSES } from "../lib/constants.js";

function parseJ(s) {
  try { return s ? JSON.parse(s) : null; } catch { return null; }
}

// ── Sense graph builder ───────────────────────────────────────────────────────
function buildSenseGraph(scoresJson) {
  const scores = parseJ(scoresJson);

  const failCount         = {};
  const roomFailingSenses = {};
  SENSES.forEach((s) => { failCount[s] = 0; });

  (scores?.rooms || []).forEach((r) => {
    const failing = SENSES.filter((s) => (r.comfortScores?.[s] || 0) < 0.5);
    roomFailingSenses[r.roomId] = failing;
    failing.forEach((s) => { failCount[s]++; });
  });

  const nodes = SENSES.map((s) => ({
    data: {
      id:    s,
      label: s,
      sym:   SI[s] || "",
      count: failCount[s],
      color: SC[s],
      size:  32 + failCount[s] * 16,
    },
  }));

  const edges = [];
  for (let i = 0; i < SENSES.length; i++) {
    for (let j = i + 1; j < SENSES.length; j++) {
      const s1     = SENSES[i];
      const s2     = SENSES[j];
      const coFail = Object.values(roomFailingSenses).filter(
        (arr) => arr.includes(s1) && arr.includes(s2)
      ).length;
      if (coFail > 0) {
        edges.push({
          data: { id: `${s1}-${s2}`, source: s1, target: s2, weight: coFail, label: `${coFail}` },
        });
      }
    }
  }

  return { nodes, edges };
}

// ── Cytoscape renderer ────────────────────────────────────────────────────────
function CyGraph({ nodes, edges, onSelect, selectedId }) {
  const ref   = useRef(null);
  const cyRef = useRef(null);

  // Rebuild only when data changes (not on selectedId change)
  useEffect(() => {
    if (!ref.current || !nodes.length) return;

    const cy = cytoscape({
      container: ref.current,
      elements:  { nodes, edges },
      style: [
        {
          selector: "node",
          style: {
            "background-color":   "data(color)",
            "background-opacity": 0.22,
            "border-color":       "data(color)",
            "border-width":       1.5,
            "border-opacity":     0.80,
            label:                "data(label)",
            color:                "rgba(240,237,232,0.85)",
            "font-size":          "12px",
            "font-family":        "IBM Plex Mono, monospace",
            "text-valign":        "bottom",
            "text-margin-y":      "10px",
            "text-wrap":          "wrap",
            width:                "data(size)",
            height:               "data(size)",
          },
        },
        {
          selector: "node:selected, node.highlighted",
          style: { "background-opacity": 0.65, "border-width": 3 },
        },
        {
          selector: "edge",
          style: {
            width:           2.5,
            "line-color":    "rgba(240,237,232,0.22)",
            "line-opacity":  1,
            label:           "data(label)",
            "font-size":     "12px",
            color:           "rgba(240,237,232,0.70)",
            "font-family":   "IBM Plex Mono, monospace",
            "font-weight":   "700",
            "text-rotation": "autorotate",
            "curve-style":   "bezier",
            "text-margin-y": "-7px",
          },
        },
      ],
      layout: {
        name:    "circle",
        animate: false,
        padding: 56,
      },
      userZoomingEnabled:  true,
      userPanningEnabled:  true,
      boxSelectionEnabled: false,
      autoungrabify:       true,
    });

    cy.ready(() => { cy.nodes().lock(); });
    cy.on("tap", "node", (e) => onSelect && onSelect(e.target.data("id")));
    cyRef.current = cy;
    return () => { try { cy.destroy(); } catch { /* noop */ } };
  }, [nodes, edges]); // eslint-disable-line

  // Highlight selected — restyling only, no layout re-run
  useEffect(() => {
    const cy = cyRef.current;
    if (!cy) return;
    cy.nodes().forEach((n) => {
      const isSel = n.data("id") === selectedId;
      n.style("background-opacity", isSel ? 0.70 : 0.22);
      n.style("border-width",       isSel ? 3    : 1.5);
      n.style("color",              isSel ? "rgba(240,237,232,1.0)" : "rgba(240,237,232,0.85)");
    });
  }, [selectedId]);

  if (!nodes.length) {
    return <div className="sg-empty">run analysis to populate the sense graph</div>;
  }
  return <div ref={ref} className="sg-cy" />;
}

// ── Public component ──────────────────────────────────────────────────────────
export default function SenseSpaceGraph({ scoresJson, onSelect, selectedId }) {
  const { nodes, edges } = useMemo(
    () => buildSenseGraph(scoresJson),
    [scoresJson]
  );

  return (
    <div className="sense-graph">
      <div className="sg-header">
        <span className="sg-title">sense graph</span>
        <span className="sg-hint-inline">
          node size = rooms failing · number = co-failures
        </span>
      </div>

      <CyGraph
        nodes={nodes}
        edges={edges}
        onSelect={onSelect}
        selectedId={selectedId}
      />

      <div className="sg-legend">
        {SENSES.filter((s) => ["acoustic", "olfactory", "thermal"].includes(s)).map((s) => (
          <span key={s} className="sg-legend-item">
            <span className="sg-legend-dot" style={{ background: SC[s] }} />
            {s}
          </span>
        ))}
      </div>
    </div>
  );
}
