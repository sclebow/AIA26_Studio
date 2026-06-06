import { useEffect, useState } from "react";
import * as api from "../api/client.js";
import { SC, SI, SENSES } from "../lib/constants.js";
import { roomScores, layoutScore } from "../lib/turn.js";
import SenseGraph from "../components/SenseGraph.jsx";
import BeforeAfterSlider from "../components/BeforeAfterSlider.jsx";
import SenseDeltaPills from "../components/SenseDeltaPills.jsx";

/*
 * DwellingStory — the head of the Report: the ripple at the scale of the whole home.
 *   1. the aggregate as a status light (deliberately de-emphasised — "the weakest teacher").
 *   2. the sense-coupling diagram = how the senses talk to each other, with the
 *      weakest thread named.
 *   3. the hero ripple demo — if an edit was made, before/after + per-sense deltas
 *      show one change rippling across the senses. (No edit → no hero image; the
 *      featured room cards below carry the imagery.)
 */
export default function DwellingStory({ turn }) {
  const scoreRooms = roomScores(turn);
  const avg = layoutScore(scoreRooms);
  const ringClass = avg == null ? "" : avg >= 0.65 ? "score-pass" : avg >= 0.45 ? "score-warn" : "score-fail";

  // weakest sense across the home (most rooms failing < 0.5)
  const failCount = {}; SENSES.forEach((s) => { failCount[s] = 0; });
  scoreRooms.forEach((r) => SENSES.forEach((s) => { if ((r.comfortScores?.[s] ?? 1) < 0.5) failCount[s]++; }));
  const worst = SENSES.reduce((a, b) => (failCount[b] > failCount[a] ? b : a), SENSES[0]);
  const worstN = failCount[worst];

  // before/after hero — the WHOLE editing session: the most-changed room from its
  // INITIAL (on-disk) state to its FINAL (current) state. Captures every edit's
  // cumulative ripple, not just the last attribute. Hidden when nothing was edited.
  const [cmp, setCmp] = useState({ loading: true, data: null, error: null });
  useEffect(() => {
    let alive = true;
    api.compareInitial()
      .then((d) => { if (alive) setCmp(d.ok ? { loading: false, data: d, error: null } : { loading: false, data: null, error: d.error || "" }); })
      .catch((e) => { if (alive) setCmp({ loading: false, data: null, error: String(e.message || e) }); });
    return () => { alive = false; };
  }, []);
  const changedLabel = cmp.data?.changed?.length ? cmp.data.changed.join(", ") : "";

  return (
    <section className="ds">
      <div className="ds-head">
        <div className={"ds-ring " + ringClass}>{avg != null ? avg.toFixed(2) : "—"}</div>
        <div className="ds-head-copy">
          <h1 className="ds-title">your home, read by the senses</h1>
          <p className="ds-sub">the overall number isn't a grade to chase — it's the weakest teacher in the system.
            the real lesson lives in the edges: how a change to one sense ripples to another.</p>
        </div>
      </div>

      <div className="ds-couplings">
        <div className="ds-couplings-viz"><SenseGraph rooms={scoreRooms} size={220} /></div>
        <div className="ds-couplings-copy">
          <div className="ds-section-label">how your senses talk to each other</div>
          {worstN > 0 ? (
            <p className="ds-lesson">
              <span style={{ color: SC[worst] }}>{SI[worst]} {worst}</span> is the weakest thread across your home —
              failing in {worstN} {worstN === 1 ? "room" : "rooms"}. Lifting it ripples out to its coupled senses.
            </p>
          ) : (
            <p className="ds-lesson">no sense is failing across your home — the couplings are carrying comfort, not dragging it.</p>
          )}
          <div className="ds-couplings-hint">solid = research · dashed = physics · bigger node = more rooms fail it</div>
        </div>
      </div>

      {(cmp.loading || cmp.data) && (
        <div className="ds-hero">
          <div className="ds-section-label">
            the ripple — {cmp.data ? `${cmp.data.room}${changedLabel ? ` · ${changedLabel}` : ""} · initial → now` : "your edits, from start to now"}
          </div>
          {cmp.loading && <div className="report-empty">rendering before / after…</div>}
          {cmp.data && (
            <>
              <BeforeAfterSlider before={cmp.data.before_image} after={cmp.data.after_image} height={300} />
              <SenseDeltaPills deltas={cmp.data.deltas} />
            </>
          )}
        </div>
      )}
    </section>
  );
}
