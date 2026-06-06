import { useEffect, useState } from "react";
import * as api from "../api/client.js";
import { SC, SI, SENSES, scoreColor } from "../lib/constants.js";
import { STATUS } from "../lib/senses.js";
import { SENSE_SENSE, basisBorder } from "../lib/senseModel.js";
import { VALENCE } from "../lib/relationships.js";
import { useSelection } from "../lib/selection.jsx";
import { roomScores, layoutScore } from "../lib/turn.js";
import SenseGraph from "../components/SenseGraph.jsx";
import BeforeAfterSlider from "../components/BeforeAfterSlider.jsx";
import SenseDeltaPills from "../components/SenseDeltaPills.jsx";

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

function Delta({ from, to, label }) {
  if (from == null || to == null) return null;
  const d = to - from;
  const col = Math.abs(d) < 0.005 ? "rgba(var(--fg-rgb),0.5)" : d > 0 ? STATUS.pass : STATUS.fail;
  return (
    <span className="ds-delta">
      <span className="ds-delta-label">{label}</span>
      <span style={{ color: scoreColor(from) }}>{from.toFixed(2)}</span>
      <span className="ds-delta-arrow">→</span>
      <span style={{ color: scoreColor(to) }}>{to.toFixed(2)}</span>
      <span className="ds-delta-amt" style={{ color: col }}>{d > 0 ? "+" : ""}{d.toFixed(2)}</span>
    </span>
  );
}

/*
 * DwellingStory — the head of The Vision: the whole home at a glance.
 *   1. a data-driven headline + the aggregate as a quiet status light.
 *   2. the sense-coupling diagram = how the senses talk to each other — INTERACTIVE:
 *      tap a sense to trace its ripple (what it helps / harms / trades with). Default
 *      names the weakest thread.
 *   3. "what your changes did" — the most-changed room, initial → now, with the
 *      before/after renders, overall score deltas, and per-sense deltas.
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

  // before/after — the most-changed room, initial (on-disk) → now (current).
  const [cmp, setCmp] = useState({ loading: true, data: null, error: null });
  useEffect(() => {
    let alive = true;
    api.compareInitial()
      .then((d) => { if (alive) setCmp(d.ok ? { loading: false, data: d, error: null } : { loading: false, data: null, error: d.error || "" }); })
      .catch((e) => { if (alive) setCmp({ loading: false, data: null, error: String(e.message || e) }); });
    return () => { alive = false; };
  }, []);
  const d = cmp.data;
  const changedLabel = d?.changed?.length ? d.changed.join(", ") : "";

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
              <BeforeAfterSlider before={d.before_image} after={d.after_image} height={300}
                beforeTag={d.room_before_overall != null ? d.room_before_overall.toFixed(2) : null}
                afterTag={d.room_after_overall != null ? d.room_after_overall.toFixed(2) : null} />
              <div className="ds-hero-scores">
                <Delta from={d.room_before_overall} to={d.room_after_overall} label={d.room} />
                <Delta from={d.dwelling_before} to={d.dwelling_after} label="whole home" />
              </div>
              <SenseDeltaPills deltas={d.deltas} />
            </>
          )}
        </div>
      )}
    </section>
  );
}
