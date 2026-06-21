import { SC, STATUS } from "../lib/senses.js";

/*
 * Legend — reading-aids key as a horizontal strip in the top canvas band (beside
 * Expand All), card-less. Visual-first: each item is the ACTUAL mark used on the
 * canvas + a 1–2 word label, no "X = Y" prose. Lens-aware (only what's on screen).
 * The couplings key plan (bottom-left) is the sense-colour key, so colour isn't
 * repeated here. Topology findings (hub/bridge/isolated) live on the node hover.
 */
export default function Legend({ layers = {} }) {
  return (
    <div className="legend-top">
      {layers.comfort && (
        <>
          <span className="legend-seg">
            <span className="legend-ramp" />
            <span className="legend-val">low → good</span>
          </span>
          <span className="legend-seg">
            <svg className="legend-ring" width="14" height="14" viewBox="0 0 16 16" aria-hidden="true">
              <circle cx="8" cy="8" r="6.5" fill="none" stroke="rgba(var(--fg-rgb),0.18)" strokeWidth="1.5" />
              <path d="M8 1.5 A6.5 6.5 0 0 1 14 10.5" fill="none" stroke={STATUS.pass} strokeWidth="1.5" strokeLinecap="round" />
            </svg>
            <span className="legend-val">room score</span>
          </span>
        </>
      )}

      {layers.graph && (
        <>
          <span className="legend-seg">
            <svg className="legend-nodes" width="24" height="12" viewBox="0 0 24 12" aria-hidden="true">
              <circle cx="4" cy="6" r="2.2" fill="rgb(var(--fg-rgb))" fillOpacity="0.55" />
              <circle cx="16" cy="6" r="4.4" fill="rgb(var(--fg-rgb))" fillOpacity="0.55" />
            </svg>
            <span className="legend-val">room · more doors</span>
          </span>
          <span className="legend-seg">
            <svg className="legend-arrow" width="24" height="9" viewBox="0 0 26 10" aria-hidden="true">
              <line x1="1" y1="5" x2="19" y2="5" stroke={SC.acoustic} strokeWidth="2.5" strokeDasharray="4 3" strokeLinecap="round" />
              <polygon points="25,5 18,2 18,8" fill={SC.acoustic} />
            </svg>
            <span className="legend-val">sense bleed</span>
          </span>
          <span className="legend-seg legend-faint">hover a node → hub · bridge</span>
        </>
      )}

      <span className="legend-seg legend-north-seg" title="north — the plan is drawn north-up">
        <svg width="9" height="11" viewBox="0 0 10 12" aria-hidden="true"><polygon points="5,0 8.5,11 5,8.5 1.5,11" /></svg>
        <span className="legend-val">N</span>
      </span>
    </div>
  );
}
