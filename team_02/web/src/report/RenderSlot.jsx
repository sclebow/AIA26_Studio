import { SC } from "../lib/constants.js";

/*
 * RenderSlot — the image cell of a room's score→prompt→image loop, with all four
 * progressive states. The Report owns the actual generation (api.renderRoom); this
 * is purely the view of one room's image status: idle (not requested yet),
 * loading (~16-40s), done (the render + re-render), error (+ retry).
 */
export default function RenderSlot({ img, roomName, onRender }) {
  const status = img?.status || "idle";

  if (status === "loading") {
    return (
      <div className="rr-render rr-render--loading">
        <div className="rr-shimmer" />
        <div className="rr-render-note">generating this space… ~20–40s</div>
      </div>
    );
  }

  if (status === "done" && img.url) {
    return (
      <div className="rr-render">
        <img src={img.url} alt={`render of ${roomName}`} className="rr-render-img" />
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
