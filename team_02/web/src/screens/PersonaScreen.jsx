import { useState } from "react";
import SensiAvatar from "../components/SensiAvatar.jsx";
import { SC, SI, SENSES, BASELINES, IMPLICATIONS } from "../lib/constants.js";

// Full persona reveal (3c) — mirrors renderPersonaProfile + the formula section.
export default function PersonaScreen({ persona, message, moodboardUrls, onConfirm, onTweak }) {
  const p = persona || {};
  const weights = p.comfort_weights || {};
  const pvb = p.preference_vs_baseline || {};
  const role = (p.role || "client").toLowerCase();
  const priorities = p.sensory_priorities || SENSES;
  const gapSenses = Object.keys(pvb).filter((s) => pvb[s] && typeof pvb[s] === "string");

  const [formulaOpen, setFormulaOpen] = useState(false);
  const [signalsOpen, setSignalsOpen] = useState(false);

  const roleTxt = p.role ? p.role.charAt(0).toUpperCase() + p.role.slice(1) : "";
  const lifeTxt = p.lifestyle ? " · " + p.lifestyle : "";

  return (
    <div className="screen active">
      <div className="top-bar">
        <div className="top-bar-pill">
          <SensiAvatar size={26} className="" />
          <span className="top-bar-label">sensi</span>
          <span className="top-bar-sep">|</span>
          <span className="top-bar-section">onboarding</span>
          <span className="top-bar-sep">|</span>
          <div className="top-bar-step" style={{ background: "rgba(212,185,106,.10)", borderColor: "rgba(212,185,106,.22)" }}>
            <div className="top-bar-step-dot" style={{ background: "#D4B96A" }} />
            <span className="top-bar-step-text" style={{ color: "rgba(212,185,106,.90)" }}>profile reveal</span>
          </div>
        </div>
      </div>

      <div className="thread" style={{ flex: 1 }}>
        <div className="thread-inner" style={{ paddingTop: 20 }}>
          <div className="bubble-wrap">
            <SensiAvatar size={28} />
            <p className="bubble-s" style={{ marginBottom: 0 }}>{message || "here's what I know about you."}</p>
          </div>

          <div className="persona-identity">
            <div className="persona-name">{p.name || "Your"}</div>
            <div className="persona-role">{roleTxt}{lifeTxt}</div>
            {p.description && <p className="persona-desc">{p.description}</p>}
          </div>

          <div className="persona-section-label">top comfort priorities</div>
          <div className="top3-grid">
            {priorities.slice(0, 3).map((s) => (
              <div className="top3-card" key={s} style={{ borderColor: `${SC[s]}33` }}>
                <div className="top3-icon" style={{ color: SC[s] }}>{SI[s]}</div>
                <div className="top3-sense" style={{ color: SC[s] }}>{s}</div>
                <div className="top3-note">{(IMPLICATIONS[s] && IMPLICATIONS[s][role]) || ""}</div>
              </div>
            ))}
          </div>

          <div className="persona-section-label">sense spectrum</div>
          <div className="bar-legend">
            <span><span style={{ display: "inline-block", width: 18, height: 2, background: "rgba(240,237,232,.45)", borderRadius: 2, verticalAlign: "middle", marginRight: 4 }} />stated</span>
            <span><span style={{ display: "inline-block", width: 1, height: 9, background: "rgba(240,237,232,.32)", verticalAlign: "middle", marginRight: 4 }} />evidence baseline</span>
          </div>
          <div style={{ width: "100%" }}>
            {SENSES.map((s) => {
              const w = weights[s] != null ? weights[s] : 0;
              const wPct = Math.min(100, Math.max(0, w * 100));
              const bPct = Math.min(100, Math.max(0, (BASELINES[s] || 0.5) * 100));
              return (
                <div className="pbar-row" key={s}>
                  <span className="pbar-lbl" style={{ color: SC[s] }}>{SI[s]} {s}</span>
                  <div className="pbar-track">
                    <div className="pbar-fill" style={{ width: `${wPct}%`, background: SC[s], opacity: 0.6 }} />
                    <div className="pbar-tick" style={{ left: `${bPct}%` }} />
                  </div>
                  <span className="pbar-val">{w.toFixed ? w.toFixed(1) : w}</span>
                </div>
              );
            })}
          </div>

          {gapSenses.length > 0 && (
            <>
              <div className="persona-section-label">stated preference · evidence baseline</div>
              <div>
                {gapSenses.map((s) => (
                  <div className="gap-item" key={s} style={{ borderColor: SC[s] || "rgba(240,237,232,.2)" }}>
                    <div className="gap-item-sense" style={{ color: SC[s] || "rgba(240,237,232,.4)" }}>{SI[s] || ""} {s}</div>
                    <div className="gap-item-note">{pvb[s]}</div>
                  </div>
                ))}
              </div>
            </>
          )}

          <div className="persona-section-label">aesthetic signature</div>
          <div className="moodboard-strip">
            {(moodboardUrls || []).slice(0, 6).map((url, i) => <img key={i} src={url} loading="lazy" alt="" />)}
          </div>
          {p.aesthetic_preferences && <p className="aesthetic-note">{p.aesthetic_preferences}</p>}

          <div className="formula-toggle" onClick={() => setFormulaOpen((o) => !o)}>
            {formulaOpen ? "how sensi built this −" : "how sensi built this +"}
          </div>
          {formulaOpen && (
            <div className="formula-content">
              <div className="formula-eq-block">
                <div className="formula-eq-row"><span className="formula-eq-lhs">w(s)</span><span className="formula-eq-rhs">= derive( quiz, inspire )</span><span className="formula-eq-note">learned from your responses</span></div>
                <div className="formula-eq-row"><span className="formula-eq-lhs">score(room, s)</span><span className="formula-eq-rhs">= w(s) × raw(room, s)</span><span className="formula-eq-note">weight × room data per sense</span></div>
                <div className="formula-eq-row"><span className="formula-eq-lhs">C(room)</span><span className="formula-eq-rhs">= Σ score(room, s)</span><span className="formula-eq-note">sum across all 6 senses</span></div>
                <div className="formula-eq-row"><span className="formula-eq-lhs">flag(s)</span><span className="formula-eq-rhs">= |w(s) − baseline(s)| &gt; 0.25</span><span className="formula-eq-note">proactive gap detection</span></div>
              </div>
              <div className="formula-prose">
                Your comfort weights were built from five sources: your sensory bothers (q3) set a floor for each affected sense; your non-negotiable (q5) gave the strongest keyword signal; your space story (q2) and inspire description added softer cues; and the images you selected in the moodboard contributed directly — each image is tagged with its dominant senses. Sensi then compared each final weight against <em>evidence baselines</em>: research-backed minimum comfort thresholds. Where your stated weight falls below a baseline, Sensi flags it proactively.
              </div>

              <div className="formula-toggle" onClick={() => setSignalsOpen((o) => !o)} style={{ marginTop: 18, marginBottom: 0 }}>
                {signalsOpen ? "weight sources −" : "weight sources +"}
              </div>
              {signalsOpen && (
                <div className="formula-content" style={{ marginTop: 10 }}>
                  <div className="formula-eq-row"><span className="formula-eq-lhs">q3 bothers</span><span className="formula-eq-rhs">floor → 0.80</span><span className="formula-eq-note">explicit comfort complaints</span></div>
                  <div className="formula-eq-row"><span className="formula-eq-lhs">q5 non-negotiable</span><span className="formula-eq-rhs">+0.18 / signal · cap 0.90</span><span className="formula-eq-note">strongest preference statement</span></div>
                  <div className="formula-eq-row"><span className="formula-eq-lhs">inspire text</span><span className="formula-eq-rhs">+0.08 / signal · cap 0.80</span><span className="formula-eq-note">your aesthetic description</span></div>
                  <div className="formula-eq-row"><span className="formula-eq-lhs">moodboard picks</span><span className="formula-eq-rhs">+0.05 / image · cap +0.20</span><span className="formula-eq-note">visual sense selections</span></div>
                  <div className="formula-eq-row"><span className="formula-eq-lhs">q2 space story</span><span className="formula-eq-rhs">+0.05 / signal · cap 0.75</span><span className="formula-eq-note">what made a space feel right</span></div>
                  <div className="formula-eq-row"><span className="formula-eq-lhs">q4 household</span><span className="formula-eq-rhs">acoustic +0.07 · spatial +0.05</span><span className="formula-eq-note">shared living context</span></div>
                  <div className="formula-prose" style={{ marginTop: 10 }}>Weights only ever increase — if the LLM already gave a sense a high score, it stays.</div>
                </div>
              )}

              <div style={{ marginTop: 14 }}>
                <div style={{ fontFamily: "'IBM Plex Mono', monospace", fontSize: 8, letterSpacing: ".12em", textTransform: "uppercase", color: "rgba(240,237,232,.25)", marginBottom: 8 }}>
                  your weights · research baseline · delta
                </div>
                {SENSES.map((s) => {
                  const w = weights[s] != null ? weights[s] : 0;
                  const base = BASELINES[s] || 0.5;
                  const delta = w - base;
                  const deltaStr = (delta >= 0 ? "+" : "") + delta.toFixed(2);
                  const deltaColor = Math.abs(delta) > 0.25 ? (delta > 0 ? "rgba(138,184,138,.80)" : "rgba(232,131,106,.80)") : "rgba(240,237,232,.28)";
                  return (
                    <div key={s} style={{ display: "flex", alignItems: "center", marginBottom: 6 }}>
                      <span style={{ fontFamily: "'IBM Plex Mono', monospace", fontSize: 8, letterSpacing: ".10em", textTransform: "uppercase", color: SC[s], width: 80, flexShrink: 0 }}>{SI[s]} {s}</span>
                      <span style={{ fontFamily: "'IBM Plex Mono', monospace", fontSize: 10, color: "rgba(240,237,232,.70)", width: 28, textAlign: "right", flexShrink: 0 }}>{w.toFixed(2)}</span>
                      <span style={{ fontFamily: "'IBM Plex Mono', monospace", fontSize: 8, color: "rgba(240,237,232,.30)", margin: "0 6px" }}>vs</span>
                      <span style={{ fontFamily: "'IBM Plex Mono', monospace", fontSize: 10, color: "rgba(240,237,232,.35)", width: 28, flexShrink: 0 }}>{base.toFixed(2)}</span>
                      <span style={{ fontFamily: "'IBM Plex Mono', monospace", fontSize: 8, color: deltaColor, marginLeft: 8 }}>{deltaStr}</span>
                    </div>
                  );
                })}
              </div>
            </div>
          )}
        </div>
      </div>

      <div className="input-area" style={{ maxWidth: 560, margin: "0 auto", width: "100%" }}>
        <div className="btn-row">
          <button className="btn-action btn-ghost" onClick={onTweak}>tweak it</button>
          <button className="btn-action" onClick={onConfirm}>this is me →</button>
        </div>
      </div>
    </div>
  );
}
