import { useState } from "react";

/*
 * Legend — persistent compact corner key, context-sensitive to active layers.
 * Explains the encodings that are actually on screen (per user: data is
 * unreadable without a legend). Collapsible.
 */
export default function Legend({ layers = {} }) {
  const [open, setOpen] = useState(true);

  return (
    <div className="legend">
      <button className="legend-toggle" onClick={() => setOpen((o) => !o)}>
        {open ? "▾" : "▸"} legend
      </button>
      {open && (
        <div className="legend-body">
          <div className="legend-row">
            <span className="legend-key">hue</span>
            <span className="legend-val">= sense</span>
          </div>
          <div className="legend-row">
            <span className="legend-key">intensity</span>
            <span className="legend-ramp" aria-label="faint = failing, vivid = strong" />
            <span className="legend-val">= comfort</span>
          </div>
          <div className="legend-row">
            <span className="legend-key">line</span>
            <span className="legend-lines">
              <span className="legend-line solid" /> research
              <span className="legend-line dashed" /> physics
              <span className="legend-line dotted" /> personality
            </span>
          </div>
          {layers.flow && (
            <div className="legend-row">
              <span className="legend-key">flow</span>
              <span className="legend-val">= sense bleeding between rooms</span>
            </div>
          )}
          {layers.signatures && (
            <div className="legend-row">
              <span className="legend-key">rose</span>
              <span className="legend-val">= a room's 6-sense fingerprint</span>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
