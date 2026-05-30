/*
 * LayerToggles — the canvas layer rail (separate from the sense-solo mixer).
 *   plan     : architecture base (toggle off to isolate a graph lens)
 *   comfort  : fill tint + per-room score ring
 *   flow / topology : graph lenses (mutually exclusive — handled by the parent)
 * A lens whose data isn't computed yet renders greyed; clicking it asks Sensi to
 * run the analysis (click-to-run) instead of toggling an empty layer.
 */
const LAYERS = [
  ["plan",     "plan"],
  ["comfort",  "comfort"],
  ["flow",     "flow"],
  ["topology", "topology"],
];

export default function LayerToggles({ layers, onToggle, available = () => true }) {
  return (
    <div className="layer-toggles" role="group" aria-label="canvas layers">
      {LAYERS.map(([key, label]) => {
        const ok = available(key);
        const on = !!layers[key];
        return (
          <button
            key={key}
            className={"layer-pill" + (on ? " active" : "") + (ok ? "" : " unavailable")}
            onClick={() => onToggle(key)}
            aria-pressed={on}
            title={ok ? label : `run ${label} analysis`}
          >
            {label}
          </button>
        );
      })}
    </div>
  );
}
