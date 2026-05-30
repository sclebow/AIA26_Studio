import { motion } from "framer-motion";
import { SC, SI, SENSES, scoreColor, scoreOpacity } from "../lib/constants.js";
import { useSelection } from "../lib/selection.jsx";
import { thresholdFromWeight, BASIS_ICON, basisBorder } from "../lib/senseModel.js";
import { roomByName, suggestionsFor } from "../lib/turn.js";
import { DUR, EASE } from "../lib/motion.js";
import Collapsible from "../ui/Collapsible.jsx";
import SenseSignature from "./SenseSignature.jsx";

/*
 * FocusCard — the per-room detail, replacing the generic bars/radar panel.
 * Shows for the bus-focused room: overall, the full signature (effective + base
 * ghost), per-sense rows (effective bar · personalized threshold · base→effective
 * with provenance), conflicts, suggestions, and a collapsible narrative.
 * "Why" lives here as readable HTML — never in-SVG text.
 */
export default function FocusCard({ turn, persona, onClose }) {
  const { activeRoom } = useSelection();

  const room = roomByName(turn, activeRoom);
  if (!activeRoom || !room) return null;

  const weights = persona?.comfort_weights || {};
  const eff = room.comfortScores || {};
  const base = room.baseScores || {};
  const adjustments = room.adjustments || [];
  const overall = room.overallScore ?? 0;

  const roomSugg = suggestionsFor(turn, activeRoom);

  const thr = (s) => thresholdFromWeight(weights[s] ?? 0.5);
  const failing = SENSES.filter((s) => (eff[s] ?? 1) < thr(s));
  const adjBySense = (s) => adjustments.filter((a) => a.sense === s);

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
          <SenseSignature scores={eff} baseScores={base} size={120} showGlyphs title={activeRoom} />
        </svg>
      </div>

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
                <span className="fc-delta" title={adj.map((a) => `${a.mechanism}`).join(" · ")}>
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

      {/* narrative (collapsible) */}
      {(turn?.score_interpretation || turn?.conflict_reasoning) && (
        <div className="fc-why">
          <Collapsible
            bodyClassName="fc-why-body"
            trigger={(open, toggle) => (
              <button className="fc-why-toggle" onClick={toggle}>
                {open ? "▾" : "▸"} what this means
              </button>
            )}
          >
            {turn.score_interpretation && <p>{turn.score_interpretation}</p>}
            {turn.conflict_reasoning && <p className="mt-2">{turn.conflict_reasoning}</p>}
            {turn.suggestion_critique && <p className="mt-2">{turn.suggestion_critique}</p>}
          </Collapsible>
        </div>
      )}
    </motion.div>
  );
}
