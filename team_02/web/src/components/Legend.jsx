import { useState } from "react";
import { SENSES, SC, STATUS } from "../lib/senses.js";

/*
 * Legend — compact corner key, STRICTLY per active lens: it only explains what's
 * actually on screen. North is docked here (the plan is drawn north-up). The
 * provenance line-style key lives with the FocusCard / sense-graph where it's
 * used — it was never a main-canvas encoding.
 */
export default function Legend({ layers = {} }) {
  const [open, setOpen] = useState(true);

  return (
    <div className="legend">
      <div className="legend-head">
        <button className="legend-toggle" onClick={() => setOpen((o) => !o)}>
          {open ? "▾" : "▸"} legend
        </button>
        <span className="legend-north" title="north — the plan is drawn north-up">
          <svg width="10" height="12" viewBox="0 0 10 12" aria-hidden="true">
            <polygon points="5,0 8.5,11 5,8.5 1.5,11" />
          </svg>
          N
        </span>
      </div>

      {open && (
        <div className="legend-body">
          <div className="legend-row">
            <span className="legend-key">color</span>
            <span className="legend-dots">
              {SENSES.map((s) => <span key={s} className="legend-dot" style={{ background: SC[s] }} />)}
            </span>
            <span className="legend-val">= which sense</span>
          </div>

          {layers.comfort && (
            <>
              <div className="legend-row">
                <span className="legend-key">shade</span>
                <span className="legend-ramp" />
                <span className="legend-val">faint = low · vivid = good</span>
              </div>
              <div className="legend-row">
                <span className="legend-key">ring</span>
                <svg className="legend-ring" width="15" height="15" viewBox="0 0 16 16" aria-hidden="true">
                  <circle cx="8" cy="8" r="6.5" fill="none" stroke="rgba(var(--fg-rgb),0.18)" strokeWidth="1.5" />
                  <path d="M8 1.5 A6.5 6.5 0 0 1 14 10.5" fill="none" stroke={STATUS.pass} strokeWidth="1.5" strokeLinecap="round" />
                </svg>
                <span className="legend-val">= room's overall score</span>
              </div>
            </>
          )}

          {layers.graph && (
            <>
              <div className="legend-row">
                <span className="legend-key">node</span>
                <span className="legend-val">= room (click to focus) · size = doors</span>
              </div>
              <div className="legend-row">
                <span className="legend-key">arrow</span>
                <svg className="legend-arrow" width="26" height="10" viewBox="0 0 26 10" aria-hidden="true">
                  <line x1="1" y1="5" x2="19" y2="5" stroke={SC.acoustic} strokeWidth="2.5" strokeDasharray="4 3" strokeLinecap="round" />
                  <polygon points="25,5 18,2 18,8" fill={SC.acoustic} />
                </svg>
                <span className="legend-val">sense bleeding worse→better · thicker = worse</span>
              </div>
              <div className="legend-row">
                <span className="legend-key">halo</span>
                <span className="legend-val">= structural room — removing it splits the plan</span>
              </div>
            </>
          )}
        </div>
      )}
    </div>
  );
}
