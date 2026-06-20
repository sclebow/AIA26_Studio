import { useState } from "react";
import { SC } from "../lib/constants.js";
import PersonaCard from "./PersonaCard.jsx";

// Slide-in comfort-profile drawer in layout mode — the persona as a companion while
// you shape. Renders the full PersonaCard (identity, priorities, spectrum, aesthetic,
// honest math), and lets you REFINE it by telling Sensi what changed (it patches the
// relevant bits — household/pets flow straight into scoring) or redo onboarding.
export default function ProfilePanel({ persona, moodboardUrls = [], open, onClose, onRefine, onRedo }) {
  const [draft, setDraft] = useState("");
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState("");

  const submit = async () => {
    const t = draft.trim();
    if (!t || busy || !onRefine) return;
    setBusy(true);
    setMsg("");
    try {
      const reply = await onRefine(t);
      setMsg(reply || "Updated your comfort profile.");
      setDraft("");
    } catch {
      setMsg("Couldn't update just now — try again.");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className={"profile-panel" + (open ? " open" : "")}>
      <div className="panel-header">
        <svg width="16" height="16" viewBox="0 0 32 32" fill="none" style={{ opacity: 0.5 }}>
          <circle cx="16" cy="16" r="14.5" stroke={SC.thermal} strokeWidth=".8" />
          <circle cx="16" cy="16" r="9.5" stroke={SC.acoustic} strokeWidth=".8" />
          <circle cx="16" cy="16" r="4.5" stroke={SC.olfactory} strokeWidth=".8" />
          <circle cx="16" cy="16" r="1.4" fill="var(--fg)" opacity=".80" />
        </svg>
        <span className="top-bar-label">comfort profile</span>
        <button className="panel-close" onClick={onClose} aria-label="close profile">×</button>
      </div>
      <div className="panel-scroll">
        <PersonaCard persona={persona} moodboardUrls={moodboardUrls} compact />

        {onRefine && (
          <div className="panel-refine">
            <div className="persona-section-label">refine</div>
            <p className="panel-refine-hint">tell Sensi what changed — it updates the rest for you.</p>
            <div className="send-row" style={{ alignItems: "flex-end" }}>
              <textarea
                className="sensi-input" rows={2} value={draft}
                placeholder="e.g. I got a dog, and noise bothers me more"
                onChange={(e) => setDraft(e.target.value)}
                onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); submit(); } }}
              />
              <button className="btn-send" onClick={submit} disabled={busy || !draft.trim()}
                title="update profile" aria-label="update profile">{busy ? "…" : "→"}</button>
            </div>
            {msg && <p className="panel-refine-msg">{msg}</p>}
          </div>
        )}

        {onRedo && (
          <button className="panel-redo" onClick={onRedo}>start over · redo onboarding</button>
        )}
      </div>
    </div>
  );
}
