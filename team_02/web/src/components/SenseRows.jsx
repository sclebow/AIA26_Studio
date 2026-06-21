import { SC, SI, SENSES, scoreOpacity } from "../lib/constants.js";
import { STATUS } from "../lib/senses.js";
import { thresholdFromWeight, BASIS_ICON, basisBorder } from "../lib/senseModel.js";

/*
 * SenseRows — the per-sense breakdown for one room: glyph · name · effective bar
 * with the personalized threshold tick · value · base→effective delta with
 * provenance icons. Lifted out of FocusCard so explore (FocusCard) and the Report
 * share one source of truth and can't drift. Pure presentational; all data is props.
 */
export default function SenseRows({ eff = {}, base = {}, weights = {}, adjustments = [] }) {
  const thr = (s) => thresholdFromWeight(weights[s] ?? 0.5);
  const adjBySense = (s) => adjustments.filter((a) => a.sense === s);
  return (
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
  );
}
