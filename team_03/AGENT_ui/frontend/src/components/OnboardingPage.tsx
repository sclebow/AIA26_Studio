import { useState, useEffect, useRef, useCallback } from "react";

export interface OnboardingData {
  role: string;
  roleOther: string;
  experience: string;
  name: string;
  layoutStatus: string;
  workflowType: string;
  workflowCustom: string;
  spaceNotes: string;
  skippedSpaceAgent: boolean;
}

interface OnboardingPageProps {
  onComplete: (data: OnboardingData) => void;
}

const ROLES = ["Designer", "Engineer", "Researcher", "Factory Owner", "Contractor"];

const ICON = {
  width: 22, height: 22, viewBox: "0 0 24 24", fill: "none",
  stroke: "currentColor", strokeWidth: 1.6,
  strokeLinecap: "round" as const, strokeLinejoin: "round" as const,
};

export const LAYOUT_STATUS = [
  { id: "existing", label: "Existing layout with equipment", icon: (
    <svg {...ICON}><rect x="3" y="4" width="18" height="16" rx="1" /><rect x="6" y="7" width="4" height="4" /><rect x="14" y="13" width="4" height="4" /></svg>
  )},
  { id: "empty", label: "Empty layout, ready to populate", icon: (
    <svg {...ICON}><rect x="3" y="4" width="18" height="16" rx="1" strokeDasharray="3 3" /></svg>
  )},
  { id: "scratch", label: "Starting from scratch", icon: (
    <svg {...ICON}><rect x="5" y="3" width="14" height="18" rx="1" /><path d="M12 9v6M9 12h6" /></svg>
  )},
];

export const WORKFLOWS = [
  { id: "electronics", label: "Electronics Assembly", desc: "PCB lines, SMT, clean rooms", icon: (
    <svg {...ICON}><rect x="7" y="7" width="10" height="10" rx="1" /><path d="M10 7V4M14 7V4M10 20v-3M14 20v-3M7 10H4M7 14H4M20 10h-3M20 14h-3" /></svg>
  )},
  { id: "woodworking", label: "Woodworking", desc: "CNC routers, saws, finishing", icon: (
    <svg {...ICON}><rect x="3" y="9" width="18" height="6" rx="1" /><path d="M6 12h5M14 11.5h4" /></svg>
  )},
  { id: "metal", label: "Metal Fabrication", desc: "Welding, press brakes, cutting", icon: (
    <svg {...ICON}><circle cx="12" cy="12" r="3.2" /><path d="M12 2v3M12 19v3M2 12h3M19 12h3M4.9 4.9l2.1 2.1M17 17l2.1 2.1M19.1 4.9L17 7M7 17l-2.1 2.1" /></svg>
  )},
  { id: "food", label: "Food Processing", desc: "Conveyors, packaging, cold storage", icon: (
    <svg {...ICON}><rect x="8" y="6" width="8" height="6" rx="1" /><path d="M3 18h18" /><circle cx="6" cy="20" r="1.4" /><circle cx="12" cy="20" r="1.4" /><circle cx="18" cy="20" r="1.4" /></svg>
  )},
  { id: "automotive", label: "Automotive", desc: "Assembly lines, paint booths", icon: (
    <svg {...ICON}><path d="M5 11l1.6-4h8.8L17 11" /><rect x="3" y="11" width="18" height="5" rx="1" /><circle cx="7.5" cy="18" r="1.6" /><circle cx="16.5" cy="18" r="1.6" /></svg>
  )},
  { id: "warehousing", label: "Warehousing", desc: "Racks, forklifts, loading docks", icon: (
    <svg {...ICON}><rect x="3" y="4" width="18" height="16" rx="1" /><path d="M3 10h18M3 15h18M9 4v16M15 4v16" /></svg>
  )},
  { id: "custom", label: "Custom", desc: "Describe your own space", icon: (
    <svg {...ICON}><path d="M4 20l4-1L19 8l-3-3L5 16z" /><path d="M14 7l3 3" /></svg>
  )},
];

// ── Isovist ray type ──────────────────────────────────────────────────────
interface IsovistRay {
  ox: number; oy: number;
  tx: number; ty: number;
  progress: number;
  speed: number;
  alpha: number;
  done: boolean;
}

export default function OnboardingPage({ onComplete }: OnboardingPageProps) {
  const [step, setStep] = useState<"user" | "space">("user");
  const [morphPhase, setMorphPhase] = useState<"idle" | "out" | "in">("idle");
  const [displayStep, setDisplayStep] = useState<"user" | "space">("user");

  const [role, setRole] = useState("");
  const [roleOther, setRoleOther] = useState("");
  const [name, setName] = useState("");
  const [layoutStatus, setLayoutStatus] = useState("");
  const [workflowType, setWorkflowType] = useState("");
  const [workflowCustom, setWorkflowCustom] = useState("");
  const [spaceNotes, setSpaceNotes] = useState("");

  // Cursor
  const mouseRef = useRef({ x: -9999, y: -9999 });
  const personPosRef = useRef({ x: -9999, y: -9999 });
  const [cursorPos, setCursorPos] = useState({ x: -9999, y: -9999 });

  // Canvas + rays
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const raysRef = useRef<IsovistRay[]>([]);

  const canProceedUser = role === "other" ? roleOther.trim().length > 0 : role !== "";

  // ── Morph transition ──────────────────────────────────────────────────────
  const goToStep = useCallback((next: "user" | "space") => {
    if (morphPhase !== "idle") return;
    setMorphPhase("out");
    setTimeout(() => {
      setDisplayStep(next);
      setStep(next);
      setMorphPhase("in");
      setTimeout(() => setMorphPhase("idle"), 350);
    }, 300);
  }, [morphPhase]);

  // ── Smooth cursor ─────────────────────────────────────────────────────────
  useEffect(() => {
    let id: number;
    let cx = -9999, cy = -9999;
    const tick = () => {
      cx += (mouseRef.current.x - cx) * 0.18;
      cy += (mouseRef.current.y - cy) * 0.18;
      personPosRef.current = { x: cx, y: cy };
      setCursorPos({ x: cx, y: cy });
      id = requestAnimationFrame(tick);
    };
    tick();
    return () => cancelAnimationFrame(id);
  }, []);

  // ── Particle + ray canvas ─────────────────────────────────────────────────
  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    let animId: number;
    let W = window.innerWidth, H = window.innerHeight;
    canvas.width = W; canvas.height = H;

    const NUM = 140;
    const CONNECT = 110;

    interface Particle { x: number; y: number; vx: number; vy: number; r: number; alpha: number; }
    const particles: Particle[] = Array.from({ length: NUM }, () => ({
      x: Math.random() * W, y: Math.random() * H,
      vx: (Math.random() - 0.5) * 0.07, vy: (Math.random() - 0.5) * 0.07,
      r: Math.random() * 2.2 + 0.8,
      alpha: Math.random() * 0.45 + 0.25,
    }));

    const resize = () => { W = window.innerWidth; H = window.innerHeight; canvas.width = W; canvas.height = H; };
    window.addEventListener("resize", resize);

    const onMouseMove = (e: MouseEvent) => { mouseRef.current = { x: e.clientX, y: e.clientY }; };
    window.addEventListener("mousemove", onMouseMove);

    const onClick = (e: MouseEvent) => {
      const count = 16;
      for (let i = 0; i < count; i++) {
        const angle = (i / count) * Math.PI * 2;
        const length = 60 + Math.random() * 80;
        raysRef.current.push({
          ox: e.clientX, oy: e.clientY,
          tx: e.clientX + Math.cos(angle) * length,
          ty: e.clientY + Math.sin(angle) * length,
          progress: 0,
          speed: 0.025 + Math.random() * 0.02,
          alpha: 0.6 + Math.random() * 0.4,
          done: false,
        });
      }
    };
    window.addEventListener("click", onClick);

    const draw = () => {
      ctx.clearRect(0, 0, W, H);
      const px = personPosRef.current.x;
      const py = personPosRef.current.y;
      const PERSON_R = 100;

      // Particles
      particles.forEach(p => {
        p.x += p.vx; p.y += p.vy;
        if (p.x < 0) p.x = W; if (p.x > W) p.x = 0;
        if (p.y < 0) p.y = H; if (p.y > H) p.y = 0;
        const dx = p.x - px, dy = p.y - py;
        const dist = Math.sqrt(dx * dx + dy * dy);
        if (dist < PERSON_R && dist > 0) {
          const f = (PERSON_R - dist) / PERSON_R;
          p.vx += (dx / dist) * f * 0.4; p.vy += (dy / dist) * f * 0.4;
          p.vx *= 0.94; p.vy *= 0.94;
        }
        ctx.beginPath();
        ctx.arc(p.x, p.y, p.r, 0, Math.PI * 2);
        ctx.fillStyle = `rgba(109,40,217,${p.alpha})`;
        ctx.fill();
      });

      // Edges
      for (let i = 0; i < particles.length; i++) {
        for (let j = i + 1; j < particles.length; j++) {
          const dx = particles[i].x - particles[j].x;
          const dy = particles[i].y - particles[j].y;
          const d = Math.sqrt(dx * dx + dy * dy);
          if (d < CONNECT) {
            const a = (1 - d / CONNECT) * 0.22;
            ctx.beginPath();
            ctx.moveTo(particles[i].x, particles[i].y);
            ctx.lineTo(particles[j].x, particles[j].y);
            ctx.strokeStyle = `rgba(109,40,217,${a})`;
            ctx.lineWidth = 0.8; ctx.stroke();
          }
        }
      }

      // Isovist rays
      const rays = raysRef.current;
      for (let i = rays.length - 1; i >= 0; i--) {
        const c = rays[i];
        c.progress += c.speed;
        const ease = 1 - Math.pow(1 - c.progress, 3);
        const cx2 = c.ox + (c.tx - c.ox) * ease;
        const cy2 = c.oy + (c.ty - c.oy) * ease;
        const fadeAlpha = c.alpha * (1 - c.progress);

        ctx.beginPath();
        ctx.moveTo(c.ox, c.oy);
        ctx.lineTo(cx2, cy2);
        ctx.strokeStyle = `rgba(109,40,217,${fadeAlpha * 0.5})`;
        ctx.lineWidth = 0.6; ctx.stroke();

        ctx.beginPath();
        ctx.arc(cx2, cy2, 2, 0, Math.PI * 2);
        ctx.fillStyle = `rgba(109,40,217,${fadeAlpha})`;
        ctx.fill();

        if (c.progress < 0.4) {
          const ringR = c.progress * 40;
          const ringA = (1 - c.progress / 0.4) * 0.3;
          ctx.beginPath();
          ctx.arc(c.ox, c.oy, ringR, 0, Math.PI * 2);
          ctx.strokeStyle = `rgba(109,40,217,${ringA})`;
          ctx.lineWidth = 0.8; ctx.stroke();
        }

        if (c.progress >= 1) rays.splice(i, 1);
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

  const handleComplete = (skipped = false) => {
    onComplete({
      role: role === "other" ? roleOther : role,
      roleOther, experience: "", name,
      layoutStatus, workflowType, workflowCustom, spaceNotes,
      skippedSpaceAgent: skipped,
    });
  };

  const showCursor = cursorPos.x > 10;

  // ── Morph style ───────────────────────────────────────────────────────────
  const morphStyle: React.CSSProperties = {
    opacity: morphPhase === "out" ? 0 : 1,
    transform: morphPhase === "out"
      ? "scale(0.97) translateY(8px)"
      : morphPhase === "in"
      ? "scale(1) translateY(0)"
      : "scale(1) translateY(0)",
    filter: morphPhase === "out" ? "blur(2px)" : "blur(0px)",
    transition: morphPhase === "out"
      ? "opacity 0.3s ease, transform 0.3s ease, filter 0.3s ease"
      : "opacity 0.35s ease 0.05s, transform 0.35s ease 0.05s, filter 0.35s ease 0.05s",
  };

  // ── Shared styles ─────────────────────────────────────────────────────────
  const accent = "rgba(109,40,217,";
  const s = {
    btn: (active: boolean): React.CSSProperties => ({
      padding: "9px 20px",
      background: active ? `${accent}0.1)` : "transparent",
      border: `1px solid ${active ? `${accent}0.7)` : `${accent}0.2)`}`,
      color: active ? "#3b0764" : `${accent}0.55)`,
      fontSize: "11px", letterSpacing: "0.25em",
      textTransform: "uppercase" as const,
      cursor: "pointer",
      fontFamily: "'Share Tech Mono', monospace",
      boxShadow: active ? `0 0 14px ${accent}0.12)` : "none",
      transition: "all 0.2s",
    }),
    input: {
      width: "100%",
      background: `${accent}0.04)`,
      border: `1px solid ${accent}0.2)`,
      color: "#3b0764",
      padding: "10px 14px", fontSize: "12px",
      fontFamily: "'Share Tech Mono', monospace",
      letterSpacing: "0.05em", outline: "none",
      boxSizing: "border-box" as const,
    },
    textarea: {
      width: "100%",
      background: `${accent}0.04)`,
      border: `1px solid ${accent}0.2)`,
      color: "#3b0764",
      padding: "12px 14px", fontSize: "12px",
      fontFamily: "'Share Tech Mono', monospace",
      letterSpacing: "0.05em", outline: "none",
      resize: "none" as const,
      boxSizing: "border-box" as const,
      minHeight: "72px",
    },
    sectionLabel: {
      fontSize: "10px", letterSpacing: "0.35em",
      color: `${accent}0.45)`, textTransform: "uppercase" as const,
      marginBottom: "14px",
      fontFamily: "'Share Tech Mono', monospace",
    },
    section: { marginBottom: "24px" },
    btnRow: { display: "flex", flexWrap: "wrap" as const, gap: "10px" },
    primaryBtn: (enabled: boolean): React.CSSProperties => ({
      padding: "11px 36px",
      background: enabled ? `${accent}0.1)` : "transparent",
      border: `1px solid ${enabled ? `${accent}0.6)` : `${accent}0.15)`}`,
      color: enabled ? "#3b0764" : `${accent}0.3)`,
      fontSize: "11px", letterSpacing: "0.4em",
      textTransform: "uppercase" as const,
      cursor: enabled ? "pointer" : "default",
      fontFamily: "'Orbitron', monospace",
      boxShadow: enabled ? `0 0 20px ${accent}0.12)` : "none",
      transition: "all 0.2s",
    }),
    skipBtn: {
      padding: "11px 24px", background: "transparent",
      border: `1px solid ${accent}0.15)`,
      color: `${accent}0.4)`, fontSize: "10px",
      letterSpacing: "0.35em", textTransform: "uppercase" as const,
      cursor: "pointer", fontFamily: "'Share Tech Mono', monospace",
      transition: "all 0.2s",
    } as React.CSSProperties,
    workflowGrid: {
      display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(140px, 1fr))",
      gap: "8px",
    },
    workflowCard: (active: boolean): React.CSSProperties => ({
      padding: "14px 12px", cursor: "pointer",
      background: active ? `${accent}0.08)` : "transparent",
      border: `1px solid ${active ? `${accent}0.6)` : `${accent}0.15)`}`,
      transition: "all 0.2s",
      display: "flex", flexDirection: "column", gap: "6px",
    }),
    workflowIcon: {
      color: `${accent}0.7)`,
      display: "flex", alignItems: "center",
    },
    workflowLabel: (active: boolean): React.CSSProperties => ({
      fontSize: "11px", letterSpacing: "0.1em",
      color: active ? "#3b0764" : `${accent}0.6)`,
      textTransform: "uppercase",
      fontFamily: "'Share Tech Mono', monospace",
    }),
    workflowDesc: {
      fontSize: "10px", color: `${accent}0.45)`,
      fontFamily: "'Share Tech Mono', monospace",
      letterSpacing: "0.05em",
    },
  };

  return (
    <div style={{
      position: "fixed", inset: 0,
      background: "#f5f3ff",
      display: "flex", alignItems: "center", justifyContent: "center",
      fontFamily: "'Share Tech Mono', monospace",
      overflow: "hidden",
      cursor: "none",
    }}>
      <link href="https://fonts.googleapis.com/css2?family=Orbitron:wght@400;700;900&family=Share+Tech+Mono&display=swap" rel="stylesheet" />

      {/* Grid */}
      <div style={{
        position: "absolute", inset: 0,
        backgroundImage: `linear-gradient(rgba(109,40,217,0.04) 1px, transparent 1px), linear-gradient(90deg, rgba(109,40,217,0.04) 1px, transparent 1px)`,
        backgroundSize: "48px 48px", pointerEvents: "none",
      }} />

      {/* Radial glow */}
      <div style={{
        position: "absolute", inset: 0,
        background: "radial-gradient(ellipse at 20% 80%, rgba(109,40,217,0.08) 0%, transparent 55%), radial-gradient(ellipse at 80% 20%, rgba(139,92,246,0.06) 0%, transparent 50%)",
        pointerEvents: "none",
      }} />

      {/* Canvas */}
      <canvas ref={canvasRef} style={{ position: "absolute", inset: 0, pointerEvents: "none" }} />

      {/* Crosshair cursor */}
      {showCursor && (
        <div style={{
          position: "fixed",
          left: cursorPos.x - 16, top: cursorPos.y - 16,
          pointerEvents: "none", zIndex: 9999,
          filter: "drop-shadow(0 0 6px rgba(109,40,217,0.4))",
        }}>
          <svg width="32" height="32" viewBox="0 0 32 32" fill="none">
            <circle cx="16" cy="16" r="10" stroke="rgba(109,40,217,0.75)" strokeWidth="1"/>
            <circle cx="16" cy="16" r="2" fill="rgba(109,40,217,0.9)"/>
            <line x1="16" y1="2" x2="16" y2="10" stroke="rgba(109,40,217,0.75)" strokeWidth="1" strokeLinecap="round"/>
            <line x1="16" y1="22" x2="16" y2="30" stroke="rgba(109,40,217,0.75)" strokeWidth="1" strokeLinecap="round"/>
            <line x1="2" y1="16" x2="10" y2="16" stroke="rgba(109,40,217,0.75)" strokeWidth="1" strokeLinecap="round"/>
            <line x1="22" y1="16" x2="30" y2="16" stroke="rgba(109,40,217,0.75)" strokeWidth="1" strokeLinecap="round"/>
            <line x1="24" y1="8" x2="26" y2="6" stroke="rgba(109,40,217,0.4)" strokeWidth="0.8" strokeLinecap="round"/>
            <line x1="8" y1="8" x2="6" y2="6" stroke="rgba(109,40,217,0.4)" strokeWidth="0.8" strokeLinecap="round"/>
            <line x1="24" y1="24" x2="26" y2="26" stroke="rgba(109,40,217,0.4)" strokeWidth="0.8" strokeLinecap="round"/>
            <line x1="8" y1="24" x2="6" y2="26" stroke="rgba(109,40,217,0.4)" strokeWidth="0.8" strokeLinecap="round"/>
          </svg>
        </div>
      )}

      {/* Card */}
      <div style={{
        position: "relative", zIndex: 10,
        width: "min(560px, 88vw)",
        background: "rgba(245,243,255,0.92)",
        border: "1px solid rgba(109,40,217,0.18)",
        boxShadow: "0 0 60px rgba(109,40,217,0.08), 0 2px 32px rgba(109,40,217,0.06)",
        padding: "40px 44px",
        backdropFilter: "blur(12px)",
      }}>

        {/* Step indicator */}
        <div style={{ display: "flex", alignItems: "center", gap: "12px", marginBottom: "28px" }}>
          <span style={{
            width: 8, height: 8, borderRadius: "50%",
            background: step === "space" ? `${accent}0.9)` : `${accent}0.9)`,
            boxShadow: step === "user" ? `0 0 10px ${accent}0.5)` : "none",
            transition: "all 0.3s",
          }} />
          <span style={{
            fontSize: "10px", letterSpacing: "0.3em",
            color: step === "user" ? "#3b0764" : `${accent}0.35)`,
            textTransform: "uppercase", transition: "color 0.3s",
            fontFamily: "'Share Tech Mono', monospace",
          }}>User Profile</span>
          <span style={{ flex: 1, height: 1, background: `${accent}0.15)` }} />
          <span style={{
            width: 8, height: 8, borderRadius: "50%",
            background: step === "space" ? `${accent}0.9)` : `${accent}0.2)`,
            boxShadow: step === "space" ? `0 0 10px ${accent}0.5)` : "none",
            transition: "all 0.3s",
          }} />
          <span style={{
            fontSize: "10px", letterSpacing: "0.3em",
            color: step === "space" ? "#3b0764" : `${accent}0.35)`,
            textTransform: "uppercase", transition: "color 0.3s",
            fontFamily: "'Share Tech Mono', monospace",
          }}>Space Setup</span>
        </div>

        {/* Content with morph */}
        <div style={morphStyle}>

          {/* ── USER STEP ── */}
          {displayStep === "user" && (
            <>
              <div style={{ fontSize: "11px", letterSpacing: "0.4em", color: `${accent}0.45)`, textTransform: "uppercase", marginBottom: "8px" }}>
                Step 01
              </div>
              <div style={{
                fontSize: "22px", fontWeight: 700, letterSpacing: "0.08em",
                color: "#3b0764", marginBottom: "36px",
                fontFamily: "'Orbitron', monospace",
              }}>WHO ARE YOU?</div>

              {/* Role */}
              <div style={s.section}>
                <div style={s.sectionLabel}>Your Role</div>
                <div style={s.btnRow}>
                  {ROLES.map(r => (
                    <button key={r} style={s.btn(role === r)} onClick={() => setRole(r)}>{r}</button>
                  ))}
                  <button style={s.btn(role === "other")} onClick={() => setRole("other")}>Other</button>
                </div>
                {role === "other" && (
                  <input style={{ ...s.input, marginTop: "10px" }}
                    placeholder="Describe your role..."
                    value={roleOther} onChange={e => setRoleOther(e.target.value)} />
                )}
              </div>

              {/* Name */}
              <div style={s.section}>
                <div style={s.sectionLabel}>Your Name (optional)</div>
                <input style={s.input} placeholder="Enter your name..."
                  value={name} onChange={e => setName(e.target.value)} />
              </div>

              <div style={{
                display: "flex", justifyContent: "space-between", alignItems: "center",
                marginTop: "28px", paddingTop: "20px",
                borderTop: `1px solid ${accent}0.1)`,
              }}>
                <div style={{ fontSize: "10px", color: `${accent}0.35)`, letterSpacing: "0.2em", fontFamily: "'Share Tech Mono', monospace" }}>
                  {!canProceedUser ? "Select a role to continue" : "Ready →"}
                </div>
                <button style={s.primaryBtn(canProceedUser)}
                  onClick={canProceedUser ? () => goToStep("space") : undefined}>
                  NEXT
                </button>
              </div>
            </>
          )}

          {/* ── SPACE STEP ── */}
          {displayStep === "space" && (
            <div style={{ maxHeight: "65vh", overflowY: "auto", paddingRight: "4px" }}>
              <div style={{ fontSize: "11px", letterSpacing: "0.4em", color: `${accent}0.45)`, textTransform: "uppercase", marginBottom: "8px" }}>
                Step 02
              </div>
              <div style={{
                fontSize: "22px", fontWeight: 700, letterSpacing: "0.08em",
                color: "#3b0764", marginBottom: "36px",
                fontFamily: "'Orbitron', monospace",
              }}>YOUR SPACE</div>

              {/* Layout status */}
              <div style={s.section}>
                <div style={s.sectionLabel}>Layout Status</div>
                <div style={{ display: "flex", flexDirection: "column", gap: "8px" }}>
                  {LAYOUT_STATUS.map(ls => (
                    <button key={ls.id} style={{
                      ...s.btn(layoutStatus === ls.id),
                      textAlign: "left", padding: "12px 18px",
                      display: "flex", alignItems: "center", gap: "14px",
                    }} onClick={() => setLayoutStatus(ls.id)}>
                      <span style={{ display: "flex", alignItems: "center", opacity: 0.75, color: `${accent}1)` }}>{ls.icon}</span>
                      <span>{ls.label}</span>
                    </button>
                  ))}
                </div>
              </div>

              {/* Workflow type */}
              <div style={s.section}>
                <div style={s.sectionLabel}>Workflow Type</div>
                <div style={s.workflowGrid}>
                  {WORKFLOWS.map(w => (
                    <div key={w.id} style={s.workflowCard(workflowType === w.id)}
                      onClick={() => setWorkflowType(w.id)}>
                      <div style={s.workflowIcon}>{w.icon}</div>
                      <div style={s.workflowLabel(workflowType === w.id)}>{w.label}</div>
                      <div style={s.workflowDesc}>{w.desc}</div>
                    </div>
                  ))}
                </div>
                {workflowType === "custom" && (
                  <input style={{ ...s.input, marginTop: "12px" }}
                    placeholder="Describe your workflow type..."
                    value={workflowCustom} onChange={e => setWorkflowCustom(e.target.value)} />
                )}
              </div>

              {/* Notes */}
              <div style={s.section}>
                <div style={s.sectionLabel}>Anything else? (optional)</div>
                <textarea style={s.textarea}
                  placeholder="Describe your space, constraints, or goals..."
                  value={spaceNotes} onChange={e => setSpaceNotes(e.target.value)} />
              </div>

              <div style={{
                display: "flex", justifyContent: "space-between", alignItems: "center",
                marginTop: "28px", paddingTop: "20px",
                borderTop: `1px solid ${accent}0.1)`,
              }}>
                <div style={{ display: "flex", gap: "12px" }}>
                  <button style={s.skipBtn} onClick={() => handleComplete(true)}>SKIP</button>
                  <button style={{ ...s.skipBtn, color: `${accent}0.55)`, borderColor: `${accent}0.25)` }}
                    onClick={() => goToStep("user")}>← BACK</button>
                </div>
                <button style={s.primaryBtn(true)} onClick={() => handleComplete(false)}>
                  ENTER STUDIO
                </button>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
