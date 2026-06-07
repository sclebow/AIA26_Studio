import { motion } from "framer-motion";
import { SC, SI, SENSES, scoreColor } from "../lib/constants.js";
import { useSelection } from "../lib/selection.jsx";
import { thresholdFromWeight, LEVER_SENSE } from "../lib/senseModel.js";
import { roomByName, suggestionsFor, narrativeBullets } from "../lib/turn.js";
import { DUR, EASE } from "../lib/motion.js";
import Collapsible from "../ui/Collapsible.jsx";
import SenseSignature from "./SenseSignature.jsx";
import SenseRows from "./SenseRows.jsx";

/*
 * FocusCard — the per-room detail, replacing the generic bars/radar panel.
 * Shows for the bus-focused room: overall, the full signature (effective + base
 * ghost), per-sense rows (effective bar · personalized threshold · base→effective
 * with provenance), conflicts, suggestions, and a collapsible narrative.
 * "Why" lives here as readable HTML — never in-SVG text.
 *
 * Pure analysis: image generation (the old "render this space" + before/after
 * slider) now lives in the Report (Act 3), not in explore.
 */
// Levers a user can actually act on, mapped to a natural-language what-if the
// agent routes to the unified `edit` action (edit_planner → apply_edits). The
// "lever bridge": a failing sense → its positive levers → one click to a real edit.
//
// IMPORTANT: the phrasing must route to an edit, NOT a full analysis. Words like
// "improve"/"fix"/"enhance" are full-analysis triggers in the action classifier,
// so we phrase each as a concrete edit instruction. "ventilation" is intentionally
// omitted — there is no ventilation edit in the backend, so it can't be a
// one-click fix (olfactory is still addressable via the "plants" lever).
const EDITABLE_LEVERS = {
  "glazing ratio":    (r) => `increase the window size in the ${r}`,   // → edit (glazing)
  "glazing type":     (r) => `upgrade to triple glazing in the ${r}`,  // → edit (glazing)
  "surface material": (r) => `change the floor to a soft material in the ${r}`, // → edit (material)
  "plants":           (r) => `add a plant to the ${r}`,                // → edit (furniture)
};

export default function FocusCard({ turn, persona, onClose, onFix }) {
  const { activeRoom, focusSense, toggleSense } = useSelection();

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

      {/* per-sense rows */}
      <div className="fc-section-label">senses</div>
      <SenseRows eff={eff} base={base} weights={weights} adjustments={adjustments} />

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
