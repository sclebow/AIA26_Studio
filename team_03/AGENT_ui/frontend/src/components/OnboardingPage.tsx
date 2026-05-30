import { useState } from "react";

export interface OnboardingData {
  // User Agent
  role: string;
  roleOther: string;
  experience: string;
  name: string;
  // Space Agent
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
const EXPERIENCE = ["Beginner", "Intermediate", "Expert"];
// Shared props for the minimalist line icons.
const ICON = {
  width: 22, height: 22, viewBox: "0 0 24 24", fill: "none",
  stroke: "currentColor", strokeWidth: 1.6,
  strokeLinecap: "round" as const, strokeLinejoin: "round" as const,
};

const LAYOUT_STATUS = [
  { id: "existing", label: "Existing layout with equipment", icon: (
    <svg {...ICON}><rect x="3" y="4" width="18" height="16" rx="1" /><rect x="6" y="7" width="4" height="4" /><rect x="14" y="13" width="4" height="4" /></svg>
  ) },
  { id: "empty", label: "Empty layout, ready to populate", icon: (
    <svg {...ICON}><rect x="3" y="4" width="18" height="16" rx="1" strokeDasharray="3 3" /></svg>
  ) },
  { id: "scratch", label: "Starting from scratch", icon: (
    <svg {...ICON}><rect x="5" y="3" width="14" height="18" rx="1" /><path d="M12 9v6M9 12h6" /></svg>
  ) },
];
const WORKFLOWS = [
  { id: "electronics", label: "Electronics Assembly", desc: "PCB lines, SMT, clean rooms", icon: (
    <svg {...ICON}><rect x="7" y="7" width="10" height="10" rx="1" /><path d="M10 7V4M14 7V4M10 20v-3M14 20v-3M7 10H4M7 14H4M20 10h-3M20 14h-3" /></svg>
  ) },
  { id: "woodworking", label: "Woodworking", desc: "CNC routers, saws, finishing", icon: (
    <svg {...ICON}><rect x="3" y="9" width="18" height="6" rx="1" /><path d="M6 12h5M14 11.5h4" /></svg>
  ) },
  { id: "metal", label: "Metal Fabrication", desc: "Welding, press brakes, cutting", icon: (
    <svg {...ICON}><circle cx="12" cy="12" r="3.2" /><path d="M12 2v3M12 19v3M2 12h3M19 12h3M4.9 4.9l2.1 2.1M17 17l2.1 2.1M19.1 4.9L17 7M7 17l-2.1 2.1" /></svg>
  ) },
  { id: "food", label: "Food Processing", desc: "Conveyors, packaging, cold storage", icon: (
    <svg {...ICON}><rect x="8" y="6" width="8" height="6" rx="1" /><path d="M3 18h18" /><circle cx="6" cy="20" r="1.4" /><circle cx="12" cy="20" r="1.4" /><circle cx="18" cy="20" r="1.4" /></svg>
  ) },
  { id: "automotive", label: "Automotive", desc: "Assembly lines, paint booths", icon: (
    <svg {...ICON}><path d="M5 11l1.6-4h8.8L17 11" /><rect x="3" y="11" width="18" height="5" rx="1" /><circle cx="7.5" cy="18" r="1.6" /><circle cx="16.5" cy="18" r="1.6" /></svg>
  ) },
  { id: "warehousing", label: "Warehousing", desc: "Racks, forklifts, loading docks", icon: (
    <svg {...ICON}><rect x="3" y="4" width="18" height="16" rx="1" /><path d="M3 10h18M3 15h18M9 4v16M15 4v16" /></svg>
  ) },
  { id: "custom", label: "Custom", desc: "Describe your own space", icon: (
    <svg {...ICON}><path d="M4 20l4-1L19 8l-3-3L5 16z" /><path d="M14 7l3 3" /></svg>
  ) },
];

export default function OnboardingPage({ onComplete }: OnboardingPageProps) {
  const [step, setStep] = useState<"user" | "space">("user");
  const [role, setRole] = useState("");
  const [roleOther, setRoleOther] = useState("");
  const [experience, setExperience] = useState("");
  const [name, setName] = useState("");
  const [layoutStatus, setLayoutStatus] = useState("");
  const [workflowType, setWorkflowType] = useState("");
  const [workflowCustom, setWorkflowCustom] = useState("");
  const [spaceNotes, setSpaceNotes] = useState("");

  const canProceedUser = (role === "other" ? roleOther.trim().length > 0 : role !== "") && experience !== "";

  const handleUserNext = () => setStep("space");

  const handleComplete = (skipped = false) => {
    onComplete({
      role: role === "other" ? roleOther : role,
      roleOther,
      experience,
      name,
      layoutStatus,
      workflowType,
      workflowCustom,
      spaceNotes,
      skippedSpaceAgent: skipped,
    });
  };

  const s = {
    root: {
      position: "fixed", inset: 0,
      background: "#0a0612",
      display: "flex", alignItems: "center", justifyContent: "center",
      fontFamily: "'Share Tech Mono', monospace",
      overflow: "hidden",
    } as React.CSSProperties,
    bg: {
      position: "absolute", inset: 0,
      background: "radial-gradient(ellipse at 20% 80%, rgba(109,40,217,0.12) 0%, transparent 55%), radial-gradient(ellipse at 80% 20%, rgba(139,92,246,0.08) 0%, transparent 50%)",
      pointerEvents: "none",
    } as React.CSSProperties,
    grid: {
      position: "absolute", inset: 0,
      backgroundImage: "linear-gradient(rgba(139,92,246,0.04) 1px, transparent 1px), linear-gradient(90deg, rgba(139,92,246,0.04) 1px, transparent 1px)",
      backgroundSize: "48px 48px",
      pointerEvents: "none",
    } as React.CSSProperties,
    card: {
      position: "relative", zIndex: 10,
      width: "min(544px, 88vw)",
      background: "rgba(15,9,30,0.92)",
      border: "1px solid rgba(139,92,246,0.2)",
      boxShadow: "0 0 80px rgba(109,40,217,0.15), inset 0 0 40px rgba(109,40,217,0.03)",
      padding: "40px 44px",
    } as React.CSSProperties,
    stepIndicator: {
      display: "flex", alignItems: "center", gap: "12px",
      marginBottom: "28px",
    },
    dot: (active: boolean, done: boolean): React.CSSProperties => ({
      width: "8px", height: "8px", borderRadius: "50%",
      background: done ? "rgba(255, 255, 255, 0.9)" : active ? "rgba(167,139,250,0.9)" : "rgba(139,92,246,0.2)",
      boxShadow: active ? "0 0 12px rgba(167,139,250,0.6)" : "none",
      transition: "all 0.3s",
    }),
    dotLine: {
      flex: 1, height: "1px",
      background: "rgba(139,92,246,0.2)",
    },
    stepLabel: (active: boolean): React.CSSProperties => ({
      fontSize: "10px", letterSpacing: "0.3em",
      color: active ? "rgba(255, 255, 255, 0.8)" : "rgba(139,92,246,0.35)",
      textTransform: "uppercase",
      transition: "color 0.3s",
    }),
    heading: {
      fontSize: "11px", letterSpacing: "0.4em",
      color: "rgba(167,139,250,0.5)", textTransform: "uppercase",
      marginBottom: "8px",
    },
    title: {
      fontSize: "22px", fontWeight: 700, letterSpacing: "0.08em",
      color: "#f5f3ff", marginBottom: "36px",
      fontFamily: "'Orbitron', monospace",
      textShadow: "0 0 40px rgba(139,92,246,0.3)",
    },
    sectionLabel: {
      fontSize: "10px", letterSpacing: "0.35em",
      color: "rgba(167,139,250,0.45)", textTransform: "uppercase",
      marginBottom: "14px",
    },
    section: { marginBottom: "24px" },
    btnRow: { display: "flex", flexWrap: "wrap" as const, gap: "10px" },
    btn: (active: boolean): React.CSSProperties => ({
      padding: "9px 20px",
      background: active ? "rgba(139,92,246,0.2)" : "transparent",
      border: `1px solid ${active ? "rgba(167,139,250,0.7)" : "rgba(139,92,246,0.25)"}`,
      color: active ? "rgb(255, 255, 255)" : "rgba(167,139,250,0.5)",
      fontSize: "11px", letterSpacing: "0.25em",
      textTransform: "uppercase" as const,
      cursor: "pointer",
      fontFamily: "'Share Tech Mono', monospace",
      boxShadow: active ? "0 0 16px rgba(139,92,246,0.2)" : "none",
      transition: "all 0.2s",
    }),
    input: {
      width: "100%",
      background: "rgba(139,92,246,0.05)",
      border: "1px solid rgba(139,92,246,0.2)",
      color: "rgba(255, 255, 255, 0.9)",
      padding: "10px 14px",
      fontSize: "12px",
      fontFamily: "'Share Tech Mono', monospace",
      letterSpacing: "0.05em",
      outline: "none",
      boxSizing: "border-box" as const,
    },
    textarea: {
      width: "100%",
      background: "rgba(139,92,246,0.05)",
      border: "1px solid rgba(139,92,246,0.2)",
      color: "rgba(255, 255, 255, 0.9)",
      padding: "12px 14px",
      fontSize: "12px",
      fontFamily: "'Share Tech Mono', monospace",
      letterSpacing: "0.05em",
      outline: "none",
      resize: "none" as const,
      boxSizing: "border-box" as const,
      minHeight: "72px",
    },
    workflowGrid: {
      display: "grid",
      gridTemplateColumns: "repeat(auto-fill, minmax(136px, 1fr))",
      gap: "10px",
    },
    workflowCard: (active: boolean): React.CSSProperties => ({
      padding: "12px 10px",
      background: active ? "rgba(139,92,246,0.15)" : "rgba(139,92,246,0.03)",
      border: `1px solid ${active ? "rgb(255, 255, 255)" : "rgba(139,92,246,0.18)"}`,
      cursor: "pointer",
      transition: "all 0.2s",
      boxShadow: active ? "0 0 20px rgba(139,92,246,0.15)" : "none",
    }),
    workflowIcon: { marginBottom: "8px", display: "flex", justifyContent: "center", color: "#c4b5fd" } as React.CSSProperties,
    workflowLabel: (active: boolean): React.CSSProperties => ({
      fontSize: "11px", letterSpacing: "0.15em",
      color: active ? "rgb(255, 255, 255)" : "rgb(255, 255, 255)",
      textTransform: "uppercase",
      marginBottom: "4px",
      fontFamily: "'Share Tech Mono', monospace",
    }),
    workflowDesc: {
      fontSize: "10px",
      color: "rgba(139,92,246,0.5)",
      fontFamily: "'Share Tech Mono', monospace",
      letterSpacing: "0.05em",
    },
    footer: {
      display: "flex", justifyContent: "space-between", alignItems: "center",
      marginTop: "28px", paddingTop: "20px",
      borderTop: "1px solid rgba(139,92,246,0.12)",
    },
    primaryBtn: (enabled: boolean): React.CSSProperties => ({
      padding: "11px 36px",
      background: enabled ? "rgba(139,92,246,0.15)" : "transparent",
      border: `1px solid ${enabled ? "rgba(167,139,250,0.6)" : "rgba(139,92,246,0.2)"}`,
      color: enabled ? "rgb(255, 255, 255)" : "rgba(139,92,246,0.3)",
      fontSize: "11px", letterSpacing: "0.4em",
      textTransform: "uppercase" as const,
      cursor: enabled ? "pointer" : "default",
      fontFamily: "'Orbitron', monospace",
      boxShadow: enabled ? "0 0 24px rgba(139,92,246,0.2)" : "none",
      transition: "all 0.2s",
    }),
    skipBtn: {
      padding: "11px 24px",
      background: "transparent",
      border: "1px solid rgba(139,92,246,0.15)",
      color: "rgba(139,92,246,0.4)",
      fontSize: "10px", letterSpacing: "0.35em",
      textTransform: "uppercase" as const,
      cursor: "pointer",
      fontFamily: "'Share Tech Mono', monospace",
      transition: "all 0.2s",
    },
  };

  return (
    <div style={s.root}>
      <link href="https://fonts.googleapis.com/css2?family=Orbitron:wght@400;700;900&family=Share+Tech+Mono&display=swap" rel="stylesheet" />
      <div style={s.bg} />
      <div style={s.grid} />

      <div style={s.card}>
        {/* Step indicator */}
        <div style={s.stepIndicator}>
          <span style={s.dot(step === "user", step === "space")} />
          <span style={s.stepLabel(step === "user")}>User Profile</span>
          <span style={s.dotLine} />
          <span style={s.dot(step === "space", false)} />
          <span style={s.stepLabel(step === "space")}>Space Setup</span>
        </div>

        {/* ── USER AGENT ── */}
        {step === "user" && (
          <>
            <div style={s.heading}>Step 01</div>
            <div style={s.title}>WHO ARE YOU?</div>

            {/* Role */}
            <div style={s.section}>
              <div style={s.sectionLabel}>Your Role</div>
              <div style={s.btnRow}>
                {ROLES.map(r => (
                  <button key={r} style={s.btn(role === r)}
                    onClick={() => setRole(r)}>{r}</button>
                ))}
                <button style={s.btn(role === "other")}
                  onClick={() => setRole("other")}>Other</button>
              </div>
              {role === "other" && (
                <input
                  style={{ ...s.input, marginTop: "10px" }}
                  placeholder="Describe your role..."
                  value={roleOther}
                  onChange={e => setRoleOther(e.target.value)}
                />
              )}
            </div>

            {/* Experience */}
            <div style={s.section}>
              <div style={s.sectionLabel}>Experience Level</div>
              <div style={s.btnRow}>
                {EXPERIENCE.map(e => (
                  <button key={e} style={s.btn(experience === e)}
                    onClick={() => setExperience(e)}>{e}</button>
                ))}
              </div>
            </div>

            {/* Name */}
            <div style={s.section}>
              <div style={s.sectionLabel}>Your Name (optional)</div>
              <input style={s.input} placeholder="Enter your name..."
                value={name} onChange={e => setName(e.target.value)} />
            </div>

            <div style={s.footer}>
              <div style={{ fontSize: "10px", color: "rgba(139,92,246,0.3)", letterSpacing: "0.2em" }}>
                {!canProceedUser ? "Select role + experience to continue" : "Ready to continue →"}
              </div>
              <button style={s.primaryBtn(canProceedUser)}
                onClick={canProceedUser ? handleUserNext : undefined}>
                NEXT
              </button>
            </div>
          </>
        )}

        {/* ── SPACE AGENT ── */}
        {step === "space" && (
          <>
            <div style={s.heading}>Step 02</div>
            <div style={s.title}>YOUR SPACE</div>

            {/* Layout status */}
            <div style={s.section}>
              <div style={s.sectionLabel}>Layout Status</div>
              <div style={{ display: "flex", flexDirection: "column" as const, gap: "8px" }}>
                {LAYOUT_STATUS.map(ls => (
                  <button key={ls.id} style={{
                    ...s.btn(layoutStatus === ls.id),
                    textAlign: "left" as const,
                    padding: "12px 18px",
                    display: "flex", alignItems: "center", gap: "14px",
                  }}
                    onClick={() => setLayoutStatus(ls.id)}>
                    <span style={{ display: "flex", alignItems: "center", opacity: 0.85, color: "#c4b5fd" }}>{ls.icon}</span>
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
                  value={workflowCustom}
                  onChange={e => setWorkflowCustom(e.target.value)} />
              )}
            </div>

            {/* Notes */}
            <div style={s.section}>
              <div style={s.sectionLabel}>Anything else? (optional)</div>
              <textarea style={s.textarea}
                placeholder="Describe your space, constraints, or goals..."
                value={spaceNotes}
                onChange={e => setSpaceNotes(e.target.value)} />
            </div>

            <div style={s.footer}>
              <div style={{ display: "flex", gap: "12px" }}>
                <button style={s.skipBtn}
                  onClick={() => handleComplete(true)}>
                  SKIP
                </button>
                <button style={{
                  ...s.skipBtn,
                  color: "rgba(167,139,250,0.5)",
                  borderColor: "rgba(139,92,246,0.25)",
                }}
                  onClick={() => setStep("user")}>
                  ← BACK
                </button>
              </div>
              <button style={s.primaryBtn(true)}
                onClick={() => handleComplete(false)}>
                ENTER STUDIO
              </button>
            </div>
          </>
        )}
      </div>
    </div>
  );
}
