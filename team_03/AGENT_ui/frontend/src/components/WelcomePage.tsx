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

  useEffect(() => {
    setTimeout(() => setVisible(true), 100);
  }, []);

  useEffect(() => {
    let animId: number;
    let cx = -9999, cy = -9999;
    const tick = () => {
      cx += (mouseRef.current.x - cx) * 0.05;
      cy += (mouseRef.current.y - cy) * 0.05;
      personPosRef.current = { x: cx, y: cy };
      setPersonPos({ x: cx, y: cy });
      animId = requestAnimationFrame(tick);
    };
    tick();
    return () => cancelAnimationFrame(animId);
  }, []);

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

    const NUM_PARTICLES = 220;
    const PERSON_RADIUS = 110;
    const CONNECT_DIST = 130;

    interface Particle {
      x: number; y: number;
      vx: number; vy: number;
      r: number; alpha: number;
    }

    interface CircuitParticle {
      x: number; y: number;
      tx: number; ty: number;
      progress: number;
      speed: number;
      alpha: number;
      trail: Array<{x:number,y:number}>;
      done: boolean;
    }

    const particles: Particle[] = Array.from({ length: NUM_PARTICLES }, () => ({
      x: Math.random() * W,
      y: Math.random() * H,
      vx: (Math.random() - 0.5) * 0.08,
      vy: (Math.random() - 0.5) * 0.08,
      r: Math.random() * 2 + 0.5,
      alpha: Math.random() * 0.45 + 0.2,
    }));

    const circuits: CircuitParticle[] = [];

    const spawnCircuits = (ox: number, oy: number) => {
      const count = 8 + Math.floor(Math.random() * 6);
      for (let i = 0; i < count; i++) {
        const target = particles[Math.floor(Math.random() * particles.length)];
        circuits.push({
          x: ox, y: oy,
          tx: target.x, ty: target.y,
          progress: 0,
          speed: 0.012 + Math.random() * 0.018,
          alpha: 0.8 + Math.random() * 0.2,
          trail: [],
          done: false,
        });
      }
    };

    const resize = () => {
      W = window.innerWidth; H = window.innerHeight;
      canvas.width = W; canvas.height = H;
    };
    window.addEventListener("resize", resize);

    const onMouseMove = (e: MouseEvent) => {
      mouseRef.current = { x: e.clientX, y: e.clientY };
    };
    window.addEventListener("mousemove", onMouseMove);

    const onClick = (e: MouseEvent) => {
      spawnCircuits(e.clientX, e.clientY);
    };
    window.addEventListener("click", onClick);

    const draw = () => {
      ctx.clearRect(0, 0, W, H);
      const px = personPosRef.current.x;
      const py = personPosRef.current.y;

      // Particles
      particles.forEach((p) => {
        p.x += p.vx;
        p.y += p.vy;
        if (p.x < 0) p.x = W;
        if (p.x > W) p.x = 0;
        if (p.y < 0) p.y = H;
        if (p.y > H) p.y = 0;

        const dx = p.x - px;
        const dy = p.y - py;
        const dist = Math.sqrt(dx * dx + dy * dy);
        if (dist < PERSON_RADIUS && dist > 0) {
          const force = (PERSON_RADIUS - dist) / PERSON_RADIUS;
          p.vx += (dx / dist) * force * 0.4;
          p.vy += (dy / dist) * force * 0.4;
          p.vx *= 0.94;
          p.vy *= 0.94;
        }

        ctx.beginPath();
        ctx.arc(p.x, p.y, p.r, 0, Math.PI * 2);
        ctx.fillStyle = `rgba(167,139,250,${p.alpha})`;
        ctx.fill();
      });

      // Connections
      for (let i = 0; i < particles.length; i++) {
        for (let j = i + 1; j < particles.length; j++) {
          const dx = particles[i].x - particles[j].x;
          const dy = particles[i].y - particles[j].y;
          const d = Math.sqrt(dx * dx + dy * dy);
          if (d < CONNECT_DIST) {
            const a = (1 - d / CONNECT_DIST) * 0.13;
            ctx.beginPath();
            ctx.moveTo(particles[i].x, particles[i].y);
            ctx.lineTo(particles[j].x, particles[j].y);
            ctx.strokeStyle = `rgba(139,92,246,${a})`;
            ctx.lineWidth = 0.5;
            ctx.stroke();
          }
        }
      }

      // Circuit particles
      for (let i = circuits.length - 1; i >= 0; i--) {
        const c = circuits[i];
        c.progress += c.speed;

        const cx2 = c.x + (c.tx - c.x) * c.progress;
        const cy2 = c.y + (c.ty - c.y) * c.progress;

        c.trail.push({ x: cx2, y: cy2 });
        if (c.trail.length > 18) c.trail.shift();

        // Draw trail
        for (let t = 0; t < c.trail.length - 1; t++) {
          const ta = (t / c.trail.length) * c.alpha * 0.7;
          ctx.beginPath();
          ctx.moveTo(c.trail[t].x, c.trail[t].y);
          ctx.lineTo(c.trail[t + 1].x, c.trail[t + 1].y);
          ctx.strokeStyle = `rgba(216,180,254,${ta})`;
          ctx.lineWidth = 1.2;
          ctx.stroke();
        }

        // Draw head dot
        ctx.beginPath();
        ctx.arc(cx2, cy2, 2.2, 0, Math.PI * 2);
        ctx.fillStyle = `rgba(245,208,254,${c.alpha})`;
        ctx.shadowColor = "rgba(216,180,254,0.9)";
        ctx.shadowBlur = 8;
        ctx.fill();
        ctx.shadowBlur = 0;

        if (c.progress >= 1) {
          // Flash at target
          ctx.beginPath();
          ctx.arc(c.tx, c.ty, 4, 0, Math.PI * 2);
          ctx.fillStyle = "rgba(245,208,254,0.6)";
          ctx.shadowColor = "rgba(216,180,254,1)";
          ctx.shadowBlur = 14;
          ctx.fill();
          ctx.shadowBlur = 0;
          circuits.splice(i, 1);
        }
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

  return (
    <div style={{
      position: "fixed", inset: 0,
      background: "#0a0612",
      overflow: "hidden",
      fontFamily: "'Orbitron', 'Share Tech Mono', monospace",
      cursor: "none",
    }}>
      <link href="https://fonts.googleapis.com/css2?family=Orbitron:wght@400;700;900&family=Share+Tech+Mono&family=Inter:wght@300;400&display=swap" rel="stylesheet" />

      {/* Background image */}
      <div style={{
        position: "absolute", inset: 0,
        backgroundImage: "url(/bg.png)",
        backgroundSize: "cover",
        backgroundPosition: "center",
        opacity: 0.45,
        filter: "hue-rotate(200deg) saturate(0.8)",
      }} />

      {/* Floor plan watermark — right side */}
      <div style={{
        position: "absolute",
        right: "4%", top: "50%",
        transform: "translateY(-50%)",
        width: "520px", height: "520px",
        backgroundImage: "url(/logo.png)",
        backgroundSize: "contain",
        backgroundRepeat: "no-repeat",
        backgroundPosition: "center",
        opacity: 0.04,
        filter: "hue-rotate(200deg) saturate(0.3) brightness(2)",
        pointerEvents: "none",
      }} />

      {/* Inline floor plan SVG — faint architectural lines */}
      <svg style={{
        position: "absolute",
        right: "3%", top: "50%",
        transform: "translateY(-50%)",
        width: "580px", height: "440px",
        opacity: 0.055,
        pointerEvents: "none",
      }} viewBox="0 0 580 440">
        {/* Outer walls */}
        <rect x="20" y="20" width="540" height="400" fill="none" stroke="rgba(167,139,250,1)" strokeWidth="2"/>
        {/* Room divisions */}
        <line x1="200" y1="20" x2="200" y2="300" stroke="rgba(167,139,250,1)" strokeWidth="1.5"/>
        <line x1="200" y1="300" x2="560" y2="300" stroke="rgba(167,139,250,1)" strokeWidth="1.5"/>
        <line x1="380" y1="20" x2="380" y2="180" stroke="rgba(167,139,250,1)" strokeWidth="1.5"/>
        <line x1="380" y1="180" x2="560" y2="180" stroke="rgba(167,139,250,1)" strokeWidth="1.5"/>
        <line x1="20" y1="200" x2="200" y2="200" stroke="rgba(167,139,250,1)" strokeWidth="1.5"/>
        {/* Door openings */}
        <line x1="200" y1="120" x2="200" y2="160" stroke="rgba(10,6,18,1)" strokeWidth="3"/>
        <path d="M200,120 Q240,120 240,160" fill="none" stroke="rgba(167,139,250,0.8)" strokeWidth="1"/>
        <line x1="310" y1="300" x2="350" y2="300" stroke="rgba(10,6,18,1)" strokeWidth="3"/>
        <path d="M310,300 Q310,260 350,260" fill="none" stroke="rgba(167,139,250,0.8)" strokeWidth="1"/>
        {/* Furniture hints */}
        <rect x="40" y="40" width="60" height="40" fill="none" stroke="rgba(167,139,250,0.6)" strokeWidth="1"/>
        <rect x="220" y="40" width="100" height="60" fill="none" stroke="rgba(167,139,250,0.6)" strokeWidth="1"/>
        <rect x="400" y="40" width="80" height="50" fill="none" stroke="rgba(167,139,250,0.6)" strokeWidth="1"/>
        <rect x="220" y="200" width="120" height="80" fill="none" stroke="rgba(167,139,250,0.6)" strokeWidth="1"/>
        <rect x="400" y="200" width="60" height="80" fill="none" stroke="rgba(167,139,250,0.6)" strokeWidth="1"/>
        <rect x="40" y="230" width="80" height="50" fill="none" stroke="rgba(167,139,250,0.6)" strokeWidth="1"/>
        <rect x="80" y="320" width="100" height="80" fill="none" stroke="rgba(167,139,250,0.6)" strokeWidth="1"/>
        <rect x="260" y="320" width="80" height="60" fill="none" stroke="rgba(167,139,250,0.6)" strokeWidth="1"/>
        <rect x="420" y="320" width="100" height="80" fill="none" stroke="rgba(167,139,250,0.6)" strokeWidth="1"/>
        {/* Person dot in center */}
        <circle cx="300" cy="220" r="5" fill="rgba(167,139,250,0.8)"/>
        <circle cx="300" cy="220" r="14" fill="none" stroke="rgba(167,139,250,0.4)" strokeWidth="1" strokeDasharray="3 3"/>
      </svg>

      {/* Purple overlay */}
      <div style={{
        position: "absolute", inset: 0,
        background: "radial-gradient(ellipse at 25% 50%, rgba(109,40,217,0.18) 0%, transparent 55%), radial-gradient(ellipse at 80% 80%, rgba(139,92,246,0.08) 0%, transparent 50%)",
        pointerEvents: "none",
      }} />

      {/* Canvas */}
      <canvas ref={canvasRef} style={{ position: "absolute", inset: 0, pointerEvents: "none" }} />

      {/* Vignette */}
      <div style={{
        position: "absolute", inset: 0,
        background: "radial-gradient(ellipse at 72% 50%, transparent 20%, rgba(10,6,18,0.72) 100%)",
        pointerEvents: "none",
      }} />

      {/* Person SVG cursor */}
      {showPerson && (
        <div style={{
          position: "fixed",
          left: personPos.x - 14,
          top: personPos.y - 38,
          pointerEvents: "none",
          zIndex: 9999,
          filter: "drop-shadow(0 0 10px rgba(167,139,250,0.95))",
          opacity: personPos.x > 10 ? 1 : 0,
          transition: "opacity 0.3s",
        }}>
          <svg width="28" height="54" viewBox="0 0 28 54" fill="none">
            <circle cx="14" cy="7" r="5.5" fill="rgba(196,181,253,0.95)"/>
            <line x1="14" y1="12.5" x2="14" y2="33" stroke="rgba(196,181,253,0.95)" strokeWidth="2.5" strokeLinecap="round"/>
            <line x1="4" y1="21" x2="24" y2="21" stroke="rgba(196,181,253,0.95)" strokeWidth="2" strokeLinecap="round"/>
            <line x1="14" y1="33" x2="6" y2="50" stroke="rgba(196,181,253,0.95)" strokeWidth="2" strokeLinecap="round"/>
            <line x1="14" y1="33" x2="22" y2="50" stroke="rgba(196,181,253,0.95)" strokeWidth="2" strokeLinecap="round"/>
            <ellipse cx="14" cy="51" rx="9" ry="2.5" fill="rgba(139,92,246,0.35)"/>
          </svg>
        </div>
      )}

      {/* Click hint */}
      {showPerson && (
        <div style={{
          position: "fixed",
          left: personPos.x + 20,
          top: personPos.y - 8,
          pointerEvents: "none",
          zIndex: 9999,
          fontSize: "9px",
          letterSpacing: "0.2em",
          color: "rgba(167,139,250,0.45)",
          fontFamily: "'Share Tech Mono', monospace",
          whiteSpace: "nowrap",
        }}>
          click to spark
        </div>
      )}

      {/* Left content */}
      <div style={{
        position: "absolute",
        left: 0, top: 0, bottom: 0,
        width: "520px",
        display: "flex",
        flexDirection: "column",
        justifyContent: "center",
        padding: "60px 64px",
        background: "linear-gradient(to right, rgba(10,6,18,0.95) 62%, transparent)",
        opacity: visible ? 1 : 0,
        transform: visible ? "translateX(0)" : "translateX(-30px)",
        transition: "opacity 1.2s ease, transform 1.2s ease",
      }}>

        {/* Logo */}
        <div style={{ display: "flex", alignItems: "center", gap: "16px", marginBottom: "52px" }}>
          <img src="/logo.png" alt="logo" style={{
            width: "52px", height: "52px", objectFit: "contain",
            filter: "hue-rotate(200deg) saturate(1.3)",
          }}/>
          <div>
            <div style={{
              fontSize: "10px", letterSpacing: "0.35em",
              color: "rgba(167,139,250,0.55)", textTransform: "uppercase", marginBottom: "3px",
            }}>AIA Studio 2026</div>
            <div style={{
              fontSize: "15px", fontWeight: 700, letterSpacing: "0.18em", color: "#e9d5ff",
            }}>SPATIAL FLOW</div>
          </div>
        </div>

        {/* Welcome label */}
        <div style={{
          fontSize: "11px", letterSpacing: "0.45em",
          color: "rgba(167,139,250,0.5)", textTransform: "uppercase",
          marginBottom: "10px",
          opacity: visible ? 1 : 0,
          transition: "opacity 1.4s ease 0.4s",
        }}>Welcome to</div>

        {/* WELCOME title */}
        <h1 style={{
          fontSize: "clamp(40px, 5vw, 60px)",
          fontWeight: 900,
          lineHeight: 1.0,
          letterSpacing: "0.06em",
          color: "#f5f3ff",
          margin: "0 0 28px 0",
          textShadow: "0 0 60px rgba(139,92,246,0.5)",
          opacity: visible ? 1 : 0,
          transition: "opacity 1.4s ease 0.6s",
        }}>WELCOME</h1>

        {/* Accent line */}
        <div style={{
          width: visible ? "72px" : "0px",
          height: "1.5px",
          background: "linear-gradient(to right, rgba(167,139,250,0.8), transparent)",
          marginBottom: "28px",
          transition: "width 1.2s ease 0.9s",
        }}/>

        {/* About */}
        <div style={{
          fontFamily: "'Inter', sans-serif",
          fontSize: "13.5px",
          fontWeight: 300,
          lineHeight: 1.85,
          color: "rgba(196,181,253,0.78)",
          marginBottom: "44px",
          opacity: visible ? 1 : 0,
          transition: "opacity 1.4s ease 1.0s",
        }}>
          <p style={{ margin: "0 0 14px 0" }}>
            <span style={{ color: "rgba(216,180,254,1)", fontWeight: 400 }}>Spatial Flow Copilot</span>{" "}
            is an AI-powered spatial reasoning agent built for industrial design.
            It understands your floor plan, places equipment intelligently, and
            iterates until the layout meets real safety standards — OSHA, NFPA, and ISO.
          </p>
          <p style={{ margin: "0 0 14px 0" }}>
            Drop in a layout. Describe what you need. The agent reasons, places,
            checks clearances, analyzes visibility and circulation paths, and
            explains every decision with grounded spatial logic.
          </p>
          <p style={{ margin: 0, fontSize: "11px", color: "rgba(139,92,246,0.45)", letterSpacing: "0.12em" }}>
            IAAC · AIA Studio 2026 · GROUP 03
          </p>
        </div>

        {/* Enter button */}
        <button
          onClick={onEnter}
          style={{
            alignSelf: "flex-start",
            padding: "13px 44px",
            background: "transparent",
            border: "1px solid rgba(139,92,246,0.5)",
            color: "rgba(196,181,253,0.9)",
            fontSize: "11px",
            letterSpacing: "0.45em",
            textTransform: "uppercase",
            cursor: "none",
            fontFamily: "'Orbitron', monospace",
            opacity: visible ? 1 : 0,
            transition: "opacity 1.4s ease 1.3s, border-color 0.3s, background 0.3s, box-shadow 0.3s",
          }}
          onMouseEnter={e => {
            const b = e.currentTarget;
            b.style.background = "rgba(139,92,246,0.14)";
            b.style.borderColor = "rgba(196,181,253,0.9)";
            b.style.boxShadow = "0 0 28px rgba(139,92,246,0.3), inset 0 0 14px rgba(139,92,246,0.1)";
          }}
          onMouseLeave={e => {
            const b = e.currentTarget;
            b.style.background = "transparent";
            b.style.borderColor = "rgba(139,92,246,0.5)";
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
        color: "rgba(139,92,246,0.22)",
        fontFamily: "'Share Tech Mono', monospace",
        opacity: visible ? 1 : 0,
        transition: "opacity 2s ease 1.6s",
      }}>
        v2.0 · SPATIAL ANALYSIS ENGINE
      </div>
    </div>
  );
}
