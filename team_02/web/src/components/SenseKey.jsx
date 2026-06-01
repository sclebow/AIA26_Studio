import { useState } from "react";
import SenseGraph from "./SenseGraph.jsx";

// Docked sense-coupling KEY — the universal "what couples to what" reference,
// always on the side (not a pop-out view). Node size = rooms failing that sense;
// edges = the canonical couplings (solid research / dashed physics). Click a node
// to solo that sense across the whole instrument. The per-room hubs show the
// REALIZED couplings; this is the model legend they read against.
export default function SenseKey({ rooms }) {
  const [open, setOpen] = useState(true);
  return (
    <div className="sense-key">
      <button className="legend-toggle" onClick={() => setOpen((o) => !o)}>
        {open ? "▾" : "▸"} sense couplings
      </button>
      {open && (
        <div className="sense-key-body">
          <SenseGraph rooms={rooms} size={150} />
          <div className="sense-key-hint">bigger node = more rooms fail this sense (score &lt; 0.5); smaller = fewer</div>
          <div className="sense-key-hint">solid research · dashed physics · click to solo</div>
        </div>
      )}
    </div>
  );
}
