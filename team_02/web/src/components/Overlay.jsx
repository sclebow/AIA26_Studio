import { useEffect, useState } from "react";
import { OVERLAY_PHRASES } from "../lib/constants.js";

// Fullscreen loading overlay. `message` is the seed string; if it maps to a
// phrase list, the text rotates every 2.6s (mirrors showOverlay in index.html).
export default function Overlay({ message }) {
  const visible = !!message;
  const phrases = (message && OVERLAY_PHRASES[message]) || (message ? [message] : []);
  const [idx, setIdx] = useState(0);

  useEffect(() => {
    setIdx(0);
    if (phrases.length <= 1) return;
    const t = setInterval(() => setIdx((i) => (i + 1) % phrases.length), 2600);
    return () => clearInterval(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [message]);

  return (
    <div id="overlay" className={visible ? "visible" : ""}>
      <svg width="52" height="52" viewBox="0 0 32 32" fill="none">
        <circle cx="16" cy="16" r="14.5" stroke="#E8836A" strokeWidth=".9" style={{ animation: "srg0 3s ease-in-out infinite" }} />
        <circle cx="16" cy="16" r="12" stroke="#D4B96A" strokeWidth=".9" style={{ animation: "srg1 3s ease-in-out infinite", animationDelay: ".5s" }} />
        <circle cx="16" cy="16" r="9.5" stroke="#9B8FD4" strokeWidth=".9" style={{ animation: "srg2 3s ease-in-out infinite", animationDelay: "1s" }} />
        <circle cx="16" cy="16" r="7" stroke="#6AB8C8" strokeWidth=".9" style={{ animation: "srg3 3s ease-in-out infinite", animationDelay: "1.5s" }} />
        <circle cx="16" cy="16" r="4.5" stroke="#8BB88A" strokeWidth=".9" style={{ animation: "srg4 3s ease-in-out infinite", animationDelay: "2s" }} />
        <circle cx="16" cy="16" r="2" stroke="#C4A882" strokeWidth=".9" style={{ animation: "srg5 3s ease-in-out infinite", animationDelay: "2.5s" }} />
        <circle cx="16" cy="16" r="1.4" fill="#F0EDE8" opacity=".85" />
      </svg>
      <p className="overlay-msg">{phrases[idx] || "starting sensi..."}</p>
    </div>
  );
}
