import { useEffect, useRef, useState } from "react";

interface WelcomePageProps {
  onEnter: () => void;
}

export default function WelcomePage({ onEnter }: WelcomePageProps) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const mouseRef = useRef({ x: -9999, y: -9999 });
  const personPosRef = useRef({ x: -9999, y: -9999 });
  const [visible, setVisible] = useState(false);
  const [personPos, setPersonPos] = useState({ x: -9999, y: -9999 });
  const [drawProgress, setDrawProgress] = useState(0);

  useEffect(() => {
    setTimeout(() => setVisible(true), 100);
  }, []);

  // Animated logo draw — loops forever
  useEffect(() => {
    let frame: number;
    let start: number | null = null;
    const DURATION = 2200;   // draw phase ms
    const HOLD = 600;        // hold at full opacity ms
    const FADE = 500;        // fade out ms
    const TOTAL = DURATION + HOLD + FADE;

    const tick = (ts: number) => {
      if (start === null) start = ts;
      const elapsed = (ts - start) % TOTAL;
      if (elapsed < DURATION) {
        setDrawProgress(elapsed / DURATION);
      } else if (elapsed < DURATION + HOLD) {
        setDrawProgress(1);
      } else {
        const fadeElapsed = elapsed - DURATION - HOLD;
        setDrawProgress(1 - fadeElapsed / FADE);
      }
      frame = requestAnimationFrame(tick);
    };
    frame = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(frame);
  }, []);

  // Smooth cursor follow
  useEffect(() => {
    let animId: number;
    let cx = -9999, cy = -9999;
    const tick = () => {
      cx += (mouseRef.current.x - cx) * 0.18;
      cy += (mouseRef.current.y - cy) * 0.18;
      personPosRef.current = { x: cx, y: cy };
      setPersonPos({ x: cx, y: cy });
      animId = requestAnimationFrame(tick);
    };
    tick();
    return () => cancelAnimationFrame(animId);
  }, []);

  // Particle canvas
  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    let animId: number;
    let W = window.innerWidth;
    let H = window.innerHeight;
    canvas.width = W;
    canvas.height = H;

    const NUM_PARTICLES = 180;
    const PERSON_RADIUS = 110;
    const CONNECT_DIST = 120;

    interface Particle {
      x: number; y: number;
      vx: number; vy: number;
      r: number; alpha: number;
    }
    interface CircuitParticle {
      x: number; y: number;
      tx: number; ty: number;
      progress: number; speed: number;
      alpha: number; trail: Array<{ x: number; y: number }>;
      done: boolean;
    }

    const particles: Particle[] = Array.from({ length: NUM_PARTICLES }, () => ({
      x: Math.random() * W, y: Math.random() * H,
      vx: (Math.random() - 0.5) * 0.07, vy: (Math.random() - 0.5) * 0.07,
      r: Math.random() * 2.2 + 0.8,
      alpha: Math.random() * 0.45 + 0.25,
    }));

    const circuits: CircuitParticle[] = [];

    const spawnIsovist = (ox: number, oy: number) => {
      const count = 16;
      for (let i = 0; i < count; i++) {
        const angle = (i / count) * Math.PI * 2;
        const length = 60 + Math.random() * 80;
        circuits.push({
          x: ox, y: oy,
          tx: ox + Math.cos(angle) * length,
          ty: oy + Math.sin(angle) * length,
          progress: 0,
          speed: 0.025 + Math.random() * 0.02,
          alpha: 0.6 + Math.random() * 0.4,
          trail: [], done: false,
        });
      }
    };

    const resize = () => {
      W = window.innerWidth; H = window.innerHeight;
      canvas.width = W; canvas.height = H;
    };
    window.addEventListener("resize", resize);

    const onMouseMove = (e: MouseEvent) => { mouseRef.current = { x: e.clientX, y: e.clientY }; };
    window.addEventListener("mousemove", onMouseMove);

    const onClick = (e: MouseEvent) => { spawnIsovist(e.clientX, e.clientY); };
    window.addEventListener("click", onClick);

    const draw = () => {
      ctx.clearRect(0, 0, W, H);
      const px = personPosRef.current.x;
      const py = personPosRef.current.y;

      particles.forEach((p) => {
        p.x += p.vx; p.y += p.vy;
        if (p.x < 0) p.x = W; if (p.x > W) p.x = 0;
        if (p.y < 0) p.y = H; if (p.y > H) p.y = 0;
        const dx = p.x - px; const dy = p.y - py;
        const dist = Math.sqrt(dx * dx + dy * dy);
        if (dist < PERSON_RADIUS && dist > 0) {
          const force = (PERSON_RADIUS - dist) / PERSON_RADIUS;
          p.vx += (dx / dist) * force * 0.4;
          p.vy += (dy / dist) * force * 0.4;
          p.vx *= 0.94; p.vy *= 0.94;
        }
        ctx.beginPath();
        ctx.arc(p.x, p.y, p.r, 0, Math.PI * 2);
        ctx.fillStyle = `rgba(109,40,217,${p.alpha})`;
        ctx.fill();
      });

      for (let i = 0; i < particles.length; i++) {
        for (let j = i + 1; j < particles.length; j++) {
          const dx = particles[i].x - particles[j].x;
          const dy = particles[i].y - particles[j].y;
          const d = Math.sqrt(dx * dx + dy * dy);
          if (d < CONNECT_DIST) {
            const a = (1 - d / CONNECT_DIST) * 0.22;
            ctx.beginPath();
            ctx.moveTo(particles[i].x, particles[i].y);
            ctx.lineTo(particles[j].x, particles[j].y);
            ctx.strokeStyle = `rgba(109,40,217,${a})`;
            ctx.lineWidth = 0.8;
            ctx.stroke();
          }
        }
      }

      for (let i = circuits.length - 1; i >= 0; i--) {
        const c = circuits[i];
        c.progress += c.speed;
        const ease = 1 - Math.pow(1 - c.progress, 3);
        const cx2 = c.x + (c.tx - c.x) * ease;
        const cy2 = c.y + (c.ty - c.y) * ease;
        const fadeAlpha = c.alpha * (1 - c.progress);

        // Ray line from origin
        ctx.beginPath();
        ctx.moveTo(c.x, c.y);
        ctx.lineTo(cx2, cy2);
        ctx.strokeStyle = `rgba(109,40,217,${fadeAlpha * 0.5})`;
        ctx.lineWidth = 0.6;
        ctx.stroke();

        // Dot at ray tip
        ctx.beginPath();
        ctx.arc(cx2, cy2, 2, 0, Math.PI * 2);
        ctx.fillStyle = `rgba(109,40,217,${fadeAlpha})`;
        ctx.fill();

        // Origin pulse ring
        if (c.progress < 0.4) {
          const ringR = c.progress * 40;
          const ringA = (1 - c.progress / 0.4) * 0.35;
          ctx.beginPath();
          ctx.arc(c.x, c.y, ringR, 0, Math.PI * 2);
          ctx.strokeStyle = `rgba(109,40,217,${ringA})`;
          ctx.lineWidth = 0.8;
          ctx.stroke();
        }

        if (c.progress >= 1) circuits.splice(i, 1);
      }

      animId = requestAnimationFrame(draw);
    };

    draw();
    return () => {
      cancelAnimationFrame(animId);
      window.removeEventListener("resize", resize);
      window.removeEventListener("mousemove", onMouseMove);
      window.removeEventListener("click", onClick);
    };
  }, []);

  const showPerson = personPos.x > 10;

  // Logo path data — the hexagonal spatial flow mark broken into segments
  // Each segment: [x1,y1,x2,y2] as fraction of 100x100 viewBox
  const logoSegments = [
    // Outer hex top
    "M50,8 L72,20",
    "M72,20 L72,44",
    // Right face
    "M72,44 L50,56",
    "M50,56 L28,44",
    // Left face top
    "M28,44 L28,20",
    "M28,20 L50,8",
    // Inner S-path
    "M50,32 L62,26",
    "M62,26 L62,38",
    "M62,38 L50,44",
    "M50,44 L38,50",
    "M38,50 L38,62",
    "M38,62 L50,56",
    // Bottom hex
    "M50,56 L72,68",
    "M72,68 L72,80",
    "M72,80 L50,92",
    "M50,92 L28,80",
    "M28,80 L28,68",
    "M28,68 L50,56",
  ];

  const totalSegments = logoSegments.length;

  return (
    <div style={{
      position: "fixed", inset: 0,
      background: "#f5f3ff",
      overflow: "hidden",
      fontFamily: "'Orbitron', 'Share Tech Mono', monospace",
      cursor: "none",
    }}>
      <link href="https://fonts.googleapis.com/css2?family=Orbitron:wght@400;700;900&family=Share+Tech+Mono&family=Inter:wght@300;400&display=swap" rel="stylesheet" />

      {/* Subtle grid background */}
      <div style={{
        position: "absolute", inset: 0,
        backgroundImage: `
          linear-gradient(rgba(109,40,217,0.04) 1px, transparent 1px),
          linear-gradient(90deg, rgba(109,40,217,0.04) 1px, transparent 1px)
        `,
        backgroundSize: "40px 40px",
        pointerEvents: "none",
      }} />

      {/* Soft radial purple glow top-left */}
      <div style={{
        position: "absolute", inset: 0,
        background: "radial-gradient(ellipse at 20% 40%, rgba(139,92,246,0.10) 0%, transparent 55%), radial-gradient(ellipse at 80% 80%, rgba(109,40,217,0.05) 0%, transparent 50%)",
        pointerEvents: "none",
      }} />

      {/* Canvas */}
      <canvas ref={canvasRef} style={{ position: "absolute", inset: 0, pointerEvents: "none" }} />

      {/* Right side — animated logo drawing */}
      <div style={{
        position: "absolute",
        right: "8%", top: "50%",
        transform: "translateY(-50%)",
        width: "420px", height: "420px",
        pointerEvents: "none",
        opacity: visible ? 1 : 0,
        transition: "opacity 1s ease 0.5s",
      }}>
        <svg
          viewBox="0 0 100 100"
          width="420" height="420"
          style={{ overflow: "visible" }}
        >
          {logoSegments.map((d, i) => {
            const segStart = i / totalSegments;
            const segEnd = (i + 1) / totalSegments;
            const localProgress = Math.max(0, Math.min(1,
              (drawProgress - segStart) / (segEnd - segStart)
            ));
            return (
              <path
                key={i}
                d={d}
                fill="none"
                stroke="rgba(109,40,217,0.55)"
                strokeWidth="1.2"
                strokeLinecap="round"
                strokeDasharray="100"
                strokeDashoffset={100 - localProgress * 100}
              />
            );
          })}
          {/* Glowing dot at draw head */}
          {drawProgress > 0 && drawProgress < 1 && (() => {
            const segIdx = Math.min(
              Math.floor(drawProgress * totalSegments),
              totalSegments - 1
            );
            return (
              <circle cx="50" cy="50" r="1.5" fill="rgba(139,92,246,0.8)" />
            );
          })()}
        </svg>
      </div>

      {/* Floor plan SVG — faint architectural lines, right background */}
      <svg style={{
        position: "absolute",
        right: "3%", top: "50%",
        transform: "translateY(-50%)",
        width: "580px", height: "440px",
        opacity: 0.04,
        pointerEvents: "none",
      }} viewBox="0 0 580 440">
        <rect x="20" y="20" width="540" height="400" fill="none" stroke="rgba(109,40,217,1)" strokeWidth="2"/>
        <line x1="200" y1="20" x2="200" y2="300" stroke="rgba(109,40,217,1)" strokeWidth="1.5"/>
        <line x1="200" y1="300" x2="560" y2="300" stroke="rgba(109,40,217,1)" strokeWidth="1.5"/>
        <line x1="380" y1="20" x2="380" y2="180" stroke="rgba(109,40,217,1)" strokeWidth="1.5"/>
        <line x1="380" y1="180" x2="560" y2="180" stroke="rgba(109,40,217,1)" strokeWidth="1.5"/>
        <line x1="20" y1="200" x2="200" y2="200" stroke="rgba(109,40,217,1)" strokeWidth="1.5"/>
        <line x1="200" y1="120" x2="200" y2="160" stroke="rgba(245,243,255,1)" strokeWidth="3"/>
        <path d="M200,120 Q240,120 240,160" fill="none" stroke="rgba(109,40,217,0.8)" strokeWidth="1"/>
        <line x1="310" y1="300" x2="350" y2="300" stroke="rgba(245,243,255,1)" strokeWidth="3"/>
        <path d="M310,300 Q310,260 350,260" fill="none" stroke="rgba(109,40,217,0.8)" strokeWidth="1"/>
        <rect x="40" y="40" width="60" height="40" fill="none" stroke="rgba(109,40,217,0.6)" strokeWidth="1"/>
        <rect x="220" y="40" width="100" height="60" fill="none" stroke="rgba(109,40,217,0.6)" strokeWidth="1"/>
        <rect x="400" y="40" width="80" height="50" fill="none" stroke="rgba(109,40,217,0.6)" strokeWidth="1"/>
        <rect x="220" y="200" width="120" height="80" fill="none" stroke="rgba(109,40,217,0.6)" strokeWidth="1"/>
        <rect x="400" y="200" width="60" height="80" fill="none" stroke="rgba(109,40,217,0.6)" strokeWidth="1"/>
        <rect x="40" y="230" width="80" height="50" fill="none" stroke="rgba(109,40,217,0.6)" strokeWidth="1"/>
        <rect x="80" y="320" width="100" height="80" fill="none" stroke="rgba(109,40,217,0.6)" strokeWidth="1"/>
        <rect x="260" y="320" width="80" height="60" fill="none" stroke="rgba(109,40,217,0.6)" strokeWidth="1"/>
        <rect x="420" y="320" width="100" height="80" fill="none" stroke="rgba(109,40,217,0.6)" strokeWidth="1"/>
        <circle cx="300" cy="220" r="5" fill="rgba(109,40,217,0.8)"/>
        <circle cx="300" cy="220" r="14" fill="none" stroke="rgba(109,40,217,0.4)" strokeWidth="1" strokeDasharray="3 3"/>
      </svg>

      {/* Right fade edge */}
      <div style={{
        position: "absolute", inset: 0,
        background: "radial-gradient(ellipse at 75% 50%, transparent 20%, rgba(245,243,255,0.65) 100%)",
        pointerEvents: "none",
      }} />

      {/* Crosshair cursor */}
      {showPerson && (
        <div style={{
          position: "fixed",
          left: personPos.x - 16, top: personPos.y - 16,
          pointerEvents: "none", zIndex: 9999,
          filter: "drop-shadow(0 0 6px rgba(109,40,217,0.4))",
          opacity: personPos.x > 10 ? 1 : 0,
          transition: "opacity 0.3s",
        }}>
          <svg width="32" height="32" viewBox="0 0 32 32" fill="none">
            {/* Outer circle */}
            <circle cx="16" cy="16" r="10" stroke="rgba(109,40,217,0.75)" strokeWidth="1"/>
            {/* Inner dot */}
            <circle cx="16" cy="16" r="2" fill="rgba(109,40,217,0.9)"/>
            {/* Cross lines — gap in center */}
            <line x1="16" y1="2" x2="16" y2="10" stroke="rgba(109,40,217,0.75)" strokeWidth="1" strokeLinecap="round"/>
            <line x1="16" y1="22" x2="16" y2="30" stroke="rgba(109,40,217,0.75)" strokeWidth="1" strokeLinecap="round"/>
            <line x1="2" y1="16" x2="10" y2="16" stroke="rgba(109,40,217,0.75)" strokeWidth="1" strokeLinecap="round"/>
            <line x1="22" y1="16" x2="30" y2="16" stroke="rgba(109,40,217,0.75)" strokeWidth="1" strokeLinecap="round"/>
            {/* Corner ticks — surveyor feel */}
            <line x1="24" y1="8" x2="26" y2="6" stroke="rgba(109,40,217,0.4)" strokeWidth="0.8" strokeLinecap="round"/>
            <line x1="8" y1="8" x2="6" y2="6" stroke="rgba(109,40,217,0.4)" strokeWidth="0.8" strokeLinecap="round"/>
            <line x1="24" y1="24" x2="26" y2="26" stroke="rgba(109,40,217,0.4)" strokeWidth="0.8" strokeLinecap="round"/>
            <line x1="8" y1="24" x2="6" y2="26" stroke="rgba(109,40,217,0.4)" strokeWidth="0.8" strokeLinecap="round"/>
          </svg>
        </div>
      )}

      {showPerson && (
        <div style={{
          position: "fixed", left: personPos.x + 20, top: personPos.y - 8,
          pointerEvents: "none", zIndex: 9999,
          fontSize: "9px", letterSpacing: "0.2em",
          color: "rgba(109,40,217,0.4)",
          fontFamily: "'Share Tech Mono', monospace",
          whiteSpace: "nowrap",
        }}>
          click to cast rays
        </div>
      )}

      {/* LEFT CONTENT */}
      <div style={{
        position: "absolute", left: 0, top: 0, bottom: 0, width: "520px",
        display: "flex", flexDirection: "column", justifyContent: "center",
        padding: "60px 64px",
        background: "linear-gradient(to right, rgba(245,243,255,0.97) 65%, transparent)",
        opacity: visible ? 1 : 0,
        transform: visible ? "translateX(0)" : "translateX(-30px)",
        transition: "opacity 1.2s ease, transform 1.2s ease",
      }}>

        {/* Logo + wordmark */}
        <div style={{ display: "flex", alignItems: "center", gap: "16px", marginBottom: "52px" }}>
          <img src="/logo.png" alt="logo" style={{ width: "52px", height: "52px", objectFit: "contain" }} />
          <div>
            <div style={{
              fontSize: "10px", letterSpacing: "0.35em",
              color: "rgba(109,40,217,0.45)", textTransform: "uppercase", marginBottom: "3px",
            }}>AIA Studio 2026</div>
            <div style={{
              fontSize: "15px", fontWeight: 700, letterSpacing: "0.18em", color: "#4c1d95",
            }}>SPATIAL FLOW</div>
          </div>
        </div>

        {/* Main title */}
        <h1 style={{
          fontSize: "clamp(40px, 5vw, 60px)", fontWeight: 900,
          lineHeight: 1.0, letterSpacing: "0.06em", color: "#3b0764",
          margin: "0 0 28px 0",
          opacity: visible ? 1 : 0,
          transition: "opacity 1.4s ease 0.6s",
        }}>WELCOME</h1>

        {/* Accent line */}
        <div style={{
          width: visible ? "72px" : "0px", height: "1.5px",
          background: "linear-gradient(to right, rgba(109,40,217,0.7), transparent)",
          marginBottom: "28px",
          transition: "width 1.2s ease 0.9s",
        }} />

        {/* Body text */}
        <div style={{
          fontFamily: "'Inter', sans-serif", fontSize: "13.5px",
          fontWeight: 300, lineHeight: 1.85, color: "rgba(76,29,149,0.72)",
          marginBottom: "44px",
          opacity: visible ? 1 : 0,
          transition: "opacity 1.4s ease 1.0s",
        }}>
          <p style={{ margin: "0 0 14px 0" }}>
            <span style={{ color: "rgba(109,40,217,1)", fontWeight: 500 }}>Spatial Flow Copilot</span>{" "}
            is an AI-powered spatial reasoning agent built for industrial design.
            It understands your floor plan, places equipment intelligently, and
            iterates until the layout meets real safety standards — OSHA, NFPA, and ISO.
          </p>
          <p style={{ margin: "0 0 14px 0" }}>
            Drop in a layout. Describe what you need. The agent reasons, places,
            checks clearances, analyzes visibility and circulation paths, and
            explains every decision with grounded spatial logic.
          </p>
          <p style={{ margin: 0, fontSize: "11px", color: "rgba(109,40,217,0.35)", letterSpacing: "0.12em" }}>
            IAAC · AIA Studio 2026 · GROUP 03
          </p>
        </div>

        {/* Enter button */}
        <button
          onClick={onEnter}
          style={{
            alignSelf: "flex-start", padding: "13px 44px",
            background: "transparent",
            border: "1px solid rgba(109,40,217,0.4)",
            color: "rgba(76,29,149,0.85)",
            fontSize: "11px", letterSpacing: "0.45em",
            textTransform: "uppercase", cursor: "none",
            fontFamily: "'Orbitron', monospace",
            opacity: visible ? 1 : 0,
            transition: "opacity 1.4s ease 1.3s, border-color 0.3s, background 0.3s, box-shadow 0.3s",
          }}
          onMouseEnter={e => {
            const b = e.currentTarget;
            b.style.background = "rgba(109,40,217,0.08)";
            b.style.borderColor = "rgba(109,40,217,0.8)";
            b.style.boxShadow = "0 0 24px rgba(109,40,217,0.15), inset 0 0 12px rgba(109,40,217,0.05)";
          }}
          onMouseLeave={e => {
            const b = e.currentTarget;
            b.style.background = "transparent";
            b.style.borderColor = "rgba(109,40,217,0.4)";
            b.style.boxShadow = "none";
          }}
        >
          ENTER
        </button>
      </div>

      {/* Version tag */}
      <div style={{
        position: "absolute", bottom: "24px", left: "64px",
        fontSize: "10px", letterSpacing: "0.2em",
        color: "rgba(109,40,217,0.2)",
        fontFamily: "'Share Tech Mono', monospace",
        opacity: visible ? 1 : 0,
        transition: "opacity 2s ease 1.6s",
      }}>
        v2.0 · SPATIAL ANALYSIS ENGINE
      </div>
    </div>
  );
}
