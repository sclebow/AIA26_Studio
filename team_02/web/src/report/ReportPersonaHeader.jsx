import { SC, SI, SENSES } from "../lib/constants.js";

/*
 * ReportPersonaHeader — the Report's opening frame (flow-audit §6.1 + §6.3). Before the
 * dwelling is read room-by-room, it names WHO this dwelling was shaped for and replays the
 * aesthetic signature curated back in onboarding's inspire phase (§6.2). A slim recap, not
 * the full PersonaCard dump — leading with meaning and reusing the shared persona vocab
 * (SC/SI glyphs, .moodboard-strip, .persona-* classes) so the persona reads as one
 * companion across Onboard → Shape → Report rather than a gate left at the front door.
 */
export default function ReportPersonaHeader({ persona, moodboardUrls = [] }) {
  const p = persona || {};
  const name = p.name || "you";
  const roleTxt = p.role ? p.role.charAt(0).toUpperCase() + p.role.slice(1) : "";
  // lifestyle is free-text: short tags ("Streets of Paris") read well in the uppercase
  // mono line, but a full sentence would shout across three lines — only fold it in short.
  const lifeTxt = p.lifestyle && p.lifestyle.length <= 40 ? " · " + p.lifestyle : "";
  const members = (p.household_members || []).filter(Boolean);
  const priorities = (p.sensory_priorities || SENSES).slice(0, 3);
  const board = (moodboardUrls || []).filter(Boolean).slice(0, 6);
  const aesthetic = p.aesthetic_preferences;

  return (
    <section className="rp-header">
      <div className="rp-eyebrow">the vision</div>
      <h2 className="rp-frame">shaped for <span className="rp-name">{name}</span></h2>
      {(roleTxt || lifeTxt) && <div className="rp-role">{roleTxt}{lifeTxt}</div>}
      {members.length > 0 && (
        <div className="persona-household" title="Sensi factors these residents into every comfort score">
          lives with {members.join(", ")}
        </div>
      )}

      <div className="rp-leads">
        <span className="rp-leads-label">leads with</span>
        {priorities.map((s) => (
          <span
            className="rp-lead-chip"
            key={s}
            style={{ color: SC[s], borderColor: `${SC[s]}44` }}
          >
            <span className="rp-lead-icon">{SI[s]}</span>{s}
          </span>
        ))}
      </div>

      {(board.length > 0 || aesthetic) && (
        <div className="rp-aesthetic">
          <div className="persona-section-label">the aesthetic you curated</div>
          {board.length > 0 && (
            <div className="moodboard-strip">
              {board.map((url, i) => (
                <img key={i} src={url} crossOrigin="anonymous" loading="lazy" alt="" />
              ))}
            </div>
          )}
          {aesthetic && <p className="aesthetic-note">{aesthetic}</p>}
        </div>
      )}
    </section>
  );
}
