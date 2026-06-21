import { useEffect, useRef, useState } from "react";
import * as api from "../api/client.js";
import { SC, SI, SENSES, scoreColor } from "../lib/constants.js";
import { SENSE_SENSE, basisBorder } from "../lib/senseModel.js";
import { VALENCE } from "../lib/relationships.js";
import { useSelection } from "../lib/selection.jsx";
import { roomScores, layoutScore } from "../lib/turn.js";
import SenseGraph from "../components/SenseGraph.jsx";
import SenseSignature from "../components/SenseSignature.jsx";
import BeforeAfterSlider from "../components/BeforeAfterSlider.jsx";
import PromptText, { voicedFromScores } from "./PromptText.jsx";

// scrub interpolation: the slider handle drives scores/signature/prompt, not just
// the image. t = 1 (fully after) … 0 (fully before).
const lerp = (a, b, t) => (a == null || b == null ? (a ?? b ?? null) : a + (b - a) * t);
const mixScores = (deltas, t) => {
  const o = {};
  for (const [s, v] of Object.entries(deltas || {})) {
    o[s] = v.before != null && v.after != null ? lerp(v.before, v.after, t) : (v.after ?? v.before);
  }
  return o;
};
const sideScores = (deltas, side) => {
  const o = {};
  for (const [s, v] of Object.entries(deltas || {})) o[s] = v[side];
  return o;
};

// Every coupling that touches sense S (skip sign "0"), with the partner + sign +
// tier + mechanism — i.e. "the ripple of S": what it helps, harms, or trades with.
function ripplesFor(S) {
  const out = [];
  SENSE_SENSE.forEach(([a, b, , sign, tier, mech]) => {
    if (sign === "0" || (a !== S && b !== S)) return;
    out.push({ partner: a === S ? b : a, sign, tier, mech });
  });
  return out;
}

/*
 * DwellingStory — the head of The Vision: the whole home at a glance.
 *   1. a data-driven headline + the aggregate as a quiet status light.
 *   2. the sense-coupling diagram = how the senses talk to each other — INTERACTIVE:
 *      tap a sense to trace its ripple (what it helps / harms / trades with). Default
 *      names the weakest thread.
 *   3. "what your changes did" — the biggest-glow-up room, initial → now: a full-card
 *      scrub of the before/after render, with a morphing sense rose + the two overall
 *      numbers that interpolate as you drag, and the two prompts that drove it.
 */
export default function DwellingStory({ turn }) {
  const { activeSense, setActiveSense } = useSelection();
  const scoreRooms = roomScores(turn);
  const avg = layoutScore(scoreRooms);
  const ringClass = avg == null ? "" : avg >= 0.65 ? "score-pass" : avg >= 0.45 ? "score-warn" : "score-fail";

  // weakest sense across the home (most rooms failing < 0.5) + the room holding it back
  const failCount = {}; SENSES.forEach((s) => { failCount[s] = 0; });
  scoreRooms.forEach((r) => SENSES.forEach((s) => { if ((r.comfortScores?.[s] ?? 1) < 0.5) failCount[s]++; }));
  const worst = SENSES.reduce((a, b) => (failCount[b] > failCount[a] ? b : a), SENSES[0]);
  const worstN = failCount[worst];
  const worstRoom = scoreRooms.length
    ? scoreRooms.reduce((a, b) => ((a.overallScore ?? 1) <= (b.overallScore ?? 1) ? a : b))
    : null;

  const tone = avg == null ? "reads quiet" : avg >= 0.65 ? "reads largely at ease" : avg >= 0.45 ? "reads mixed" : "reads strained";
  const headline = worstN > 0
    ? `Your home ${tone} — ${worst} is the weakest thread${worstRoom ? `, hardest in the ${worstRoom.roomName}` : ""}.`
    : `Your home ${tone} — the couplings carry comfort, not drag it.`;

  const ripples = activeSense ? ripplesFor(activeSense) : [];

  // before/after — the biggest-glow-up room, initial (on-disk) → now (current).
  const [cmp, setCmp] = useState({ loading: true, data: null, error: null });
  const [pos, setPos] = useState(0.5);     // slider handle, 0..1 (left=before … right=after)
  useEffect(() => {
    let alive = true;
    api.compareInitial()
      .then((d) => { if (alive) setCmp(d.ok ? { loading: false, data: d, error: null } : { loading: false, data: null, error: d.error || "" }); })
      .catch((e) => { if (alive) setCmp({ loading: false, data: null, error: String(e.message || e) }); });
    return () => { alive = false; };
  }, []);
  const d = cmp.data;
  const changedLabel = d?.changed?.length ? d.changed.join(", ") : "";

  // the handle drives the whole readout, not just the image. t = after-ness:
  // handle far left reveals the after (t→1), far right reveals the before (t→0).
  const t = 1 - pos;
  const interp = d ? mixScores(d.deltas, t) : {};
  const baseScores = d ? sideScores(d.deltas, "before") : {};
  const roomNow = d ? lerp(d.room_before_overall, d.room_after_overall, t) : null;
  const homeNow = d ? lerp(d.dwelling_before, d.dwelling_after, t) : null;
  const beforeVoiced = d ? voicedFromScores(sideScores(d.deltas, "before")) : [];
  const afterVoiced = d ? voicedFromScores(sideScores(d.deltas, "after")) : [];

  // full-card scrub: drag anywhere on the hero to move the spine + the whole readout.
  const scrubRef = useRef(null);
  const setFromX = (clientX) => {
    const r = scrubRef.current?.getBoundingClientRect();
    if (!r || !r.width) return;
    setPos(Math.max(0, Math.min(1, (clientX - r.left) / r.width)));
  };
  const onScrubDown = (e) => { try { scrubRef.current?.setPointerCapture(e.pointerId); } catch { /* noop */ } setFromX(e.clientX); };
  const onScrubMove = (e) => { if (e.buttons) setFromX(e.clientX); };
  const railPos = Math.max(0.14, Math.min(0.86, pos)); // keep the centered readout on-card

  return (
    <section className="ds">
      <div className="ds-head">
        <div className={"ds-ring " + ringClass}>{avg != null ? avg.toFixed(2) : "—"}</div>
        <div className="ds-head-copy">
          <h1 className="ds-title">your home, read by the senses</h1>
          <p className="ds-headline">{headline}</p>
          <p className="ds-sub">the overall number isn't a grade to chase — it's the weakest teacher in the system.
            the real lesson lives in the edges: how a change to one sense ripples to another.</p>
        </div>
      </div>

      <div className="ds-couplings">
        <div className="ds-couplings-viz"><SenseGraph rooms={scoreRooms} size={220} /></div>
        <div className="ds-couplings-copy">
          <div className="ds-section-label">how your senses talk to each other</div>
          {activeSense ? (
            <>
              <p className="ds-lesson">
                the ripple of <span style={{ color: SC[activeSense] }}>{SI[activeSense]} {activeSense}</span> —
                how it moves the others:
              </p>
              <div className="ds-ripples">
                {ripples.map((r, i) => (
                  <div className="ds-ripple-row" key={i}>
                    <span className="ds-ripple-val" style={{ color: VALENCE[r.sign].tint }}>{VALENCE[r.sign].glyph}</span>
                    <span className="ds-ripple-partner" style={{ color: SC[r.partner] }}>{SI[r.partner]} {r.partner}</span>
                    <span className="ds-ripple-lbl" style={{ color: VALENCE[r.sign].tint }}>{VALENCE[r.sign].label}</span>
                    <span className="ds-ripple-mech" style={{ borderBottomStyle: basisBorder(r.tier === "verified" ? "research" : "physics") }}>{r.mech}</span>
                  </div>
                ))}
              </div>
              <button className="ds-ripple-clear" onClick={() => setActiveSense(null)}>← all senses</button>
            </>
          ) : (
            <>
              {worstN > 0 ? (
                <p className="ds-lesson">
                  <span style={{ color: SC[worst] }}>{SI[worst]} {worst}</span> is the weakest thread across your home —
                  failing in {worstN} {worstN === 1 ? "room" : "rooms"}. Lifting it ripples out to its coupled senses.
                </p>
              ) : (
                <p className="ds-lesson">no sense is failing across your home — the couplings are carrying comfort, not dragging it.</p>
              )}
              <div className="ds-couplings-hint">tap a sense to trace its ripple · solid = research, dashed = physics</div>
            </>
          )}
        </div>
      </div>

      {(cmp.loading || d) && (
        <div className="ds-hero">
          <div className="ds-section-label">
            what your changes did — {d ? `${d.room}${changedLabel ? ` · ${changedLabel}` : ""} · initial → now` : "initial → now"}
          </div>
          {cmp.loading && <div className="report-empty">rendering before / after…</div>}
          {d && (
            <>
              {/* one scrub surface: drag anywhere; a single spine runs the whole card */}
              <div className="ds-scrub" ref={scrubRef} onPointerDown={onScrubDown} onPointerMove={onScrubMove}>
                <BeforeAfterSlider before={d.before_image} after={d.after_image} height={300}
                  pos={pos} interactive={false}
                  beforeTag={d.room_before_overall != null ? d.room_before_overall.toFixed(2) : null}
                  afterTag={d.room_after_overall != null ? d.room_after_overall.toFixed(2) : null} />

                {/* mid band: the live readout rides the spine — petals + numbers move with it */}
                <div className="ds-scrub-mid">
                  <div className="ds-scrub-readout" style={{ left: `${railPos * 100}%` }}>
                    <svg width="80" height="80" viewBox="0 0 80 80">
                      <SenseSignature scores={interp} baseScores={baseScores} size={80} showGlyphs
                        title={d.room} activeSense={activeSense} onHoverSense={setActiveSense} />
                    </svg>
                    <div className="ds-scrub-nums">
                      <div className="ds-hero-now">
                        <span className="ds-delta-label">{d.room}</span>
                        <span className="ds-hero-now-val" style={{ color: scoreColor(roomNow) }}>
                          {roomNow != null ? roomNow.toFixed(2) : "—"}</span>
                      </div>
                      <div className="ds-hero-now">
                        <span className="ds-delta-label">whole home</span>
                        <span className="ds-hero-now-val" style={{ color: scoreColor(homeNow) }}>
                          {homeNow != null ? homeNow.toFixed(2) : "—"}</span>
                      </div>
                    </div>
                  </div>
                </div>

                {/* the two prompts that drove the renders — before left, after right of the spine */}
                {(d.before_prompt || d.after_prompt) && (
                  <div className="ds-scrub-prompts">
                    <div className="ds-hero-prompt" style={{ opacity: 0.25 + 0.75 * pos }}>
                      <div className="ds-hero-prompt-tag">before · the prompt</div>
                      <div className="rr-prompt"><PromptText prompt={d.before_prompt || ""} voiced={beforeVoiced} hoverSense={activeSense} /></div>
                    </div>
                    <div className="ds-hero-prompt" style={{ opacity: 0.25 + 0.75 * t }}>
                      <div className="ds-hero-prompt-tag">after · the prompt</div>
                      <div className="rr-prompt"><PromptText prompt={d.after_prompt || ""} voiced={afterVoiced} hoverSense={activeSense} /></div>
                    </div>
                  </div>
                )}

                {/* the spine: one vertical line through the whole card */}
                <div className="ds-scrub-spine" style={{ left: `${pos * 100}%` }} aria-hidden="true" />
              </div>
            </>
          )}
        </div>
      )}
    </section>
  );
}
