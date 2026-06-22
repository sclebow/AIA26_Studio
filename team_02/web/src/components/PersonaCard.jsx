import { useState } from "react";
import { motion, useReducedMotion } from "framer-motion";
import Collapsible from "../ui/Collapsible.jsx";
import SenseSignature from "./SenseSignature.jsx";
import { SC, SI, SENSES, BASELINES, IMPLICATIONS } from "../lib/constants.js";
import { VETO_WEIGHT } from "../lib/scoringModel.js";
import { EASE, DUR } from "../lib/motion.js";

// Shared persona surface — the onboarding REVEAL (PersonaScreen, full-screen, a HERO sense
// fingerprint that draws in, then a 3-up row cascades) AND the in-layout recall drawer
// (ProfilePanel, compact → stacks, no re-animation). The six senses read as ONE rose
// (your weight = petal, the average = dashed ghost + a bright baseline dot); hovering a petal
// OR a priority lights it and reads out "you vs average" — clarity on demand, poetic at rest.
// The scoring math is three honest lines with the exact formula one tap away. See DESIGN_SYSTEM.md.
export default function PersonaCard({ persona, moodboardUrls = [], compact = false }) {
  const p = persona || {};
  const weights = p.comfort_weights || {};
  const pvb = p.preference_vs_baseline || {};
  const role = (p.role || "client").toLowerCase();
  const priorities = p.sensory_priorities || SENSES;
  const roleTxt = p.role ? p.role.charAt(0).toUpperCase() + p.role.slice(1) : "";
  const members = (p.household_members || []).filter(Boolean);

  const [activeSense, setActiveSense] = useState(null);
  const reduce = useReducedMotion();
  const animate = !compact && !reduce;

  // framer-motion cascade: hero first, then the cards stagger (off in the drawer / reduced-motion)
  const rise = (delay) => animate
    ? { initial: { opacity: 0, y: 14 }, animate: { opacity: 1, y: 0 }, transition: { duration: DUR.slow, ease: EASE.out, delay } }
    : {};

  const cmp = (s) => ((weights[s] ?? 0) >= (BASELINES[s] ?? 0.5) ? "you care more than most" : "you care less than most");
  const readout = activeSense ? (
    <>
      <span style={{ color: SC[activeSense] }}>{SI[activeSense]} {activeSense}</span>
      {" — you "}{(weights[activeSense] ?? 0).toFixed(2)} · average {(BASELINES[activeSense] || 0.5).toFixed(2)} · {cmp(activeSense)}.
      {pvb[activeSense] ? " " + pvb[activeSense] : ""}
    </>
  ) : "hover a sense — or a priority — to see how you compare";

  return (
    <div className={"persona-reveal2" + (compact ? " is-compact" : "")}>

      {/* ── Hero (left): the sense fingerprint as the moment ───────────── */}
      <motion.div className="preveal-hero" {...rise(0.05)}>
        <SenseSignature
          scores={weights}
          baseScores={BASELINES}
          size={compact ? 168 : 230}
          showGlyphs
          baselineDot
          baselineTop
          reveal={animate}
          activeSense={activeSense}
          onSelectSense={(s) => setActiveSense(s)}
          onHoverSense={(s) => setActiveSense(s)}
          title={p.name || "your"}
        />
        <div className="preveal-hero-id">
          <span className="preveal-hero-name">{p.name || "Your profile"}</span>
          {roleTxt && <span className="preveal-hero-role">{roleTxt}</span>}
          {members.length > 0 && (
            <span className="preveal-hero-house" title="Sensi factors these residents into your comfort scores">
              ⌂ {members.join(", ")}
            </span>
          )}
        </div>
        <p className={"preveal-readout" + (activeSense ? " is-on" : "")}>{readout}</p>
        {p.description && <p className="preveal-bio">{p.description}</p>}
      </motion.div>

      {/* ── Evidence (right): three accordion panels — equal at rest, the hovered one grows
          (revealing its detail) while the others shrink back to their summary; fixed total
          area, so they never overlap and the page never shifts ── */}
      <div className="preveal-evidence">

        {/* priorities — hovering a row lights its petal; notes unfold on hover */}
        <motion.div className="preveal-card2" tabIndex={0} {...rise(0.18)} onMouseLeave={() => setActiveSense(null)}>
          <div className="persona-section-label">top priorities</div>
          {priorities.slice(0, 3).map((s) => (
            <div className="preveal-pri-row" key={s}
                 onMouseEnter={() => setActiveSense(s)}
                 style={{ borderColor: `${SC[s]}33`, background: activeSense === s ? `${SC[s]}14` : undefined }}>
              <span className="preveal-pri-head">
                <span className="preveal-pri-glyph" style={{ color: SC[s] }}>{SI[s]}</span>
                <span className="preveal-pri-name" style={{ color: SC[s] }}>{s}</span>
              </span>
              <span className="preveal-pri-note preveal-detail">{(IMPLICATIONS[s] && IMPLICATIONS[s][role]) || ""}</span>
            </div>
          ))}
        </motion.div>

        {/* aesthetic — the moodboard develops in; the note unfolds on hover */}
        <motion.div className="preveal-card2" tabIndex={0} {...rise(0.26)}>
          <div className="persona-section-label">aesthetic</div>
          {moodboardUrls.length > 0 && (
            <div className="preveal-board">
              {moodboardUrls.slice(0, 6).map((url, i) => (
                <motion.img key={i} src={url} loading="lazy" alt=""
                  {...(animate ? { initial: { opacity: 0 }, animate: { opacity: 0.7 }, transition: { duration: DUR.slow, delay: 0.45 + i * 0.07 } } : {})} />
              ))}
            </div>
          )}
          {p.aesthetic_preferences && <p className="aesthetic-note preveal-detail">{p.aesthetic_preferences}</p>}
        </motion.div>

        {/* how scoring works — three honest leads; the mechanism + formula unfold on hover */}
        <motion.div className="preveal-card2" tabIndex={0} {...rise(0.34)}>
          <div className="persona-section-label">how it's scored</div>
          <div className="preveal-scoring">
            <div className="psc-point"><span className="psc-mark">○</span>
              <div className="psc-body"><strong>Measured from the room.</strong>
                <span className="psc-rest preveal-detail"> Daylight, materials, air and layout set each sense's score.</span></div></div>
            <div className="psc-point"><span className="psc-mark">◐</span>
              <div className="psc-body"><strong>Your priorities choose what matters.</strong>
                <span className="psc-rest preveal-detail"> They weight the overall comfort — never a sense's own score.</span></div></div>
            <div className="psc-point"><span className="psc-mark">●</span>
              <div className="psc-body"><strong>The worst sense rules.</strong>
                <span className="psc-rest preveal-detail"> One weak sense always drags a room down.</span></div></div>
          </div>
          <div className="preveal-detail">
            <p className="psc-prov">Built from what bothers you, your non-negotiable, your space story and your moodboard picks.</p>
            <Collapsible
              bodyClassName="psc-formula"
              trigger={(open, toggle) => (
                <div className="psc-formula-toggle" onClick={toggle}>
                  {open ? "the exact formula −" : "the exact formula +"}
                </div>
              )}
            >
              <p className="psc-formula-line">
                C(room) = (1−{VETO_WEIGHT})·<span className="psc-dim">weighted mean of your senses</span> + {VETO_WEIGHT}·<span className="psc-dim">your worst sense</span>
              </p>
              <p className="psc-formula-note">A 50/50 blend of the weighted average and your single weakest sense — the same calculation, written out.</p>
            </Collapsible>
          </div>
        </motion.div>

      </div>
    </div>
  );
}
