import { SC, SI } from "../lib/constants.js";

/*
 * SenseDeltaPills — per-sense before→after chips for a single edit: one sense
 * rippling out to its neighbours. Driven by the compare deltas
 * { sense: { before, after } }. Senses that didn't move are skipped. Lifted from
 * FocusCard's old before/after block; now the Report's before/after hero uses it.
 */
export default function SenseDeltaPills({ deltas = {}, className = "flex flex-wrap gap-1.5", style = { marginTop: 6 } }) {
  return (
    <div className={className} style={style}>
      {Object.entries(deltas).map(([s, v]) => {
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
  );
}
