import { useLayoutEffect, useMemo, useRef, useState } from "react";
import { SC, SI, SENSES } from "../lib/constants.js";
import { SENSE_SENSE } from "../lib/senseModel.js";
import { VALENCE, edgeWidth } from "../lib/relationships.js";

// CheckpointGraph (Session 8 · v3) — the commit history as a bold horizontal RIPPLE
// graph. X = commits over time; each sense is a luminous strand on its OWN auto-zoomed
// scale (so a 0.02 move reads as clearly as a 0.2 move), and the strands weave/cross.
// Where an edit makes two COUPLED senses move together, a glowing valence-tinted arc
// braids them at that commit — the "ripple" that is the heart of Sensi. A node is a
// commit you can focus → restore; the uncommitted draft trails off dashed to "now".
//
// Pure SVG, no chart library. Reuses the coupling vocabulary (SENSE_SENSE, VALENCE,
// sense hues SC/SI) — nothing reinvented.

const H = 214;
const PAD = { t: 22, r: 26, b: 30, l: 16 };   // extra right pad for end-of-strand glyphs
const MIN_DX = 104;            // min px between commits before horizontal scroll
const MIN_RANGE = 0.05;        // floor so a flat sense stays gently flat, not full-swing
const MOVE_EPS = 0.006;        // a sense "moved" at a commit if |delta| exceeds this
const clamp01 = (v) => Math.max(0, Math.min(1, v));
const short = (s, n = 11) => (s && s.length > n ? s.slice(0, n - 1) + "…" : s || "");
const tierDash = (tier) => (tier === "inferred" ? "5 4" : "none");
const fmtTime = (iso) => { try { return new Date(iso).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }); } catch { return ""; } };

// Smooth horizontal-ease path through points — gives the strands a woven, organic feel.
function smooth(pts) {
  if (!pts.length) return "";
  if (pts.length === 1) return `M ${pts[0].x} ${pts[0].y}`;
  let d = `M ${pts[0].x.toFixed(1)} ${pts[0].y.toFixed(1)}`;
  for (let i = 1; i < pts.length; i++) {
    const p0 = pts[i - 1], p1 = pts[i], mx = (p0.x + p1.x) / 2;
    d += ` C ${mx.toFixed(1)} ${p0.y.toFixed(1)} ${mx.toFixed(1)} ${p1.y.toFixed(1)} ${p1.x.toFixed(1)} ${p1.y.toFixed(1)}`;
  }
  return d;
}

// Couplings that "fired" at a commit: a canonical SENSE_SENSE edge whose BOTH endpoints
// moved between this commit and the previous — honest "potential ripple", grounded in
// what actually co-moved (not a claimed causal chain).
function firedCouplings(prev, cur) {
  if (!prev || !cur) return [];
  const out = [];
  for (const [a, b, , sign, tier] of SENSE_SENSE) {
    if (sign === "0") continue;
    const da = cur[a] != null && prev[a] != null ? cur[a] - prev[a] : 0;
    const db = cur[b] != null && prev[b] != null ? cur[b] - prev[b] : 0;
    if (Math.abs(da) > MOVE_EPS && Math.abs(db) > MOVE_EPS) out.push({ a, b, sign, tier, mag: (Math.abs(da) + Math.abs(db)) / 2 });
  }
  return out;
}

export default function CheckpointGraph({ checkpoints = [], liveHead = null, viewedId = null, onView, onRestore, onClose }) {
  const scrollRef = useRef(null);
  const [vw, setVw] = useState(640);
  const [solo, setSolo] = useState(null);
  const [hover, setHover] = useState(null);   // { idx, mx, my }

  useLayoutEffect(() => {
    const el = scrollRef.current;
    if (!el || typeof ResizeObserver === "undefined") return;
    const update = () => setVw(el.clientWidth || 640);
    update();
    const ro = new ResizeObserver(update);
    ro.observe(el);
    return () => ro.disconnect();
  }, []);

  const rows = useMemo(() => {
    const r = checkpoints.map((cp) => ({
      id: cp.id, label: cp.is_initial ? "initial" : cp.label,
      means: cp.sense_means || {}, score: cp.avg_score, at: cp.created_at, live: false,
    }));
    if (liveHead) r.push({ id: "__live", label: "now", means: liveHead.sense_means || {}, score: liveHead.avg_score, live: true });
    return r;
  }, [checkpoints, liveHead]);

  // Per-sense auto-zoom: map each sense's own min→max (floored) to the full plot height,
  // so small moves read AND the independent strands weave and cross (the intertwining).
  const ranges = useMemo(() => {
    const out = {};
    for (const s of SENSES) {
      const vals = rows.map((r) => r.means[s]).filter((v) => v != null);
      if (!vals.length) { out[s] = { lo: 0, span: 1 }; continue; }
      const lo = Math.min(...vals), hi = Math.max(...vals);
      out[s] = { lo, span: Math.max(MIN_RANGE, hi - lo) };
    }
    return out;
  }, [rows]);

  if (!checkpoints.length) return null;

  const n = rows.length;
  const W = Math.max(vw, PAD.l + PAD.r + Math.max(1, n - 1) * MIN_DX);
  const innerH = H - PAD.t - PAD.b;
  const xAt = (i) => (n <= 1 ? W / 2 : PAD.l + ((W - PAD.l - PAD.r) * i) / (n - 1));
  const yAt = (s, v) => PAD.t + innerH * (1 - clamp01((v - ranges[s].lo) / ranges[s].span));
  const viewedIdx = rows.findIndex((r) => r.id === viewedId);
  const guideIdx = hover ? hover.idx : viewedIdx;

  const senseOpacity = (s) => (solo ? (solo === s ? 1 : 0.08) : 0.9);
  const senseWidth = (s) => (solo === s ? 3.2 : 2.4);
  const hv = hover ? rows[hover.idx] : null;

  return (
    <div className="cg-panel cg-panel-tall">
      <div className="cg-head">
        <span className="cg-title">senses across checkpoints</span>
        <div className="cg-legend">
          {SENSES.map((s) => (
            <button key={s} type="button" className={"cg-legend-chip" + (solo === s ? " active" : "")}
              style={{ color: SC[s] }} onClick={() => setSolo((c) => (c === s ? null : s))}
              title={solo === s ? "show all senses" : `solo ${s}`}>
              <span className="cg-legend-glyph">{SI[s]}</span>{s}
            </button>
          ))}
        </div>
        <button type="button" className="cg-close" onClick={() => onClose?.()} title="close graph">✕</button>
      </div>

      <div className="cg-caption">
        each line is a sense — it <b>rises as that sense improves</b> · glowing arcs = the <b>ripple</b> (senses that moved together) · dashed = uncommitted · hover a step for exact scores
      </div>

      <div className="cg-scroll" ref={scrollRef}>
        <svg className="cg-svg" width={W} height={H} onMouseLeave={() => setHover(null)}>
          {/* focused / hovered commit guide */}
          {guideIdx >= 0 && <line x1={xAt(guideIdx)} y1={PAD.t - 6} x2={xAt(guideIdx)} y2={H - PAD.b + 4} className="cg-guide" />}

          {/* coupling braids — glowing valence arcs where two coupled senses co-moved */}
          {rows.map((r, i) => {
            if (i === 0) return null;
            const x = xAt(i);
            return firedCouplings(rows[i - 1].means, r.means).map((f, k) => {
              if (solo && solo !== f.a && solo !== f.b) return null;
              const ya = yAt(f.a, r.means[f.a]), yb = yAt(f.b, r.means[f.b]);
              const midy = (ya + yb) / 2, bow = 14 + Math.min(16, f.mag * 140);
              const tint = VALENCE[f.sign]?.tint || VALENCE["0"].tint;
              const d = `M ${x} ${ya.toFixed(1)} Q ${(x - bow).toFixed(1)} ${midy.toFixed(1)} ${x} ${yb.toFixed(1)}`;
              return (
                <g key={`c${i}_${k}`} pointerEvents="none">
                  <path d={d} fill="none" stroke={tint} strokeWidth={edgeWidth(f.mag) + 4} strokeOpacity="0.16" strokeLinecap="round" />
                  <path d={d} fill="none" stroke={tint} strokeWidth={edgeWidth(f.mag)} strokeOpacity={r.live ? 0.6 : 0.95}
                    strokeDasharray={tierDash(f.tier)} strokeLinecap="round" />
                  <text x={x - bow - 2} y={midy + 3} className="cg-braid-glyph" fill={tint} textAnchor="middle">{VALENCE[f.sign]?.glyph}</text>
                </g>
              );
            });
          })}

          {/* sense strands — bold, luminous, woven (each on its own auto-zoom) */}
          {SENSES.map((s) => {
            const pts = rows.map((r, i) => (r.means[s] != null ? { x: xAt(i), y: yAt(s, r.means[s]), live: r.live } : null)).filter(Boolean);
            if (pts.length < 1) return null;
            const solid = pts.filter((p) => !p.live);
            const dSolid = smooth(solid);
            const tail = liveHead && pts.length >= 2 && pts[pts.length - 1].live ? smooth([solid[solid.length - 1], pts[pts.length - 1]]) : "";
            return (
              <g key={s} style={{ opacity: senseOpacity(s), transition: "opacity .2s" }}>
                <path d={dSolid} className="cg-glow" stroke={SC[s]} />
                <path d={dSolid} fill="none" stroke={SC[s]} strokeWidth={senseWidth(s)} strokeLinecap="round" strokeLinejoin="round" />
                {tail && <path d={tail} fill="none" stroke={SC[s]} strokeWidth={senseWidth(s)} strokeDasharray="3 4" strokeLinecap="round" />}
                {pts.map((p, i) => <circle key={i} cx={p.x} cy={p.y} r={solo === s ? 3 : 2.1} fill={SC[s]} opacity={p.live ? 0.7 : 1} />)}
                {/* glyph at the strand's end so you can trace which line is which sense */}
                <text x={pts[pts.length - 1].x + 7} y={pts[pts.length - 1].y + 3.5} className="cg-end-glyph" fill={SC[s]}>{SI[s]}</text>
              </g>
            );
          })}

          {/* per-commit hit columns + x labels */}
          {rows.map((r, i) => {
            const x = xAt(i), dx = n > 1 ? (W - PAD.l - PAD.r) / (n - 1) : W;
            return (
              <g key={r.id}>
                <rect x={x - dx / 2} y="0" width={dx} height={H - 14} fill="transparent"
                  onMouseEnter={(e) => setHover({ idx: i, mx: e.clientX, my: e.clientY })}
                  onMouseMove={(e) => setHover({ idx: i, mx: e.clientX, my: e.clientY })}
                  onClick={() => !r.live && onView?.(r.id)} style={{ cursor: r.live ? "default" : "pointer" }} />
                <text x={x} y={H - 9} className={"cg-x-label" + (r.live ? " live" : "") + (i === viewedIdx ? " focused" : "")} textAnchor="middle">
                  {short(r.label)}
                </text>
              </g>
            );
          })}
        </svg>
      </div>

      {hv && (
        <div className="plan-tooltip cg-tooltip" style={{
          left: hover.mx + 16 + 220 > window.innerWidth ? Math.max(8, hover.mx - 236) : hover.mx + 16,
          top: hover.my + 16 + 188 > window.innerHeight ? Math.max(8, hover.my - 204) : hover.my + 16,
        }}>
          <div className="plan-tooltip-title">{hv.live ? "uncommitted · now" : hv.label}</div>
          <div className="plan-tooltip-row"><span>whole-home</span><span>{hv.score != null ? hv.score.toFixed(2) : "—"}</span></div>
          {SENSES.map((s) => {
            const cur = hv.means[s];
            if (cur == null) return null;
            const prev = hover.idx > 0 ? rows[hover.idx - 1].means[s] : null;
            const d = prev != null ? cur - prev : null;
            const arrow = d == null ? "" : d > MOVE_EPS ? " ↑" : d < -MOVE_EPS ? " ↓" : " ·";
            return (
              <div className="plan-tooltip-row" key={s}>
                <span style={{ color: SC[s] }}>{SI[s]} {s}</span>
                <span className={d > MOVE_EPS ? "cg-tip-val up" : d < -MOVE_EPS ? "cg-tip-val down" : "cg-tip-val"}>{cur.toFixed(2)}{arrow}</span>
              </div>
            );
          })}
          {!hv.live && <div className="plan-tooltip-why">committed {fmtTime(hv.at)} · click to focus</div>}
          {hv.live && <div className="plan-tooltip-why">edits not yet committed</div>}
        </div>
      )}

      {viewedIdx >= 0 && !rows[viewedIdx].live && (
        <div className="cg-restore-row">
          <span className="cg-restore-label">viewing · {rows[viewedIdx].label}</span>
          <button type="button" className="layer-pill" onClick={() => {
            if (window.confirm(`Restore to "${rows[viewedIdx].label}"? This discards any uncommitted edits.`)) onRestore?.(viewedId);
          }}>↺ restore</button>
        </div>
      )}
    </div>
  );
}
