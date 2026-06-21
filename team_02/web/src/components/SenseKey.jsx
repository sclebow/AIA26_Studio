import SenseGraph from "./SenseGraph.jsx";
import { useSelection } from "../lib/selection.jsx";

// Sense-coupling KEY PLAN — drawn straight onto the canvas (no card), the way an
// architectural drawing carries a small key in the corner. It is both the universal
// "what couples to what" reference AND the single sense filter: tap a node to focus
// that sense across the whole instrument; "all" clears it.
export default function SenseKey({ rooms }) {
  const { activeSense, setActiveSense } = useSelection();
  return (
    <div className="sense-key">
      <div className="sense-key-head">
        <span className="sense-key-title">sense couplings</span>
        {activeSense && (
          <button className="sense-key-clear" onClick={() => setActiveSense(null)} title="show all senses">all</button>
        )}
      </div>
      <div className="sense-key-cta">tap a sense to focus</div>
      <div className="sense-key-body">
        <SenseGraph rooms={rooms} size={180} />
      </div>
      <div className="sense-key-hint">node size = rooms failing this sense</div>
      <div className="sense-key-prov">
        <span className="prov-item">
          <svg width="20" height="4" viewBox="0 0 20 4" aria-hidden="true"><line x1="0" y1="2" x2="20" y2="2" stroke="rgba(var(--fg-rgb),0.8)" strokeWidth="1.6" strokeLinecap="round" /></svg>
          research
        </span>
        <span className="prov-item">
          <svg width="20" height="4" viewBox="0 0 20 4" aria-hidden="true"><line x1="0" y1="2" x2="20" y2="2" stroke="rgba(var(--fg-rgb),0.8)" strokeWidth="1.6" strokeDasharray="5 4" strokeLinecap="round" /></svg>
          physics
        </span>
      </div>
    </div>
  );
}
