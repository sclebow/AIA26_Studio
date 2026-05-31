import { useEffect, useRef, useState } from "react";
import ForceGraph3D from "3d-force-graph";
import SpriteText from "three-spritetext";
import { UnrealBloomPass } from "three/addons/postprocessing/UnrealBloomPass.js";
import { buildRelationshipGraph, GALAXY_LEGEND } from "../lib/relationshipGraph.js";

// The Relationship Galaxy — a full-screen 3D force-directed view of the whole
// relationship system (senses + rooms + levers, four link types). Lazy-loaded so
// three/3d-force-graph never touch the initial bundle. See docs/adr-relationship-galaxy.md.

// alpha-stamp any color string (hex / rgb / rgba)
function withAlpha(color, a) {
  if (typeof color !== "string") return color;
  if (color.startsWith("#")) { const n = parseInt(color.slice(1), 16); return `rgba(${(n >> 16) & 255},${(n >> 8) & 255},${n & 255},${a})`; }
  if (color.startsWith("rgba(")) return color.replace(/[\d.]+\)\s*$/, `${a})`);
  if (color.startsWith("rgb(")) return color.replace("rgb(", "rgba(").replace(")", `,${a})`);
  return color;
}

function nodeLabelHtml(n) {
  if (n.kind === "sense") return `<div class="gx-tip"><b>${n.label}</b><br/>rooms failing: ${n.fail}</div>`;
  if (n.kind === "room") return `<div class="gx-tip"><b>${n.label}</b><br/>type ${n.rtype || "—"} · doors ${n.degree} · circulation ${(+n.betweenness).toFixed(2)}${n.bridge ? " · structural" : ""}${n.isolated ? " · isolated" : ""}</div>`;
  return `<div class="gx-tip"><b>${n.label}</b><br/>design lever</div>`;
}
function linkLabelHtml(l) {
  const a = l.source?.label || l.source, b = l.target?.label || l.target;
  return `<div class="gx-tip"><b>${a} → ${b}</b><br/>${l.mech || l.kind}${l.basis ? ` · ${l.basis}` : ""}</div>`;
}

export default function RelationshipGalaxy({ turn, persona, onClose }) {
  const mountRef = useRef(null);
  const graphRef = useRef(null);
  const hlRef = useRef({ nodes: new Set(), links: new Set() });
  const [level, setLevel] = useState(3);

  // init once
  useEffect(() => {
    const el = mountRef.current;
    if (!el) return;
    const hl = hlRef.current;
    const G = new ForceGraph3D(el)
      .backgroundColor("#0D0D0D")
      .showNavInfo(false)
      .nodeResolution(14)
      .nodeVal((n) => n.val)
      .nodeRelSize(2.4)
      .nodeOpacity(0.85)
      .nodeColor((n) => (hl.nodes.size && !hl.nodes.has(n)) ? withAlpha(n.color, 0.12) : n.color)
      .nodeThreeObjectExtend(true)
      .nodeThreeObject((n) => {
        if (n.kind === "lever") return null;
        const t = new SpriteText(n.label);
        t.color = n.color;
        t.textHeight = n.kind === "sense" ? 5 : 3.6;
        t.fontFace = "JetBrains Mono, monospace";
        t.material.depthWrite = false;
        t.material.transparent = true;
        return t;
      })
      .linkColor((l) => withAlpha(l.color, (hl.links.size && !hl.links.has(l)) ? 0.04 : l.opacity))
      .linkWidth((l) => (hl.links.has(l) ? l.width * 2 : l.width))
      .linkDirectionalArrowLength((l) => (l.arrow ? 2.6 : 0))
      .linkDirectionalArrowRelPos(1)
      .linkDirectionalParticles((l) => (hl.links.has(l) ? Math.max(2, l.particles || 0) : (l.particles || 0)))
      .linkDirectionalParticleWidth(1.4)
      .linkDirectionalParticleSpeed(0.008)
      .nodeLabel(nodeLabelHtml)
      .linkLabel(linkLabelHtml)
      .onNodeHover((node) => {
        hl.nodes.clear(); hl.links.clear();
        if (node) {
          hl.nodes.add(node);
          G.graphData().links.forEach((l) => {
            if (l.source === node || l.target === node) { hl.links.add(l); hl.nodes.add(l.source); hl.nodes.add(l.target); }
          });
        }
        el.style.cursor = node ? "pointer" : "";
        G.nodeColor(G.nodeColor()).linkColor(G.linkColor()).linkWidth(G.linkWidth()).linkDirectionalParticles(G.linkDirectionalParticles());
      })
      .onNodeClick((node) => {
        const d = 90, r = 1 + d / Math.hypot(node.x || 1, node.y || 1, node.z || 1);
        G.cameraPosition({ x: (node.x || 0) * r, y: (node.y || 0) * r, z: (node.z || 0) * r }, node, 1400);
      });

    const bloom = new UnrealBloomPass();
    bloom.strength = 0.55; bloom.radius = 0.4; bloom.threshold = 0.4;   // gentle glow — readable nodes
    G.postProcessingComposer().addPass(bloom);
    G.d3Force("charge").strength(-240);                                  // spread the stars
    const linkForce = G.d3Force("link"); if (linkForce) linkForce.distance(38);

    graphRef.current = G;
    const resize = () => G.width(el.clientWidth).height(el.clientHeight);
    resize();
    window.addEventListener("resize", resize);
    return () => {
      window.removeEventListener("resize", resize);
      try { G._destructor && G._destructor(); } catch { /* noop */ }
      if (el) el.replaceChildren();
    };
  }, []);

  // (re)build data on level / turn change
  useEffect(() => {
    const G = graphRef.current;
    if (!G) return;
    G.graphData(buildRelationshipGraph(turn, persona, level));
  }, [level, turn, persona]);

  return (
    <div className="galaxy-overlay">
      <div className="galaxy-canvas" ref={mountRef} />

      <div className="galaxy-top">
        <span className="galaxy-title">relationship galaxy</span>
        <div className="galaxy-levels">
          {[[1, "essentials"], [2, "full"], [3, "everything"]].map(([lv, name]) => (
            <button key={lv} className={"galaxy-lv" + (level === lv ? " on" : "")} onClick={() => setLevel(lv)}>L{lv} · {name}</button>
          ))}
        </div>
        <button className="galaxy-close" onClick={onClose}>×</button>
      </div>

      <div className="galaxy-legend">
        {GALAXY_LEGEND.map(([k, v]) => (
          <div className="galaxy-legend-row" key={k}><span className="galaxy-legend-key">{k}</span><span>{v}</span></div>
        ))}
        <div className="galaxy-hint">drag to orbit · scroll to zoom · hover to light up · click to fly in</div>
      </div>
    </div>
  );
}
