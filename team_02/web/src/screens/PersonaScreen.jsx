import SensiAvatar from "../components/SensiAvatar.jsx";
import TopBar from "../ui/TopBar.jsx";
import PersonaCard from "../components/PersonaCard.jsx";
import { SC } from "../lib/constants.js";

// The earned reveal: lead with a warm line, then the shared PersonaCard (identity →
// priorities → spectrum → aesthetic → honest math). One CTA into layout — questions
// about the profile now live in the layout chat (and the persona is recallable there),
// so the old "tweak it" read-only detour is gone.
export default function PersonaScreen({ persona, message, moodboardUrls, onConfirm }) {
  const name = (persona && persona.name) || "you";

  return (
    <div className="screen active">
      <TopBar>
        <span className="top-bar-sep">|</span>
        <span className="top-bar-section">onboarding</span>
        <span className="top-bar-sep">|</span>
        <div className="top-bar-step" style={{ background: "rgba(212,185,106,.10)", borderColor: "rgba(212,185,106,.22)" }}>
          <div className="top-bar-step-dot" style={{ background: SC.visual }} />
          <span className="top-bar-step-text" style={{ color: "rgba(212,185,106,.90)" }}>profile reveal</span>
        </div>
      </TopBar>

      <div className="thread" style={{ flex: 1 }}>
        <div className="thread-inner" style={{ paddingTop: 20 }}>
          <div className="bubble-wrap">
            <SensiAvatar size={28} />
            <p className="bubble-s" style={{ marginBottom: 0 }}>
              {message || `Here's who I'll be designing for, ${name}.`}
            </p>
          </div>

          <PersonaCard persona={persona} moodboardUrls={moodboardUrls} />
        </div>
      </div>

      <div className="input-area" style={{ maxWidth: 560, margin: "0 auto", width: "100%" }}>
        <button className="btn-action" onClick={onConfirm} style={{ width: "100%" }}>
          this is me — start shaping →
        </button>
      </div>
    </div>
  );
}
