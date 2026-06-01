import { useEffect, useRef, useState } from "react";
import ForceGraph3D from "3d-force-graph";
import SpriteText from "three-spritetext";
import { UnrealBloomPass } from "three/addons/postprocessing/UnrealBloomPass.js";
import {
  FogExp2, Group, Vector3, QuadraticBezierCurve3, BufferGeometry, Line, LineDashedMaterial,
  Mesh, SphereGeometry, OctahedronGeometry, MeshBasicMaterial, AdditiveBlending,
} from "three";
import { SENSES } from "../lib/constants.js";
import { buildRelationshipGraph, buildContext, GALAXY_LEGEND, LENSES, DEFAULT_LENSES } from "../lib/relationshipGraph.js";
import { childrenOf } from "../lib/galaxyChildren.js";
import { rippleSequence, worstSense } from "../lib/rippleSim.js";
import { clusterForce, SENSE_ANCHORS, recomputeCentroids, bundleControlPoints } from "./galaxyForces.js";

// The Relationship Galaxy — six sense-communities; links are delicate CURVED FIBERS
// bundled toward the community waist (DTI look), dashed where the basis is physics.
// Rooms = grey spheres, levers = bright-white wireframe diamonds. Meaning lenses;
// click to expand in place; click a sense (or ▶) to ripple; "concept" = fibers only.

function withAlpha(color, a) {
  if (typeof color !== "string") return color;
  if (color.startsWith("#")) { const n = parseInt(color.slice(1), 16); return `rgba(${(n >> 16) & 255},${(n >> 8) & 255},${n & 255},${a})`; }
  if (color.startsWith("rgba(")) return color.replace(/[\d.]+\)\s*$/, `${a})`);
  if (color.startsWith("rgb(")) return color.replace("rgb(", "rgba(").replace(")", `,${a})`);
  return color;
}
function baseColor(str) {
  if (typeof str !== "string") return "#ffffff";
  if (str[0] === "#") return str;
  const m = str.match(/rgba?\(([^)]+)\)/);
  if (m) { const p = m[1].split(",").map((x) => x.trim()); return `rgb(${p[0]},${p[1]},${p[2]})`; }
  return "#ffffff";
}
const dashFor = (basis) => (basis === "physics" ? { dashSize: 4, gapSize: 3 } : { dashSize: 1e5, gapSize: 0 });
const idOf = (x) => (x && typeof x === "object" ? x.id : x);
const linkKey = (l) => `${idOf(l.source)}|${idOf(l.target)}|${l.kind}`;

function nodeLabelHtml(n) {
  if (n.kind === "sense") return `<div class="gx-tip"><b>${n.label}</b><br/>rooms failing: ${n.fail} · click to ripple / expand</div>`;
  if (n.kind === "room") return `<div class="gx-tip"><b>${n.label}</b><br/>type ${n.rtype || "—"} · doors ${n.degree}${n.bridge ? " · structural" : ""}${n.isolated ? " · isolated" : ""}<br/>click to expand its senses + neighbours</div>`;
  if (n.kind === "score") return `<div class="gx-tip"><b>${n.label}</b></div>`;
  return `<div class="gx-tip"><b>${n.label}</b><br/>design lever · click to expand</div>`;
}

export default function RelationshipGalaxy({ turn, persona, onClose }) {
  const mountRef = useRef(null);
  const graphRef = useRef(null);
  const hlRef = useRef({ nodes: new Set(), links: new Set() });
  const focusRef = useRef({ nodes: new Set(), links: new Set(), active: false });   // ripple focus (priority over hover)
  const centroidsRef = useRef({});
  const ctxRef = useRef(null);
  const expandedRef = useRef(new Set());
  const ownersRef = useRef(new Map());
  const rippleTimersRef = useRef([]);
  const rippleMeshesRef = useRef([]);
  const rippleFocusRef = useRef(0);
  const rafRef = useRef(0);
  const hoverIvRef = useRef(0);
  const lensesRef = useRef(null);
  const conceptRef = useRef(false);
  const prevLensesRef = useRef(null);
  const [lenses, setLenses] = useState(() => new Set(DEFAULT_LENSES));
  const [playing, setPlaying] = useState(false);
  const [concept, setConcept] = useState(false);
  const [legendOpen, setLegendOpen] = useState(true);
  lensesRef.current = lenses;
  conceptRef.current = concept;

  const paintLink = (l) => {
    const lines = l.__lines;
    if (!lines) return;
    const f = focusRef.current, hl = hlRef.current;
    const base = l.__fiberOpacity ?? (l.opacity ?? 0.4);
    let op;
    if (f.active) op = f.links.has(l) ? Math.min(1, base + 0.45) : 0.006;
    else op = hl.links.size ? (hl.links.has(l) ? Math.min(1, base + 0.4) : 0.012) : base;
    lines.forEach((ln) => { ln.material.opacity = op; });
  };
  const nodeColorFn = (n) => {
    const f = focusRef.current, hl = hlRef.current;
    if (f.active) return f.nodes.has(n) ? n.color : withAlpha(n.color, 0.05);
    return (hl.nodes.size && !hl.nodes.has(n)) ? withAlpha(n.color, 0.1) : n.color;
  };
  // re-set nodeColor with a FRESH function each time so 3d-force-graph actually
  // recomputes node tints (re-setting the same reference is a no-op).
  const refreshHighlight = () => { const G = graphRef.current; if (!G) return; G.nodeColor((n) => nodeColorFn(n)); G.graphData().links.forEach(paintLink); };

  // ── ripple pulses travelling the fibers ──
  const tickRipple = () => {
    const G = graphRef.current; const arr = rippleMeshesRef.current;
    if (!G) { rafRef.current = 0; return; }
    for (let i = arr.length - 1; i >= 0; i--) {
      const p = arr[i];
      p.t += p.speed;
      if (p.t >= 1 || !p.curve) { G.scene().remove(p.mesh); p.mesh.geometry.dispose(); p.mesh.material.dispose(); arr.splice(i, 1); continue; }
      const pt = p.curve.getPoint(p.t);
      p.mesh.position.set(pt.x, pt.y, pt.z);
      p.mesh.material.opacity = Math.sin(p.t * Math.PI);
    }
    rafRef.current = arr.length ? requestAnimationFrame(tickRipple) : 0;
  };
  const spawnPulse = (curve, color, speed) => {
    const G = graphRef.current; if (!G || !curve) return;
    const mesh = new Mesh(new SphereGeometry(2.4, 8, 8),
      new MeshBasicMaterial({ color: baseColor(color), transparent: true, opacity: 0, blending: AdditiveBlending, depthWrite: false }));
    const p0 = curve.getPoint(0); mesh.position.set(p0.x, p0.y, p0.z);
    G.scene().add(mesh);
    rippleMeshesRef.current.push({ curve, t: 0, speed: speed || 0.012, mesh });
    if (!rafRef.current) rafRef.current = requestAnimationFrame(tickRipple);
  };
  const clearRipple = () => {
    rippleTimersRef.current.forEach(clearTimeout); rippleTimersRef.current = [];
    clearTimeout(rippleFocusRef.current);
    focusRef.current.active = false;
    hlRef.current.nodes.clear(); hlRef.current.links.clear();
    const G = graphRef.current;
    rippleMeshesRef.current.forEach((p) => { try { G && G.scene().remove(p.mesh); p.mesh.geometry.dispose(); p.mesh.material.dispose(); } catch { /* noop */ } });
    rippleMeshesRef.current = [];
    if (rafRef.current) { cancelAnimationFrame(rafRef.current); rafRef.current = 0; }
  };
  const fireRipple = (sourceSenseId, focus = false) => {
    const G = graphRef.current, ctx = ctxRef.current;
    if (!G || !ctx) return;
    const sense = idOf(sourceSenseId).replace("sense:", "");
    const couplings = G.graphData().links.filter((l) => l.kind === "coupling" && idOf(l.source).startsWith("sense:"));
    const findLink = (a, b) => couplings.find((l) => { const s = idOf(l.source).replace("sense:", ""), t = idOf(l.target).replace("sense:", ""); return (s === a && t === b) || (s === b && t === a); });
    const room = ctx.rooms.reduce((w, r) => ((r.comfortScores?.[sense] ?? 1) < (w?.comfortScores?.[sense] ?? 2) ? r : w), null);
    const seq = rippleSequence(sense, { room });
    const senses = new Set([sense]); const inLinks = new Set(); let maxDelay = 0;
    seq.forEach((step) => {
      senses.add(step.from); senses.add(step.to); maxDelay = Math.max(maxDelay, step.delay);
      const link = findLink(step.from, step.to); if (!link) return; inLinks.add(link);
      for (let i = 0; i < step.count; i++) { const t = setTimeout(() => spawnPulse(link.__curve, step.color, step.speed), step.delay + i * 130); rippleTimersRef.current.push(t); }
    });
    if (focus) {                                  // fade everything not in the ripple path
      const f = focusRef.current; f.nodes = new Set(); f.links = new Set();
      G.graphData().nodes.forEach((n) => { if (n.kind === "sense" && senses.has(n.sense)) f.nodes.add(n); });
      inLinks.forEach((l) => f.links.add(l));
      f.active = true;
      refreshHighlight();
      clearTimeout(rippleFocusRef.current);
      rippleFocusRef.current = setTimeout(() => { focusRef.current.active = false; hlRef.current.nodes.clear(); hlRef.current.links.clear(); refreshHighlight(); }, maxDelay + 3500);
    }
  };

  // ── expand / collapse in place ──
  const expand = (node) => {
    const G = graphRef.current, ctx = ctxRef.current;
    if (!G || !ctx) return;
    const { nodes, links } = G.graphData();
    const byId = new Map(nodes.map((n) => [n.id, n]));
    const have = new Set(links.map(linkKey));
    const jit = () => (Math.random() - 0.5) * 18;
    const addOwner = (cid) => { (ownersRef.current.get(cid) || ownersRef.current.set(cid, new Set()).get(cid)).add(node.id); };
    const c = childrenOf(node, ctx);
    c.nodes.forEach((n) => {
      const ex = byId.get(n.id);
      if (!ex) { n.x = (node.x || 0) + jit(); n.y = (node.y || 0) + jit(); n.z = (node.z || 0) + jit(); nodes.push(n); byId.set(n.id, n); addOwner(n.id); }
      else if (ex.parent) addOwner(n.id);
    });
    c.links.forEach((l) => { if (!have.has(linkKey(l))) { links.push(l); have.add(linkKey(l)); } });
    expandedRef.current.add(node.id);
    G.graphData({ nodes, links });
  };
  const collapse = (id) => {
    const G = graphRef.current; if (!G) return;
    let { nodes, links } = G.graphData();
    const remove = new Set();
    nodes.forEach((n) => {
      if (!n.parent) return;
      const owners = ownersRef.current.get(n.id);
      if (owners && owners.has(id)) { owners.delete(id); if (owners.size === 0) { remove.add(n.id); ownersRef.current.delete(n.id); expandedRef.current.delete(n.id); } }
    });
    links = links.filter((l) => l.owner !== id && !remove.has(l.owner) && !remove.has(idOf(l.source)) && !remove.has(idOf(l.target)));
    nodes = nodes.filter((n) => !remove.has(n.id));
    expandedRef.current.delete(id);
    G.graphData({ nodes, links });
  };

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
      .nodeRelSize(2.2)
      .nodeOpacity(0.78)
      .nodeVisibility(() => !conceptRef.current)              // "concept" hides nodes → pure fibers
      .nodeColor(nodeColorFn)
      .nodeThreeObjectExtend(true)
      .nodeThreeObject((n) => {
        if (n.kind === "sense") {
          const t = new SpriteText(` ${n.label} `);
          t.color = n.color; t.textHeight = 5; t.fontFace = "JetBrains Mono, monospace";
          t.backgroundColor = "rgba(13,13,13,0.72)"; t.padding = 2; t.borderRadius = 3;
          t.material.depthWrite = false; t.material.transparent = true;
          t.position.set(0, 10, 0);                            // float the chip above the node
          return t;
        }
        if (n.kind === "lever") {                              // small bright-white wireframe diamond (smallest tier)
          return new Mesh(new OctahedronGeometry(3.6, 0),
            new MeshBasicMaterial({ color: "#F2F4F8", wireframe: true, transparent: true, opacity: 0.6, depthWrite: false }));
        }
        return null;
      })
      .linkThreeObjectExtend(false)
      .linkThreeObject((l) => {
        // each connection = a BUNDLE of thin fanned sub-fibers (more in concept mode)
        const concept = conceptRef.current;
        const K = concept ? 8 : 1;                 // fanned bundles only in fiber view; single clean fibre normally
        const d = dashFor(l.basis);
        const fiberOpacity = (l.opacity ?? 0.4) * (concept ? 0.28 : 0.65);
        l.__fiberOpacity = fiberOpacity;
        const group = new Group();
        const lines = [];
        for (let i = 0; i < K; i++) {
          const line = new Line(new BufferGeometry(),
            new LineDashedMaterial({ color: baseColor(l.color), transparent: true, opacity: fiberOpacity, blending: AdditiveBlending, depthWrite: false, dashSize: d.dashSize, gapSize: d.gapSize }));
          group.add(line); lines.push(line);
        }
        group.userData = { seg: concept ? 22 : 18, K };
        l.__lines = lines;
        return group;
      })
      .linkPositionUpdate((group, { start, end }, l) => {
        const s = new Vector3(start.x, start.y, start.z), e = new Vector3(end.x, end.y, end.z);
        const { seg, K } = group.userData;
        const ctrls = bundleControlPoints(l, s, e, centroidsRef.current, K);
        for (let i = 0; i < K; i++) {
          const curve = new QuadraticBezierCurve3(s, ctrls[i], e);
          if (i === 0) l.__curve = curve;                  // ripple rides the centre fibre
          const line = l.__lines[i];
          line.geometry.setFromPoints(curve.getPoints(seg));
          line.computeLineDistances();
        }
        return true;
      })
      .nodeLabel(nodeLabelHtml)
      .onNodeHover((node) => {
        hl.nodes.clear(); hl.links.clear();
        if (node) {
          hl.nodes.add(node);
          G.graphData().links.forEach((l) => { if (l.source === node || l.target === node) { hl.links.add(l); hl.nodes.add(l.source); hl.nodes.add(l.target); } });
        }
        el.style.cursor = node ? "pointer" : "";
        refreshHighlight();
        if (hoverIvRef.current) { clearInterval(hoverIvRef.current); hoverIvRef.current = 0; }
        if (node && hl.links.size) {
          const flow = () => hlRef.current.links.forEach((l) => { if (l.__curve) spawnPulse(l.__curve, l.color, 0.02); });
          flow(); hoverIvRef.current = setInterval(flow, 650);
        }
      })
      .onNodeClick((node) => {
        if (node.kind === "sense") {                           // a sense → ripple + fade everything else
          if (lensesRef.current?.has("ripple")) fireRipple(node.id, true);
          if (G.zoomToFit) G.zoomToFit(1200, 70);
          return;
        }
        if (expandedRef.current.has(node.id)) collapse(node.id); else expand(node);
        const d = 80, r = 1 + d / Math.hypot(node.x || 1, node.y || 1, node.z || 1);
        G.cameraPosition({ x: (node.x || 0) * r, y: (node.y || 0) * r, z: (node.z || 0) * r }, node, 1200);
      })
      .onNodeDragEnd((node) => {
        node.fx = undefined; node.fy = undefined; node.fz = undefined;
        if (G.d3ReheatSimulation) G.d3ReheatSimulation();
      });

    const bloom = new UnrealBloomPass();
    bloom.strength = 0.9; bloom.radius = 0.85; bloom.threshold = 0.05;
    G.postProcessingComposer().addPass(bloom);
    G.scene().fog = new FogExp2(0x0d0d0d, 0.0009);

    G.d3Force("charge").strength(-100);
    const lf = G.d3Force("link"); if (lf) lf.distance((l) => (l.kind === "coupling" ? 70 : 30)).strength(0.08);
    G.d3Force("cluster", clusterForce({ strength: 0.22, getGroup: (n) => n.group, anchors: SENSE_ANCHORS }));
    G.d3VelocityDecay(0.4);
    G.cooldownTicks(300);
    G.onEngineTick(() => recomputeCentroids(G.graphData().nodes, centroidsRef.current));

    graphRef.current = G;
    const resize = () => G.width(el.clientWidth).height(el.clientHeight);
    resize();
    window.addEventListener("resize", resize);
    return () => {
      window.removeEventListener("resize", resize);
      if (hoverIvRef.current) clearInterval(hoverIvRef.current);
      clearRipple();
      try { G._destructor && G._destructor(); } catch { /* noop */ }
      if (el) el.replaceChildren();
    };
  }, []);

  // (re)build data on lens / turn change — reset expansion + seed at anchors
  useEffect(() => {
    const G = graphRef.current; if (!G) return;
    clearRipple();
    expandedRef.current = new Set();
    ownersRef.current = new Map();
    const ctx = buildContext(turn, persona);
    ctxRef.current = ctx;
    const data = buildRelationshipGraph(turn, persona, lenses);
    const j = () => (Math.random() - 0.5) * 28;
    data.nodes.forEach((n) => { const a = SENSE_ANCHORS[n.group]; if (a) { n.x = a.x + j(); n.y = a.y + j(); n.z = a.z + j(); } });
    G.graphData(data);
  }, [lenses, turn, persona]);

  // concept (fibers-only) toggle — hide nodes, max out the fibers (all lenses) for the
  // dense tractography read; restore the prior lenses on exit. Re-create link bundles
  // so the higher fiber count (K) takes effect.
  useEffect(() => {
    const G = graphRef.current; if (!G) return;
    if (concept) {
      prevLensesRef.current = lenses;
      const all = new Set(LENSES.map((L) => L.key));
      if ([...all].some((k) => !lenses.has(k))) setLenses(all);
      else G.linkThreeObject(G.linkThreeObject());
    } else if (prevLensesRef.current) {
      const prev = prevLensesRef.current; prevLensesRef.current = null;
      setLenses(prev);
    } else {
      G.linkThreeObject(G.linkThreeObject());
    }
    if (G.nodeVisibility) G.nodeVisibility(G.nodeVisibility());
  }, [concept]);

  // ripple Play loop — overview + cycle ambient ripples (no fade), worst senses first
  useEffect(() => {
    if (!playing) { clearRipple(); return; }
    const G = graphRef.current, ctx = ctxRef.current;
    if (!G || !ctx) return;
    if (G.zoomToFit) G.zoomToFit(1000, 70);
    const order = [...SENSES].sort((a, b) => (ctx.fail?.[b] || 0) - (ctx.fail?.[a] || 0));
    let i = 0;
    const fireNext = () => { fireRipple(`sense:${order[i % order.length]}`); i += 1; };
    const start = setTimeout(fireNext, 600);
    const iv = setInterval(fireNext, 2600);
    return () => { clearTimeout(start); clearInterval(iv); };
  }, [playing]);

  const toggleLens = (k) => setLenses((prev) => { const next = new Set(prev); next.has(k) ? next.delete(k) : next.add(k); return next; });
  const recenter = () => { const G = graphRef.current; if (G && G.zoomToFit) G.zoomToFit(800, 60); };

  return (
    <div className="galaxy-overlay">
      <div className="galaxy-canvas" ref={mountRef} />

      <div className="galaxy-top">
        <span className="galaxy-title">relationship galaxy</span>
        <div className="galaxy-levels">
          {LENSES.map((L) => (
            <button key={L.key} className={"galaxy-lv" + (lenses.has(L.key) ? " on" : "")} title={L.desc} onClick={() => toggleLens(L.key)}>{L.label}</button>
          ))}
          <button className={"galaxy-lv galaxy-play" + (playing ? " on" : "")} disabled={!lenses.has("ripple")}
            title={lenses.has("ripple") ? "" : "turn on the ripple lens first"} onClick={() => setPlaying((p) => !p)}>{playing ? "⏸ ripple" : "▶ ripple"}</button>
        </div>
        <button className={"galaxy-lv" + (concept ? " on" : "")} title="fiber view — bundles only, nodes dissolved" onClick={() => setConcept((c) => !c)}>fiber</button>
        <button className="galaxy-lv" title="recenter" onClick={recenter}>⤢</button>
        <button className="galaxy-close" onClick={onClose}>×</button>
      </div>

      <div className="galaxy-legend">
        <button className="galaxy-legend-toggle" onClick={() => setLegendOpen((o) => !o)}>{legendOpen ? "legend ▾" : "legend ▸"}</button>
        {legendOpen && (
          <div className="galaxy-legend-body">
            {GALAXY_LEGEND.map(([k, v]) => (
              <div className="galaxy-legend-row" key={k}><span className="galaxy-legend-key">{k}</span><span>{v}</span></div>
            ))}
            <div className="galaxy-legend-row" style={{ marginTop: 8 }}><span className="galaxy-legend-key" style={{ textTransform: "uppercase", letterSpacing: ".12em" }}>lenses</span><span /></div>
            {LENSES.map((L) => (
              <div className="galaxy-legend-row" key={L.key}><span className="galaxy-legend-key">{L.label}</span><span>{L.desc}</span></div>
            ))}
            <div className="galaxy-hint">click a node to expand · click a sense to ripple · drag a node, it springs back</div>
          </div>
        )}
      </div>
    </div>
  );
}
