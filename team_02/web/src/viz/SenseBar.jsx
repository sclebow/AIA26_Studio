import { SC, SI } from "../lib/senses.js";

// Sense spectrum bar (the old `pbar-row`) — identical markup was duplicated in
// PersonaScreen and ProfilePanel. One horizontal track per sense: fill width =
// value, an optional baseline tick, and a right-aligned value label. Colored at
// the sense's own hue (intensity convention).
//
//   value     0..1 — fill width
//   baseline  0..1 — tick position (omit to hide)
//   opacity   fill alpha (default 0.6, matching the spectrum look)
export default function SenseBar({ sense, value = 0, baseline, opacity = 0.6, valueLabel, className = "", style }) {
  const wPct = Math.min(100, Math.max(0, value * 100));
  const label = valueLabel != null ? valueLabel : (value.toFixed ? value.toFixed(1) : value);
  return (
    <div className={"pbar-row " + className} style={style}>
      <span className="pbar-lbl" style={{ color: SC[sense] }}>{SI[sense]} {sense}</span>
      <div className="pbar-track">
        <div className="pbar-fill" style={{ width: `${wPct}%`, background: SC[sense], opacity }} />
        {baseline != null && (
          <div className="pbar-tick" style={{ left: `${Math.min(100, Math.max(0, baseline * 100))}%` }} />
        )}
      </div>
      <span className="pbar-val">{label}</span>
    </div>
  );
}
