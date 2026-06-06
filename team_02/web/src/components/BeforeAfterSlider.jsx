import { useRef, useState } from "react";

// A vertical wipe slider: AFTER is the base layer; BEFORE is overlaid and clipped
// to the left of the handle. Drag the handle — left of it = before, right = after.
export default function BeforeAfterSlider({ before, after, height = 170, beforeTag, afterTag }) {
  const [x, setX] = useState(50);
  const ref = useRef(null);

  const move = (clientX) => {
    const r = ref.current?.getBoundingClientRect();
    if (!r) return;
    setX(Math.max(0, Math.min(100, ((clientX - r.left) / r.width) * 100)));
  };

  return (
    <div
      ref={ref}
      className="ba-slider"
      style={{ position: "relative", width: "100%", height, borderRadius: 8, overflow: "hidden",
        border: "1px solid rgba(var(--fg-rgb),0.14)", cursor: "ew-resize", userSelect: "none", touchAction: "none" }}
      onPointerDown={(e) => { e.currentTarget.setPointerCapture(e.pointerId); move(e.clientX); }}
      onPointerMove={(e) => { if (e.buttons) move(e.clientX); }}
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
