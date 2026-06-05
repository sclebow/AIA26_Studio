import { useEffect, useState } from "react";
import { motion } from "framer-motion";
import * as api from "../api/client.js";
import { SC, SI, SENSES, scoreColor, scoreOpacity } from "../lib/constants.js";
import { STATUS } from "../lib/senses.js";
import { useSelection } from "../lib/selection.jsx";
import { thresholdFromWeight, BASIS_ICON, basisBorder, LEVER_SENSE } from "../lib/senseModel.js";
import { roomByName, suggestionsFor, narrativeBullets } from "../lib/turn.js";
import { DUR, EASE } from "../lib/motion.js";
import Collapsible from "../ui/Collapsible.jsx";
import SenseSignature from "./SenseSignature.jsx";
import BeforeAfterSlider from "./BeforeAfterSlider.jsx";

/*
 * FocusCard — the per-room detail, replacing the generic bars/radar panel.
 * Shows for the bus-focused room: overall, the full signature (effective + base
 * ghost), per-sense rows (effective bar · personalized threshold · base→effective
 * with provenance), conflicts, suggestions, and a collapsible narrative.
 * "Why" lives here as readable HTML — never in-SVG text.
 */
// Levers a user can actually act on, mapped to a natural-language what-if the
// agent can route to a REAL edit tool (modify_glazing / change_material /
// add_furniture). The "lever bridge": a failing sense → its positive levers →
// one click to a real edit.
//
// IMPORTANT: the phrasing must route to an edit, NOT a full analysis. Words like
// "improve"/"fix"/"enhance" are full-analysis triggers in the action classifier,
// so we phrase each as a concrete edit instruction. "ventilation" is intentionally
// omitted — there is no ventilation edit tool in the backend, so it can't be a
// one-click fix (olfactory is still addressable via the "plants" lever).
const EDITABLE_LEVERS = {
  "glazing ratio":    (r) => `increase the window size in the ${r}`,   // → modify_glazing
  "glazing type":     (r) => `upgrade to triple glazing in the ${r}`,  // → modify_glazing
  "surface material": (r) => `change the floor to a soft material in the ${r}`, // → change_material
  "plants":           (r) => `add a plant to the ${r}`,                // → add_furniture
};

export default function FocusCard({ turn, persona, onClose, onFix }) {
  const { activeRoom, focusSense, toggleSense } = useSelection();

  // Generative "how it feels" render (Phase 1) — on-demand, reset per room.
  const [render, setRender] = useState({ loading: false, url: null, error: null });
  useEffect(() => { setRender({ loading: false, url: null, error: null }); }, [activeRoom]);
  const doRender = async (force = false) => {
    setRender({ loading: true, url: null, error: null });
    try {
      const d = await api.renderRoom(activeRoom, force);
      if (d.ok) setRender({ loading: false, url: d.image_base64, error: null });
      else setRender({ loading: false, url: null, error: d.error || "render failed" });
    } catch (e) {
      setRender({ loading: false, url: null, error: String(e.message || e) });
    }
  };

  // Before/after compare (Phase 2) — auto when THIS room was the most recent edit.
  const wasEdited = !!(turn?.layout_diff && turn.layout_diff.room_name === activeRoom && turn.layout_diff.attribute);
  const [compare, setCompare] = useState({ loading: false, data: null, error: null });
  useEffect(() => {
    if (!wasEdited) { setCompare({ loading: false, data: null, error: null }); return; }
    let alive = true;
    setCompare({ loading: true, data: null, error: null });
    api.compareRoom(activeRoom)
      .then((d) => { if (alive) setCompare(d.ok ? { loading: false, data: d, error: null } : { loading: false, data: null, error: d.error || "compare failed" }); })
      .catch((e) => { if (alive) setCompare({ loading: false, data: null, error: String(e.message || e) }); });
    return () => { alive = false; };
  }, [activeRoom, wasEdited, turn?.id]); // eslint-disable-line

  const room = roomByName(turn, activeRoom);
  if (!activeRoom || !room) return null;

  const weights = persona?.comfort_weights || {};
  const eff = room.comfortScores || {};
  const base = room.baseScores || {};
  const adjustments = room.adjustments || [];
  const overall = room.overallScore ?? 0;

  const roomSugg = suggestionsFor(turn, activeRoom);
  const whyBullets = narrativeBullets(turn, activeRoom);

  const thr = (s) => thresholdFromWeight(weights[s] ?? 0.5);
  const failing = SENSES.filter((s) => (eff[s] ?? 1) < thr(s));
  const adjBySense = (s) => adjustments.filter((a) => a.sense === s);

  // lever bridge: positive, editable levers that fix the failing senses (deduped)
  const fixes = (() => {
    const seen = new Set(), out = [];
    failing.forEach((s) => LEVER_SENSE.forEach(([lever, sense, sign]) => {
      if (sense === s && sign === "+" && EDITABLE_LEVERS[lever] && !seen.has(lever)) { seen.add(lever); out.push({ lever, sense: s }); }
    }));
    return out;
  })();

  return (
    <motion.div
      className="focus-card"
      initial={{ opacity: 0, x: 16 }}
      animate={{ opacity: 1, x: 0 }}
      exit={{ opacity: 0, x: 16 }}
      transition={{ duration: DUR.base, ease: EASE.out }}
    >
      {/* header */}
      <div className="flex items-center gap-2 mb-2">
        <span className="fc-room">{activeRoom}</span>
        <span className="fc-overall" style={{ color: scoreColor(overall) }}>{overall.toFixed(2)}</span>
        {onClose && <button className="fc-close" onClick={onClose} aria-label="close">×</button>}
      </div>

      {/* signature (detail) */}
      <div className="flex justify-center py-1">
        <svg width="120" height="120" viewBox="0 0 120 120">
          <SenseSignature scores={eff} baseScores={base} size={120} showGlyphs title={activeRoom}
            activeSense={focusSense} onSelectSense={toggleSense} />
        </svg>
      </div>

      {/* generative render — before/after for a just-edited room (Phase 2),
          otherwise a single "how it feels" render (Phase 1) */}
      {wasEdited ? (
        <>
          <div className="fc-section-label">
            before / after — {compare.data?.attribute || turn.layout_diff.attribute}
          </div>
          {compare.loading && <div style={{ fontSize: 11, opacity: 0.6, padding: "12px 0" }}>rendering before / after…</div>}
          {compare.error && <div style={{ fontSize: 11, opacity: 0.7, color: SC.thermal }}>{compare.error}</div>}
          {compare.data && (
            <>
              <BeforeAfterSlider before={compare.data.before_image} after={compare.data.after_image} />
              <div className="flex flex-wrap gap-1.5" style={{ marginTop: 6 }}>
                {Object.entries(compare.data.deltas).map(([s, v]) => {
                  if (v.before == null || v.after == null) return null;
                  const d = v.after - v.before;
                  if (Math.abs(d) < 0.01) return null;
                  return (
                    <span key={s} style={{ fontSize: 11, border: `1px solid ${SC[s]}`, color: SC[s], borderRadius: 10, padding: "1px 7px" }}
                      title={`${s}: ${v.before.toFixed(2)} → ${v.after.toFixed(2)}`}>
                      {SI[s]} {v.before.toFixed(2)}→{v.after.toFixed(2)} {d > 0 ? "↑" : "↓"}
                    </span>
                  );
                })}
              </div>
            </>
          )}
        </>
      ) : (
        <>
          <div className="fc-section-label">how it feels</div>
          {render.url ? (
            <div className="fc-render-wrap">
              <img src={render.url} alt={`render of ${activeRoom}`}
                style={{ width: "100%", borderRadius: 8, display: "block", border: "1px solid rgba(var(--fg-rgb),0.14)" }} />
              <button className="fc-render-again" onClick={() => doRender(true)}
                style={{ marginTop: 6, fontSize: 11, opacity: 0.65, cursor: "pointer", background: "none", border: "none", color: "inherit" }}>
                ↻ re-render
              </button>
            </div>
          ) : (
            <button className="fc-render-btn" onClick={() => doRender(false)} disabled={render.loading}
              style={{ width: "100%", padding: "9px", borderRadius: 8, cursor: render.loading ? "default" : "pointer",
                background: "rgba(var(--fg-rgb),0.06)", color: "inherit",
                border: "1px solid rgba(var(--fg-rgb),0.2)", letterSpacing: "0.04em", fontSize: 12 }}>
              {render.loading ? "rendering this space…" : "✦ render this space"}
            </button>
          )}
          {render.error && (
            <div className="fc-render-err" style={{ fontSize: 11, opacity: 0.7, marginTop: 4, color: SC.thermal }}>{render.error}</div>
          )}
        </>
      )}

      {/* per-sense rows */}
      <div className="fc-section-label">senses</div>
      <div className="flex flex-col gap-1.5">
        {SENSES.map((s) => {
          const v = eff[s] ?? 0;
          const b = base[s];
          const moved = typeof b === "number" && Math.abs(b - v) >= 0.01;
          const t = thr(s);
          const adj = adjBySense(s);
          return (
            <div key={s} className="fc-row">
              <span className="fc-glyph" style={{ color: SC[s] }}>{SI[s]}</span>
              <span className="fc-sense">{s}</span>
              <div className="fc-track">
                <div className="fc-fill" style={{ width: `${v * 100}%`, background: SC[s], opacity: scoreOpacity(v) }} />
                <div className="fc-thresh" style={{ left: `${t * 100}%` }} title={`your threshold ${t.toFixed(2)}`} />
              </div>
              <span className="fc-val" style={{ color: v < t ? SC[s] : "rgba(var(--fg-rgb),0.5)" }}>{v.toFixed(2)}</span>
              {moved && (
                <span className="fc-delta" style={{ color: v > b ? STATUS.pass : STATUS.fail }}
                  title={adj.map((a) => `${a.mechanism} (${a.delta > 0 ? "+" : ""}${a.delta})`).join(" · ")}>
                  {b.toFixed(2)}→{v.toFixed(2)}
                  {adj.map((a, i) => (
                    <span key={i} className="fc-basis" style={{ borderBottomStyle: basisBorder(a.basis) }}>{BASIS_ICON[a.basis] || ""}</span>
                  ))}
                </span>
              )}
            </div>
          );
        })}
      </div>

      {/* conflicts */}
      {failing.length > 0 && (
        <>
          <div className="fc-section-label">conflicts — below your threshold</div>
          <div className="flex flex-wrap gap-1.5">
            {failing.map((s) => (
              <span key={s} className="fc-flag" data-sense={s} style={{ color: SC[s], borderColor: SC[s] }}>{SI[s]} {s}</span>
            ))}
          </div>
        </>
      )}

      {/* lever bridge — one click runs a what-if edit that improves a failing sense */}
      {onFix && fixes.length > 0 && (
        <>
          <div className="fc-section-label">fix it — run a what-if</div>
          <div className="flex flex-wrap gap-1.5">
            {fixes.map((f) => (
              <button key={f.lever} className="fc-fix" style={{ borderColor: SC[f.sense], color: SC[f.sense] }}
                onClick={() => onFix(EDITABLE_LEVERS[f.lever](activeRoom))}
                title={EDITABLE_LEVERS[f.lever](activeRoom)}>⚒ {f.lever}</button>
            ))}
          </div>
        </>
      )}

      {/* suggestions */}
      {roomSugg.length > 0 && (
        <>
          <div className="fc-section-label">suggestions</div>
          <div className="flex flex-col gap-1.5">
            {roomSugg.map((sg, i) => (
              <div key={i} className="fc-sugg">
                <span className="fc-glyph" style={{ color: SC[sg.sense] }}>{SI[sg.sense] || ""}</span>
                <span className="fc-sugg-text">{sg.suggestion}</span>
              </div>
            ))}
          </div>
        </>
      )}

      {/* narrative (collapsible) — short, room-specific bullet points */}
      {whyBullets.length > 0 && (
        <div className="fc-why">
          <Collapsible
            bodyClassName="fc-why-body"
            trigger={(open, toggle) => (
              <button className="fc-why-toggle" onClick={toggle}>
                {open ? "▾" : "▸"} what this means
              </button>
            )}
          >
            <ul className="fc-why-list">
              {whyBullets.map((b, i) => (
                <li key={i}>{b}</li>
              ))}
            </ul>
          </Collapsible>
        </div>
      )}
    </motion.div>
  );
}
