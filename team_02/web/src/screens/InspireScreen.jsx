import { useRef, useState } from "react";
import SensiAvatar from "../components/SensiAvatar.jsx";
import * as api from "../api/client.js";
import { SC, SI } from "../lib/constants.js";

const ORDER = ["thermal", "visual", "acoustic", "spatial", "olfactory", "tactile"];
const MAX_PICKS = 3; // contract: each round, pick a minimum of 1 and a maximum of 3

function hexToRgb(hex) {
  return `${parseInt(hex.slice(1, 3), 16)},${parseInt(hex.slice(3, 5), 16)},${parseInt(hex.slice(5, 7), 16)}`;
}
function makeGradient(senses) {
  if (!senses || senses.length === 0) return "rgba(240,237,232,.10)";
  const c1 = SC[senses[0]] || "#E8836A";
  if (senses.length === 1) {
    const rgb = hexToRgb(c1);
    return `linear-gradient(270deg, ${c1}, rgba(${rgb},.28), rgba(${rgb},.55), ${c1})`;
  }
  const c2 = SC[senses[1]] || c1;
  return `linear-gradient(270deg, ${c1}, rgba(${hexToRgb(c2)},.70), ${c2}, rgba(${hexToRgb(c1)},.70), ${c1})`;
}

// Full inspire pipeline (3b): mirrors submitInspireQuestion / renderInspireGrid /
// advanceInspireRound / buildMoodboardDisplay / finaliseMoodboard.
export default function InspireScreen({ question, setOverlay, onPersonaReady }) {
  const [stage, setStage] = useState("question");
  const [text, setText] = useState("");
  const [b64s, setB64s] = useState([]);
  const [round, setRound] = useState(1);
  const [degraded, setDegraded] = useState(false);
  const [refineText, setRefineText] = useState("");   // optional "say more" between rounds

  const urlsRef = useRef([[], [], []]);
  const sensesRef = useRef([[], [], []]);
  const [selected, setSelected] = useState([{}, {}, {}]);
  const [, force] = useState(0);
  const fileRef = useRef(null);

  const curUrls = urlsRef.current[round - 1] || [];
  const curSenses = sensesRef.current[round - 1] || [];
  const curSel = selected[round - 1] || {};
  const selCount = Object.keys(curSel).length;
  const atMax = selCount >= MAX_PICKS;

  const renderRound = (data) => {
    const r = data.round;
    urlsRef.current[r - 1] = data.urls || [];
    sensesRef.current[r - 1] = data.senses || [];
    setSelected((prev) => { const n = [...prev]; n[r - 1] = {}; return n; });
    setDegraded(!!data.degraded);
    setRefineText("");
    setRound(r);
    setStage("grid");
    setOverlay(null);
  };

  // Re-run the current round (used by the "retry" affordance when the image
  // service returned a degraded/fallback set).
  const retryRound = () => {
    setOverlay("finding more images...");
    const cbs = { onProgress: (m) => setOverlay(m), onResult: renderRound };
    const req = round === 1
      ? api.prepareInspire(text, b64s, 1, cbs)
      : api.refineInspire("", round, cbs);
    req.catch(() => setOverlay(null));
  };

  // Round 1 needs no typed description — the board is seeded from the quiz. Any text the
  // user adds is optional flavour on top.
  const submitQuestion = () => {
    setRound(1);
    setOverlay("reading your aesthetic...");
    api.prepareInspire(text.trim(), b64s, 1, {
      onProgress: (m) => setOverlay(m),
      onResult: (data) => {
        if (!data.urls || data.urls.length === 0) { buildMoodboard(); return; }
        renderRound(data);
      },
    }).catch(() => setOverlay(null));
  };

  // What the user leaned toward this round — the senses of the images they picked — so the
  // next round evolves toward them (alongside any optional "say more" text).
  const pickedSenseLean = () => {
    const tally = {};
    Object.keys(curSel).forEach((i) => {
      (curSenses[parseInt(i)] || []).forEach((s) => { tally[s] = (tally[s] || 0) + 1; });
    });
    const top = Object.entries(tally).sort((a, b) => b[1] - a[1]).slice(0, 2).map(([s]) => s);
    return top.length ? `lean toward ${top.join(" and ")} spaces` : "";
  };

  const toggleCell = (i) => {
    setSelected((prev) => {
      const n = prev.map((o) => ({ ...o }));
      const cell = n[round - 1];
      if (cell[i]) {
        delete cell[i];                                   // always allow deselect
      } else if (Object.keys(cell).length < MAX_PICKS) {
        cell[i] = true;                                   // cap selections at MAX_PICKS
      }
      return n;
    });
  };

  const advance = () => {
    const picks = Object.keys(curSel).map((i) => curUrls[parseInt(i)]).filter(Boolean);
    api.saveInspirePicks(round, picks).catch(() => {});
    if (round < 3) {
      // Evolve the next round from what they picked + any optional "say more" text.
      const refine = [pickedSenseLean(), refineText.trim()].filter(Boolean).join(". ");
      setOverlay("finding more images...");
      api.refineInspire(refine, round + 1, {
        onProgress: (m) => setOverlay(m),
        onResult: renderRound,
      }).catch(() => setOverlay(null));
    } else {
      buildMoodboard();
    }
  };

  const moodboardUrls = () => {
    const all = [], seen = new Set();
    for (let r = 0; r < 3; r++) {
      const sel = selected[r] || {};
      const urls = urlsRef.current[r] || [];
      Object.keys(sel).forEach((i) => {
        const u = urls[parseInt(i)];
        if (u && !seen.has(u)) { seen.add(u); all.push(u); }
      });
    }
    return all;
  };

  const buildMoodboard = () => { setStage("moodboard"); force((x) => x + 1); };

  const keepPicking = () => {
    setRound(3);
    setOverlay("finding more images...");
    api.refineInspire("", 3, { onProgress: (m) => setOverlay(m), onResult: renderRound }).catch(() => setOverlay(null));
  };

  const finalise = () => {
    const counts = {};
    for (let r = 0; r < 3; r++) {
      const sel = selected[r] || {};
      const senses = sensesRef.current[r] || [];
      Object.keys(sel).forEach((i) => {
        (senses[parseInt(i)] || []).forEach((s) => { counts[s] = (counts[s] || 0) + 1; });
      });
    }
    setOverlay("building your comfort profile...");
    api.buildMoodboard(counts)
      .then((data) => { setOverlay(null); onPersonaReady(data); })
      .catch(() => setOverlay(null));
  };

  const onPickFiles = (e) => {
    const files = Array.from(e.target.files || []).slice(0, 5);
    Promise.all(files.map((f) => new Promise((res) => {
      const reader = new FileReader();
      reader.onload = () => res(String(reader.result).split(",")[1] || "");
      reader.readAsDataURL(f);
    }))).then((arr) => setB64s(arr.filter(Boolean)));
  };

  const TopBar = (
    <div className="top-bar">
      <div className="top-bar-pill">
        <SensiAvatar size={26} className="" />
        <span className="top-bar-label">sensi</span>
        <span className="top-bar-sep">|</span>
        <span className="top-bar-section">onboarding</span>
        <span className="top-bar-sep">|</span>
        <div className="top-bar-step">
          <div className="top-bar-step-dot" />
          <span className="top-bar-step-text">
            {stage === "grid" ? `aesthetic · round ${round} of 3` : "aesthetic profile"}
          </span>
        </div>
      </div>
    </div>
  );

  return (
    <div className="screen active">
      {TopBar}

      {stage === "question" && (
        <div style={{ flex: 1, display: "flex", flexDirection: "column", overflow: "hidden" }}>
          <div className="thread" style={{ flex: 1 }}>
            <div className="thread-inner" style={{ paddingTop: 24 }}>
              <div className="bubble-wrap">
                <SensiAvatar size={28} />
                <p className="bubble-s" style={{ marginBottom: 0 }}>{question}</p>
              </div>
              <p className="label" style={{ marginTop: 8 }}>
                I'll start from your quiz — add anything you'd like, or just go.
              </p>
            </div>
          </div>
          <div className="input-area" style={{ maxWidth: 560, margin: "0 auto", width: "100%" }}>
            <textarea className="sensi-input" placeholder="anything to add about your ideal space? (optional)"
              value={text} onChange={(e) => setText(e.target.value)} style={{ height: 90 }} />
            <div className="upload-row">
              <button className="btn-upload" onClick={() => fileRef.current && fileRef.current.click()}>+ add reference images</button>
              <span className="upload-names">{b64s.length ? `${b64s.length} image${b64s.length > 1 ? "s" : ""} selected` : "optional · up to 5"}</span>
              <input ref={fileRef} type="file" accept="image/*" multiple style={{ display: "none" }} onChange={onPickFiles} />
            </div>
            <div className="upload-preview">
              {b64s.map((b, i) => <img key={i} src={`data:image/jpeg;base64,${b}`} alt="" />)}
            </div>
            <button className="btn-action" onClick={submitQuestion}>show me my moodboard →</button>
          </div>
        </div>
      )}

      {stage === "grid" && (
        <div style={{ flex: 1, display: "flex", flexDirection: "column", overflow: "hidden" }}>
          <div className="thread" style={{ flex: 1 }}>
            <div className="thread-inner" style={{ paddingTop: 16 }}>
              <div className="bubble-wrap" style={{ marginBottom: 8 }}>
                <SensiAvatar size={28} />
                <p className="bubble-s" style={{ marginBottom: 0 }}>which of these feel like you?</p>
              </div>
              <p className="label" style={{ marginTop: 4 }}>click to select · pick 1–3 that resonate</p>
              {degraded && (
                <p className="label" style={{ marginTop: 4, color: "var(--sense-thermal, #E8836A)", opacity: 0.85 }}>
                  couldn't reach the image service for a full set (it may be rate-limited) — showing fallbacks ·{" "}
                  <button
                    onClick={retryRound}
                    style={{ background: "none", border: "none", color: "inherit", textDecoration: "underline", cursor: "pointer", padding: 0, font: "inherit" }}>
                    retry
                  </button>
                </p>
              )}
              <div className="sense-legend">
                {ORDER.map((s) => (
                  <span className="sl-item" key={s}>
                    <span className="sl-dot" style={{ background: SC[s] }} />
                    <span className="sl-sym">{SI[s]}</span>
                    <span className="sl-name">{s}</span>
                  </span>
                ))}
              </div>
              <div className="img-grid">
                {curUrls.map((url, i) => {
                  const cs = curSenses[i] || [];
                  const sel = !!curSel[i];
                  return (
                    <div key={i}
                      className={"img-cell" + (sel ? " selected sg-anim" : "")}
                      style={sel
                        ? { background: makeGradient(cs) }
                        : (atMax ? { opacity: 0.4, cursor: "default" } : undefined)}
                      onClick={() => toggleCell(i)}>
                      <img src={url} loading="lazy" alt="" />
                      <div className="sense-badge">
                        {cs.map((s, k) => <span className="sense-dot" key={k} style={{ background: SC[s] || "#888" }} />)}
                        <span className="sense-sym">{cs.map((s) => SI[s] || "").join(" ")}</span>
                      </div>
                    </div>
                  );
                })}
              </div>
              <p className="label" style={{ marginTop: 8 }}>
                {selCount}/{MAX_PICKS} selected{atMax ? " · max reached" : (selCount === 0 ? " · pick at least 1" : "")}
              </p>
            </div>
          </div>
          <div className="input-area" style={{ maxWidth: 560, margin: "0 auto", width: "100%" }}>
            {round < 3 && (
              <input className="sensi-input" value={refineText} onChange={(e) => setRefineText(e.target.value)}
                placeholder="say more about what you want next (optional)…"
                style={{ height: 40, marginBottom: 8 }} />
            )}
            <button className="btn-action" onClick={advance} disabled={selCount === 0}>continue →</button>
          </div>
        </div>
      )}

      {stage === "moodboard" && (
        <div style={{ flex: 1, display: "flex", flexDirection: "column", overflow: "hidden" }}>
          <div className="thread" style={{ flex: 1 }}>
            <div className="thread-inner" style={{ paddingTop: 16 }}>
              <div className="bubble-wrap" style={{ marginBottom: 10 }}>
                <SensiAvatar size={28} />
                <p className="bubble-s" style={{ marginBottom: 0 }}>here's your moodboard.</p>
              </div>
              <div className="img-grid" style={{ marginTop: 10 }}>
                {moodboardUrls().slice(0, 6).map((url, i) => (
                  <div className="img-cell selected" key={i}><img src={url} loading="lazy" alt="" /></div>
                ))}
              </div>
            </div>
          </div>
          <div className="input-area" style={{ maxWidth: 560, margin: "0 auto", width: "100%" }}>
            <div className="btn-row">
              <button className="btn-action btn-ghost" onClick={keepPicking}>keep picking</button>
              <button className="btn-action" onClick={finalise}>this is it →</button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
