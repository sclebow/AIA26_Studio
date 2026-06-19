import { biophilicProfile, LEAVES } from "../lib/biophilic.js";

// The biophilic FINGERPRINT — shown on room-select while the green lens is on. This is
// where the research depth lives (progressive disclosure): the 5 leaves filled/partial/
// hollow, each with its value + documented benefit, plus a playful one-line narrator and
// a one-tap "add greenery" for a room that has none.
const GREEN = "124,179,66";

const mark = (level) => (level >= 1 ? "●●" : level >= 0.5 ? "●" : "○");

function narrate(rec) {
  const have = LEAVES.filter((l) => rec.patterns[l.key].level > 0).map((l) => l.label);
  const miss = LEAVES.filter((l) => rec.patterns[l.key].level === 0).map((l) => l.label);
  if (rec.status === "thriving")
    return `thriving — ${have.slice(0, 3).join(", ")}.` + (miss.length ? ` only ${miss[0]} is missing.` : "");
  if (rec.status === "moderate")
    return `coming along — has ${have.join(", ") || "little"}; could use ${miss.slice(0, 2).join(" & ") || "more"}.`;
  return `a bit thirsty — no ${miss.slice(0, 3).join(", ")}. shall I tuck some green in?`;
}

export default function BiophilicCard({ layout, roomName, onClose, onGreen }) {
  const rec = biophilicProfile(layout).byName[roomName];
  if (!rec) return null;
  return (
    <div className="bio-card">
      <div className="bio-card-hdr">
        <span className="bio-card-name">{rec.name}</span>
        <span className="bio-card-score" style={{ color: `rgb(${GREEN})` }}>{rec.richness.toFixed(2)} · {rec.status}</span>
        <button className="bio-card-close" onClick={onClose}>×</button>
      </div>

      <div className="bio-leaves">
        {LEAVES.map((l) => {
          const p = rec.patterns[l.key];
          const on = p.level > 0;
          return (
            <div className={"bio-leaf-row" + (on ? "" : " is-off")} key={l.key}>
              <span className="bio-leaf-mark" style={{ color: on ? `rgb(${GREEN})` : undefined }}>{mark(p.level)}</span>
              <span className="bio-leaf-name">{l.label}</span>
              <span className="bio-leaf-val">{p.value}</span>
              <span className="bio-leaf-benefit">{l.benefit}</span>
            </div>
          );
        })}
      </div>

      <div className="bio-card-narr">{narrate(rec)}</div>

      {rec.plantCount === 0 && (
        <button className="bio-card-green" onClick={() => onGreen && onGreen(rec.name)}>+ add greenery</button>
      )}
    </div>
  );
}
