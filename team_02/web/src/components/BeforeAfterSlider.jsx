import { useRef, useState } from "react";

// A vertical wipe slider: AFTER is the base layer; BEFORE is overlaid and clipped
// to the left of the handle. Drag the handle — left of it = before, right = after.
// Controlled mode: pass `pos` (0..1) + `onPos` so a parent can drive scores/prompt
// off the same handle; otherwise it owns its own position.
// `interactive={false}` disables its own pointer handling so a parent (e.g. a
// full-card scrub spine) can own the drag and this just renders the wipe from `pos`.
export default function BeforeAfterSlider({ before, after, height = 170, beforeTag, afterTag, pos, onPos, interactive = true }) {
  const controlled = typeof pos === "number";
  const [xInternal, setXInternal] = useState(50);
  const x = controlled ? Math.max(0, Math.min(100, pos * 100)) : xInternal;
  const ref = useRef(null);

  const move = (clientX) => {
    const r = ref.current?.getBoundingClientRect();
    if (!r) return;
    const nx = Math.max(0, Math.min(100, ((clientX - r.left) / r.width) * 100));
    if (controlled) onPos?.(nx / 100);
    else setXInternal(nx);
  };

  return (
    <div
      ref={ref}
      className="ba-slider"
      style={{ position: "relative", width: "100%", height, borderRadius: 8, overflow: "hidden",
        border: "1px solid rgba(var(--fg-rgb),0.14)", cursor: interactive ? "ew-resize" : "inherit", userSelect: "none", touchAction: "none" }}
      onPointerDown={interactive ? (e) => { e.currentTarget.setPointerCapture(e.pointerId); move(e.clientX); } : undefined}
      onPointerMove={interactive ? (e) => { if (e.buttons) move(e.clientX); } : undefined}
    >
      <img src={after} alt="after" draggable={false}
        style={{ position: "absolute", inset: 0, width: "100%", height: "100%", objectFit: "cover" }} />
      <img src={before} alt="before" draggable={false}
        style={{ position: "absolute", inset: 0, width: "100%", height: "100%", objectFit: "cover",
          clipPath: `inset(0 ${100 - x}% 0 0)` }} />
      <div style={{ position: "absolute", top: 0, bottom: 0, left: `${x}%`, width: 2,
        background: "rgba(255,255,255,0.85)", boxShadow: "0 0 4px rgba(0,0,0,0.6)", transform: "translateX(-1px)" }} />
      <span style={{ position: "absolute", left: 6, bottom: 4, fontSize: 10, letterSpacing: "0.08em",
        color: "#fff", opacity: 0.85, textShadow: "0 1px 2px #000" }}>
        BEFORE{beforeTag != null && <b style={{ marginLeft: 5, fontWeight: 600 }}>{beforeTag}</b>}
      </span>
      <span style={{ position: "absolute", right: 6, bottom: 4, fontSize: 10, letterSpacing: "0.08em",
        color: "#fff", opacity: 0.85, textShadow: "0 1px 2px #000" }}>
        {afterTag != null && <b style={{ marginRight: 5, fontWeight: 600 }}>{afterTag}</b>}AFTER
      </span>
    </div>
  );
}
