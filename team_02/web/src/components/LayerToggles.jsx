/*
 * LayerToggles — user-controlled on/off for the canvas data layers (hybrid control:
 * free toggles; the canvas auto-dims signatures when flow is loud). Separate from the
 * sense-solo mixer (which sets the lens).
 */
const LAYERS = [
  ["fill",       "comfort"],
  ["signatures", "signatures"],
  ["flow",       "flow"],
  ["topology",   "topology"],
];

export default function LayerToggles({ layers, onToggle }) {
  return (
    <div className="layer-toggles" role="group" aria-label="data layers">
      {LAYERS.map(([key, label]) => (
        <button
          key={key}
          className={"layer-pill" + (layers[key] ? " active" : "")}
          onClick={() => onToggle(key)}
          aria-pressed={!!layers[key]}
        >
          {label}
        </button>
      ))}
    </div>
  );
}
