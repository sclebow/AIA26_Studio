import SensiAvatar from "./SensiAvatar.jsx";

// The inline "Sensi is thinking" bubble with pulsing dots.
export default function Thinking() {
  return (
    <div className="bubble-wrap">
      <SensiAvatar size={28} />
      <div className="bubble-s" style={{ marginBottom: 0, padding: "12px 16px" }}>
        <span className="thinking-dots"><span></span><span></span><span></span></span>
      </div>
    </div>
  );
}
