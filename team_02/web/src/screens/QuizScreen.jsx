import { useEffect, useState } from "react";
import ChatThread from "../ui/ChatThread.jsx";
import TopBar from "../ui/TopBar.jsx";
import { STEPS, STEP_LABELS, SI } from "../lib/constants.js";

// ── Per-step input ────────────────────────────────────────────────────────
function QuizInput({ step, onSubmit }) {
  const [text, setText] = useState("");
  const [role, setRole] = useState(null);
  const [senses, setSenses] = useState([]);
  const [stage, setStage] = useState(null);
  const [living, setLiving] = useState(null);
  const [other, setOther] = useState("");

  // reset transient state when the step changes
  useEffect(() => {
    setText(""); setRole(null); setSenses([]); setStage(null); setLiving(null); setOther("");
  }, [step]);

  if (step === 0) {
    return (
      <div className="send-row">
        <input
          className="sensi-input" type="text" placeholder="your name" autoComplete="off"
          autoFocus value={text} onChange={(e) => setText(e.target.value)}
          onKeyDown={(e) => { if (e.key === "Enter" && text.trim()) onSubmit(text.trim()); }}
          style={{ flex: 1 }}
        />
        <button className="btn-send" onClick={() => text.trim() && onSubmit(text.trim())}>→</button>
      </div>
    );
  }

  if (step === 1) {
    const opts = [
      { role: "architect", label: "◎  i design spaces", text: "I design spaces -- architect" },
      { role: "client", label: "⌂  i live in them", text: "I live in spaces -- client" },
      { role: "student", label: "◈  here to learn", text: "I am here to learn -- student" },
    ];
    return (
      <div className="pill-group">
        {opts.map((o) => (
          <div
            key={o.role}
            className={"pill" + (role === o.role ? " selected" : "")}
            onClick={() => { setRole(o.role); setTimeout(() => onSubmit(o.text), 220); }}
          >
            {o.label}
          </div>
        ))}
      </div>
    );
  }

  if (step === 6) {
    // Personality / arousal axis (Eysenck): introvert prefers low stimulation,
    // extrovert high. Feeds persona_profile.personality → apply_personality scoring.
    const opts = [
      { val: "introvert", label: "🌙  a calm space to myself", text: "After a demanding day I recharge best in a calm space to myself." },
      { val: "mixed", label: "⚖  a balance of both", text: "After a demanding day I recharge with a balance of quiet and company." },
      { val: "extrovert", label: "☀  people and activity", text: "After a demanding day I recharge around people and activity." },
    ];
    return (
      <div className="pill-group">
        {opts.map((o) => (
          <div
            key={o.val}
            className={"pill" + (role === o.val ? " selected" : "")}
            onClick={() => { setRole(o.val); setTimeout(() => onSubmit(o.text), 220); }}
          >
            {o.label}
          </div>
        ))}
      </div>
    );
  }

  if (step === 2 || step === 5) {
    const placeholder = step === 2
      ? "could be anywhere — a room, a café, a corner of the world..."
      : "e.g. natural light, silence, warmth...";
    return (
      <div className="send-row" style={{ alignItems: "flex-end" }}>
        <textarea
          className="sensi-input" placeholder={placeholder} autoFocus
          value={text} onChange={(e) => setText(e.target.value)}
          onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); if (text.trim()) onSubmit(text.trim()); } }}
          style={{ flex: 1, height: 72 }}
        />
        <button className="btn-send" onClick={() => text.trim() && onSubmit(text.trim())}>→</button>
      </div>
    );
  }

  if (step === 3) {
    const toggle = (s) => setSenses((cur) => cur.includes(s) ? cur.filter((x) => x !== s) : [...cur, s]);
    const submit = () => {
      const t = senses.length
        ? "The senses that pull me out of comfort: " + senses.join(", ") + "."
        : "No specific sensory bothers mentioned.";
      onSubmit(t);
    };
    const order = ["thermal", "visual", "acoustic", "spatial", "olfactory", "tactile"];
    return (
      <>
        <div className="sense-grid">
          {order.map((s) => (
            <div
              key={s}
              className={"sense-pill" + (senses.includes(s) ? " selected" : "")}
              data-sense={s}
              onClick={() => toggle(s)}
            >
              <span className="si">{SI[s]}</span>
              <span className="sn">{s}</span>
            </div>
          ))}
        </div>
        <button
          className="btn-action"
          onClick={submit}
          style={{ opacity: senses.length ? 1 : 0.2, pointerEvents: senses.length ? "auto" : "none" }}
        >
          done →
        </button>
      </>
    );
  }

  if (step === 4) {
    const stages = ["20s-30s", "30s-40s", "40s+"];
    const livings = ["just me", "partner", "family", "flatmates", "other"];
    const submit = () => {
      if (!stage || !living) return;
      const liv = living === "other" && other.trim() ? other.trim() : living;
      onSubmit(`Life stage: ${stage}. Living situation: ${liv}.`);
    };
    return (
      <>
        <p className="label" style={{ marginBottom: 10, textAlign: "left" }}>life stage</p>
        <div className="pill-group">
          {stages.map((v) => (
            <div key={v} className={"pill" + (stage === v ? " selected" : "")} onClick={() => setStage(v)}>
              {v.replace("-", " – ").replace("+", " +")}
            </div>
          ))}
        </div>
        <p className="label" style={{ margin: "16px 0 10px", textAlign: "left" }}>who do you share your home with?</p>
        <div className="pill-group">
          {livings.map((v) => (
            <div key={v} className={"pill" + (living === v ? " selected" : "")} onClick={() => setLiving(v)}>
              {v === "other" ? "other..." : v}
            </div>
          ))}
        </div>
        {living === "other" && (
          <input
            className="sensi-input" type="text" placeholder="tell us a bit more..."
            value={other} onChange={(e) => setOther(e.target.value)} style={{ marginTop: 8 }}
          />
        )}
        <button className="btn-action" onClick={submit}>continue →</button>
      </>
    );
  }

  return null;
}

export default function QuizScreen({ messages, step, thinking, onSubmit }) {
  const idx = Math.min(step, STEPS.length - 1);
  const label = STEP_LABELS[STEPS[idx]] || STEPS[idx];

  return (
    <div className="screen active">
      <TopBar>
        <span className="top-bar-sep">|</span>
        <span className="top-bar-section">onboarding</span>
        <span className="top-bar-sep">|</span>
        <div className="top-bar-step">
          <div className="top-bar-step-dot" />
          <span className="top-bar-step-text">{`${idx + 1} of ${STEPS.length} · ${label}`}</span>
        </div>
      </TopBar>

      <ChatThread messages={messages} thinking={thinking} />

      <div className="input-area">
        {!thinking && <QuizInput step={step} onSubmit={onSubmit} />}
      </div>
    </div>
  );
}
