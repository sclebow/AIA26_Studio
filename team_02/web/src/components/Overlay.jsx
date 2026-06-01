import { useEffect, useState } from "react";
import SensiAvatar from "./SensiAvatar.jsx";
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
      <SensiAvatar size={52} className="" strokeWidth={0.9} centerR={1.4} centerOpacity={0.85} />
      <p className="overlay-msg">{phrases[idx] || "starting sensi..."}</p>
    </div>
  );
}
