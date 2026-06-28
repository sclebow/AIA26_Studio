import { useEffect, useState } from "react";
import { SC } from "../lib/constants.js";

/*
 * RenderSlot — the image cell of a room's score→prompt→image loop, with all four
 * progressive states. The Report owns the actual generation (api.renderRoom); this is
 * purely the view of one room's image status: idle (not requested yet), loading
 * (~10-30s), done (the render + re-render), error (+ retry).
 *
 * The loading state is a PROGRESSIVE REVEAL (flow-audit §6.5): the scores + prompt are
 * already on screen, and here a poetic status cycles over the shimmer so the wait reads
 * as "working, developing your space" rather than a stall — then the image fades in.
 */
const RENDER_PHRASES = [
  "composing the light…",
  "warming the materials…",
  "settling the quiet…",
  "letting the room breathe…",
  "developing the frame…",
];

export default function RenderSlot({ img, roomName, onRender }) {
  const status = img?.status || "idle";
  const [phase, setPhase] = useState(0);

  useEffect(() => {
    if (status !== "loading") return;
    setPhase(0);
    const id = setInterval(() => setPhase((i) => (i + 1) % RENDER_PHRASES.length), 2600);
    return () => clearInterval(id);
  }, [status]);

  if (status === "loading") {
    return (
      <div className="rr-render rr-render--loading">
        <div className="rr-shimmer" />
        <div className="rr-render-note rr-render-note--cycle" key={phase}>
          {RENDER_PHRASES[phase]} <span className="rr-render-eta">~10–30s</span>
        </div>
      </div>
    );
  }

  if (status === "done" && img.url) {
    return (
      <div className="rr-render">
        <img src={img.url} alt={`render of ${roomName}`} className="rr-render-img rr-render-img--in" />
        <button className="rr-render-again" onClick={() => onRender(true)}>↻ re-render</button>
      </div>
    );
  }

  if (status === "error") {
    return (
      <div className="rr-render rr-render--error">
        <div className="rr-render-note" style={{ color: SC.thermal }}>{img.error || "render failed"}</div>
        <button className="rr-render-again" onClick={() => onRender(true)}>↻ try again</button>
      </div>
    );
  }

  // idle
  return (
    <button className="rr-render-btn" onClick={() => onRender(false)}>✦ render this space</button>
  );
}
