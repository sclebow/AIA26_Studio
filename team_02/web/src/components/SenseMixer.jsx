import { SC, SI, SENSES } from "../lib/constants.js";
import { useSelection } from "../lib/selection.jsx";

/*
 * SenseMixer — the persistent control rail for the senses.
 *
 * Replaces the old single-select lens row. Each pill carries hue + glyph +
 * label (so it teaches the sensory alphabet instead of hiding it behind a
 * cryptic symbol). Clicking a sense "solos" it; clicking it again, or "all",
 * clears back to the full picture. Hover previews via the selection bus, so
 * the whole instrument lights up before you even click.
 *
 * State lives in the shared selection bus (useSelection), not locally — this
 * rail is just the surface that drives it.
 */
export default function SenseMixer() {
  const { activeSense, toggleSense, setActiveSense, setHoverSense } = useSelection();

  return (
    <div className="sense-mixer" role="group" aria-label="sense layers">
      <button
        className={"mix-pill mix-all" + (activeSense == null ? " active" : "")}
        onClick={() => setActiveSense(null)}
        onMouseEnter={() => setHoverSense(null)}
        title="all senses"
      >
        all
      </button>
      {SENSES.map((s) => (
        <button
          key={s}
          className={"mix-pill" + (activeSense === s ? " active" : "")}
          data-sense={s}
          style={{ "--hue": SC[s] }}
          onClick={() => toggleSense(s)}
          onMouseEnter={() => setHoverSense(s)}
          onMouseLeave={() => setHoverSense(null)}
          title={s}
        >
          <span className="mix-dot" style={{ background: SC[s] }} />
          <span className="mix-glyph" style={{ color: SC[s] }}>{SI[s]}</span>
          <span className="mix-label">{s}</span>
        </button>
      ))}
    </div>
  );
}
