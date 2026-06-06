import { useState } from "react";
import { SC, SI, SENSES, scoreColor } from "../lib/constants.js";
import { STATUS } from "../lib/senses.js";
import { thresholdFromWeight } from "../lib/senseModel.js";
import { roomByName, suggestionsFor, narrativeBullets } from "../lib/turn.js";
import SenseSignature from "../components/SenseSignature.jsx";
import SenseRows from "../components/SenseRows.jsx";
import Collapsible from "../ui/Collapsible.jsx";
import RenderSlot from "./RenderSlot.jsx";

// a room's overall in one word — a glance before the number
const verdictOf = (o) => (o >= 0.65 ? "serene" : o >= 0.5 ? "comfortable" : o >= 0.4 ? "strained" : "conflicted");
// narrative bullets are "sense: text" — pull the sense so we can colour/glyph it
const SENSE_RE = new RegExp(`^(${SENSES.join("|")})\\s*[:\\uFF1A]\\s*(.*)$`, "i");
function parseInsight(b) {
  const m = b.match(SENSE_RE);
  return m ? { sense: m[1].toLowerCase(), text: m[2] } : { sense: null, text: b };
}

// Exact mirror of imaging/prompt.py _SENSE_FRAGMENTS [low (<0.45), high (>0.70)].
// Used to locate each voiced sense's words inside the prompt so hovering a petal
// or chip can highlight the slice of language that sense produced.
const FRAG = {
  thermal:   ["a cool, slightly cold feel with bluish daylight", "a warm, cosy feel with golden light"],
  visual:    ["dim, harsh and visually cluttered with uneven lighting", "bright, airy and visually calm with balanced natural light"],
  acoustic:  ["hard reflective surfaces — bare concrete, glass and tile — that look acoustically live", "soft sound-absorbing textiles, rugs and drapes"],
  spatial:   ["cramped and tight with a low ceiling", "open, spacious and generous in volume"],
  olfactory: ["stuffy and closed with stale air", "fresh and well-ventilated, with a few plants"],
  tactile:   ["cold, hard, unwelcoming materials", "warm natural materials like wood and wool"],
};

/*
 * RoomReportCard — the per-room unit of the Report, built as the explicit loop
 * the whole product turns on: the scores → become a prompt → become an image.
 * Featured rooms (worst / most-recently-edited) open by default and render on
 * entry; the rest are collapsed and render lazily when expanded.
 *
 * `voiced` mirrors imaging/prompt.py: only a sense scored clearly low (<0.45) or
 * clearly high (>0.70) earns a fragment in the prompt — so a room's *weak* senses
 * set the mood. We surface exactly those senses to make the score→prompt link legible.
 */
const voicedTier = (v) => (v == null ? null : v < 0.45 ? "low" : v > 0.70 ? "high" : null);

function PromptText({ prompt, voiced, hoverSense }) {
  if (!voiced.length) return <>{prompt}</>;
  // Locate each voiced sense's exact fragment in the prompt; wrap it so hovering a
  // petal/chip lights up the words that sense produced. Keeps the true prompt text.
  const marks = voiced
    .map(([s, t]) => ({ s, text: FRAG[s][t === "low" ? 0 : 1] }))
    .filter((m) => prompt.includes(m.text))
    .sort((a, b) => prompt.indexOf(a.text) - prompt.indexOf(b.text));
  if (!marks.length) return <>{prompt}</>;
  const out = [];
  let cursor = 0;
  marks.forEach((m, i) => {
    const idx = prompt.indexOf(m.text, cursor);
    if (idx < 0) return;
    if (idx > cursor) out.push(prompt.slice(cursor, idx));
    out.push(
      <span key={i}
        className={"rr-frag rr-prompt-voiced" + (hoverSense === m.s ? " rr-frag-hi" : "")}
        style={hoverSense === m.s ? { color: SC[m.s] } : undefined}>
        {m.text}
      </span>
    );
    cursor = idx + m.text.length;
  });
  if (cursor < prompt.length) out.push(prompt.slice(cursor));
  return <>{out}</>;
}

export default function RoomReportCard({ room, turn, persona, img, defaultOpen = false, onRequestRender }) {
  const [hoverSense, setHoverSense] = useState(null);
  const name = room.room_name;
  const scored = roomByName(turn, name);                 // richer: baseScores + adjustments
  const eff = scored?.comfortScores || room.comfort_scores || {};
  const base = scored?.baseScores || {};
  const adjustments = scored?.adjustments || [];
  const weights = persona?.comfort_weights || {};
  const overall = room.overall_score ?? scored?.overallScore ?? 0;

  const voiced = SENSES.map((s) => [s, voicedTier(eff[s])]).filter(([, t]) => t);
  const sugg = suggestionsFor(turn, name);
  const why = narrativeBullets(turn, name);

  // per-sense health dot vs the persona's threshold (red below · green strong · neutral ok)
  const dotColor = (s) => {
    const v = eff[s];
    if (v == null) return "rgba(var(--fg-rgb),0.3)";
    const t = thresholdFromWeight(weights[s] ?? 0.5);
    return v < t ? STATUS.fail : v >= 0.65 ? STATUS.pass : "rgba(var(--fg-rgb),0.45)";
  };

  return (
    <div className={"rr-card" + (defaultOpen ? " rr-card--featured" : "")}>
      <Collapsible
        defaultOpen={defaultOpen}
        trigger={(open, toggle) => (
          <button className="rr-card-head" onClick={() => { if (!open) onRequestRender(name, false); toggle(); }}>
            <span className="rr-card-caret">{open ? "▾" : "▸"}</span>
            <span className="rr-card-name">{name}</span>
            {room.room_type && <span className="rr-card-type">{room.room_type}</span>}
            {defaultOpen && <span className="rr-card-flag">featured</span>}
            <span className="rr-card-verdict" style={{ color: scoreColor(overall) }}>{verdictOf(overall)}</span>
            <span className="rr-card-score" style={{ color: scoreColor(overall) }}>{overall.toFixed(2)}</span>
          </button>
        )}
      >
        <div className="rr-loop">
          {/* 1 · the scores */}
          <div className="rr-pane">
            <div className="rr-pane-label">the scores</div>
            <div className="rr-sig">
              <svg width="108" height="108" viewBox="0 0 108 108">
                <SenseSignature scores={eff} baseScores={base} size={108} showGlyphs title={name}
                  activeSense={hoverSense} onHoverSense={setHoverSense} />
              </svg>
            </div>
            <SenseRows eff={eff} base={base} weights={weights} adjustments={adjustments} />
          </div>

          <span className="rr-loop-arrow" aria-hidden="true">→</span>

          {/* 2 · become a prompt */}
          <div className="rr-pane">
            <div className="rr-pane-label">become a prompt</div>
            <div className="rr-prompt"><PromptText prompt={room.prompt || ""} voiced={voiced} hoverSense={hoverSense} /></div>
            {voiced.length > 0 && (
              <div className="rr-voiced">
                {voiced.map(([s, t]) => (
                  <span key={s}
                    className={"rr-voiced-chip" + (hoverSense === s ? " rr-voiced-chip--hi" : "")}
                    style={{ color: SC[s], borderColor: SC[s] }}
                    onMouseEnter={() => setHoverSense(s)}
                    onMouseLeave={() => setHoverSense(null)}>
                    {SI[s]} {s} {t === "low" ? "↓" : "↑"}
                  </span>
                ))}
              </div>
            )}
            <div className="rr-voiced-note">only a room's extreme senses are voiced — discomfort becomes visible</div>
          </div>

          <span className="rr-loop-arrow" aria-hidden="true">→</span>

          {/* 3 · become an image */}
          <div className="rr-pane">
            <div className="rr-pane-label">become an image</div>
            <RenderSlot img={img} roomName={name} onRender={(force) => onRequestRender(name, force)} />
          </div>
        </div>

        {(why.length > 0 || sugg.length > 0) && (
          <div className="rr-notes">
            {why.map((b, i) => {
              const { sense, text } = parseInsight(b);
              return (
                <div className="rr-insight" key={"w" + i}>
                  <span className="rr-insight-glyph" style={{ color: sense ? SC[sense] : "rgba(var(--fg-rgb),0.4)" }}>{sense ? SI[sense] : "·"}</span>
                  {sense && <span className="rr-insight-dot" style={{ background: dotColor(sense) }} title="vs your threshold" />}
                  <span className="rr-insight-text">{sense && <b style={{ color: SC[sense] }}>{sense}</b>} {text}</span>
                </div>
              );
            })}
            {sugg.map((sg, i) => (
              <div className="rr-insight rr-insight--fix" key={"s" + i}>
                <span className="rr-insight-glyph" style={{ color: SC[sg.sense] }}>⚒</span>
                <span className="rr-insight-text"><b style={{ color: SC[sg.sense] }}>{sg.sense}</b> {sg.suggestion}</span>
              </div>
            ))}
          </div>
        )}
      </Collapsible>
    </div>
  );
}
