import Collapsible from "../ui/Collapsible.jsx";
import SenseBar from "../viz/SenseBar.jsx";
import { SC, SI, SENSES, BASELINES, IMPLICATIONS } from "../lib/constants.js";
import { VETO_WEIGHT, THRESHOLD, BASELINE_GAP } from "../lib/scoringModel.js";

// Shared persona surface — used both as the onboarding REVEAL (PersonaScreen) and the
// in-layout recall drawer (ProfilePanel). Leads with meaning (who you are → what Sensi
// optimises for you → your aesthetic) and tucks the (now HONEST) math behind
// progressive disclosure. The math here mirrors python/comfort/sense_model.py exactly.
export default function PersonaCard({ persona, moodboardUrls = [], compact = false }) {
  const p = persona || {};
  const weights = p.comfort_weights || {};
  const pvb = p.preference_vs_baseline || {};
  const role = (p.role || "client").toLowerCase();
  const priorities = p.sensory_priorities || SENSES;
  const gapSenses = Object.keys(pvb).filter((s) => pvb[s] && typeof pvb[s] === "string");

  const roleTxt = p.role ? p.role.charAt(0).toUpperCase() + p.role.slice(1) : "";
  const lifeTxt = p.lifestyle ? " · " + p.lifestyle : "";
  const members = (p.household_members || []).filter(Boolean);

  return (
    <div className={"persona-card" + (compact ? " persona-card-compact" : "")}>
      {/* ── Identity ───────────────────────────────────────────────── */}
      <div className="persona-identity">
        <div className="persona-name">{p.name || "Your profile"}</div>
        <div className="persona-role">{roleTxt}{lifeTxt}</div>
        {members.length > 0 && (
          <div className="persona-household" title="Sensi factors these residents into your comfort scores">
            lives with {members.join(", ")}
          </div>
        )}
        {p.description && <p className="persona-desc">{p.description}</p>}
      </div>

      {/* ── What Sensi will optimise for you (the hero) ────────────── */}
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

      {/* ── Full spectrum ─────────────────────────────────────────── */}
      <div className="persona-section-label">sense spectrum</div>
      <div className="bar-legend">
        <span><span style={{ display: "inline-block", width: 18, height: 2, background: "rgba(240,237,232,.45)", borderRadius: 2, verticalAlign: "middle", marginRight: 4 }} />stated</span>
        <span><span style={{ display: "inline-block", width: 1, height: 9, background: "rgba(240,237,232,.32)", verticalAlign: "middle", marginRight: 4 }} />evidence baseline</span>
      </div>
      <div style={{ width: "100%" }}>
        {SENSES.map((s) => {
          const w = weights[s] != null ? weights[s] : 0;
          return <SenseBar key={s} sense={s} value={w} baseline={BASELINES[s] || 0.5} />;
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

      {/* ── Aesthetic signature ───────────────────────────────────── */}
      {(moodboardUrls.length > 0 || p.aesthetic_preferences) && (
        <>
          <div className="persona-section-label">aesthetic signature</div>
          {moodboardUrls.length > 0 && (
            <div className="moodboard-strip">
              {moodboardUrls.slice(0, 6).map((url, i) => <img key={i} src={url} loading="lazy" alt="" />)}
            </div>
          )}
          {p.aesthetic_preferences && <p className="aesthetic-note">{p.aesthetic_preferences}</p>}
        </>
      )}

      {/* ── How Sensi built this — HONEST math, collapsed by default ─ */}
      <Collapsible
        bodyClassName="formula-content"
        trigger={(open, toggle) => (
          <div className="formula-toggle" onClick={toggle}>
            {open ? "how sensi scores your comfort −" : "how sensi scores your comfort +"}
          </div>
        )}
      >
        <div className="formula-eq-block">
          <div className="formula-eq-row"><span className="formula-eq-lhs">w(s)</span><span className="formula-eq-rhs">= learned( quiz, inspire )</span><span className="formula-eq-note">your weight per sense, 0–1</span></div>
          <div className="formula-eq-row"><span className="formula-eq-lhs">eff(room, s)</span><span className="formula-eq-rhs">= base(room) ± design ± cross-modal ± personality ± household</span><span className="formula-eq-note">the room's objective per-sense score — your weights never change it</span></div>
          <div className="formula-eq-row"><span className="formula-eq-lhs">C(room)</span><span className="formula-eq-rhs">= (1−{VETO_WEIGHT})·Σ w·eff / Σ w  +  {VETO_WEIGHT}·min eff</span><span className="formula-eq-note">weighted mean, blended 50/50 with your WORST sense</span></div>
          <div className="formula-eq-row"><span className="formula-eq-lhs">conflict(s)</span><span className="formula-eq-rhs">when eff(s) &lt; {THRESHOLD.base} + {THRESHOLD.span}·w(s)</span><span className="formula-eq-note">the bar rises the more you weight a sense</span></div>
        </div>
        <div className="formula-prose">
          Your per-sense scores are <em>objective</em> — built from the room's physics
          (daylight, glazing, materials, adjacency, ventilation), then nudged by
          cross-modal coupling (a failing sense drags its partners), your personality
          (introvert/extrovert tunes the stimulation senses), and your household (an
          elderly resident, children or pets make a deficit count for more). Every nudge
          is shown on the room card. Your comfort weights don't inflate these scores —
          they shape the <em>overall</em>: a weighted average that your top senses lead,
          but which is floored 50/50 by your single worst sense, so one bad sense always
          drags a room down. A conflict is flagged when a sense falls below a bar that
          rises with how much you care about it.
        </div>

        <Collapsible
          bodyClassName="formula-content"
          bodyStyle={{ marginTop: 10 }}
          trigger={(open, toggle) => (
            <div className="formula-toggle" onClick={toggle} style={{ marginTop: 18, marginBottom: 0 }}>
              {open ? "where your weights came from −" : "where your weights came from +"}
            </div>
          )}
        >
          <div className="formula-eq-row"><span className="formula-eq-lhs">q3 bothers</span><span className="formula-eq-rhs">floor → 0.80</span><span className="formula-eq-note">explicit comfort complaints</span></div>
          <div className="formula-eq-row"><span className="formula-eq-lhs">q5 non-negotiable</span><span className="formula-eq-rhs">+0.18 / signal · cap 0.90</span><span className="formula-eq-note">strongest preference statement</span></div>
          <div className="formula-eq-row"><span className="formula-eq-lhs">inspire text</span><span className="formula-eq-rhs">+0.08 / signal · cap 0.80</span><span className="formula-eq-note">your aesthetic description</span></div>
          <div className="formula-eq-row"><span className="formula-eq-lhs">moodboard picks</span><span className="formula-eq-rhs">+0.05 / image · cap +0.20</span><span className="formula-eq-note">visual sense selections</span></div>
          <div className="formula-eq-row"><span className="formula-eq-lhs">q2 space story</span><span className="formula-eq-rhs">+0.05 / signal · cap 0.75</span><span className="formula-eq-note">what made a space feel right</span></div>
          <div className="formula-eq-row"><span className="formula-eq-lhs">q4 household</span><span className="formula-eq-rhs">acoustic +0.07 · spatial +0.05</span><span className="formula-eq-note">shared living context</span></div>
          <div className="formula-prose" style={{ marginTop: 10 }}>Weights only ever increase — if a sense already scored high, it stays.</div>
        </Collapsible>

        <div style={{ marginTop: 14 }}>
          <div style={{ fontFamily: "var(--font-mono)", fontSize: 11, letterSpacing: ".12em", textTransform: "uppercase", color: "rgba(240,237,232,.25)", marginBottom: 8 }}>
            your weights · research baseline · delta
          </div>
          {SENSES.map((s) => {
            const w = weights[s] != null ? weights[s] : 0;
            const base = BASELINES[s] || 0.5;
            const delta = w - base;
            const deltaStr = (delta >= 0 ? "+" : "") + delta.toFixed(2);
            const deltaColor = Math.abs(delta) > BASELINE_GAP ? (delta > 0 ? "rgba(138,184,138,.80)" : "rgba(232,131,106,.80)") : "rgba(240,237,232,.28)";
            return (
              <div key={s} style={{ display: "flex", alignItems: "center", marginBottom: 6 }}>
                <span style={{ fontFamily: "var(--font-mono)", fontSize: 11, letterSpacing: ".10em", textTransform: "uppercase", color: SC[s], width: 80, flexShrink: 0 }}>{SI[s]} {s}</span>
                <span style={{ fontFamily: "var(--font-mono)", fontSize: 11, color: "rgba(240,237,232,.70)", width: 28, textAlign: "right", flexShrink: 0 }}>{w.toFixed(2)}</span>
                <span style={{ fontFamily: "var(--font-mono)", fontSize: 11, color: "rgba(240,237,232,.30)", margin: "0 6px" }}>vs</span>
                <span style={{ fontFamily: "var(--font-mono)", fontSize: 11, color: "rgba(240,237,232,.35)", width: 28, flexShrink: 0 }}>{base.toFixed(2)}</span>
                <span style={{ fontFamily: "var(--font-mono)", fontSize: 11, color: deltaColor, marginLeft: 8 }}>{deltaStr}</span>
              </div>
            );
          })}
        </div>
      </Collapsible>
    </div>
  );
}
