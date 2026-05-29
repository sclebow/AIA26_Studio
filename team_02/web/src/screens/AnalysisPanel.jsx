import { useEffect, useMemo, useRef, useState } from "react";
import Chart from "chart.js/auto";
import { SC, SI, SENSES, scoreColor } from "../lib/constants.js";

// Topology removed — the room network now lives in the center viewer (SenseSpaceGraph).
// This panel: room chips, bars/radar, conflicts, suggestions, specialist blocks.
// selectedRoom / onSelectRoom are owned by LayoutModeScreen (shared with Zone 2).


function parse(s) { try { return s ? JSON.parse(s) : null; } catch { return null; } }

function sensesFromConflicts(conflicts) {
  const out = [];
  (conflicts || []).forEach((conf) => {
    SENSES.forEach((s) => {
      if (out.includes(s)) return;
      if (typeof conf === "string") { if (conf.indexOf(s) !== -1) out.push(s); }
      else if (conf && typeof conf === "object") { if (s in conf) out.push(s); }
    });
  });
  return out;
}

// ── Per-room sense bars ───────────────────────────────────────────────────────
function RoomBars({ room }) {
  const sc      = room.comfortScores || {};
  const overall = room.overallScore || 0;
  const oColor  = scoreColor(overall);
  return (
    <div>
      <div className="ap-room-detail-header">
        <span className="ap-room-detail-name">{room.roomName || "?"}</span>
        <span className="ap-room-detail-score" style={{ color:oColor, opacity:0.8 }}>{overall.toFixed(2)}</span>
      </div>
      {SENSES.map((s) => {
        const v       = sc[s] !== undefined ? sc[s] : 0;
        const opacity = v < 0.5 ? 1 : v < 0.65 ? 0.65 : 0.38;
        return (
          <div className="ap-bar-row" key={s}>
            <span className="ap-bar-sense">{s}</span>
            <div className="ap-bar-track">
              <div className="ap-bar-fill" style={{ width:`${(v*100).toFixed(1)}%`, background:SC[s], opacity }} />
              <div className="ap-bar-threshold" style={{ left:"50%" }} />
              <div className="ap-bar-threshold" style={{ left:"65%", opacity:0.1 }} />
            </div>
            <span className="ap-bar-val" style={{ color:v < 0.5 ? SC[s] : "rgba(240,237,232,.35)" }}>{v.toFixed(2)}</span>
          </div>
        );
      })}
    </div>
  );
}

// ── Radar chart across all rooms ──────────────────────────────────────────────
function Radar({ rooms }) {
  const ref = useRef(null);
  useEffect(() => {
    if (!ref.current) return;
    const colors = [
      "rgba(232,131,106,0.85)", "rgba(212,185,106,0.85)", "rgba(155,143,212,0.85)",
      "rgba(106,184,200,0.85)", "rgba(139,184,138,0.85)", "rgba(196,168,130,0.85)",
    ];
    const chart = new Chart(ref.current, {
      type: "radar",
      data: {
        labels: SENSES.map((s) => (SI[s] ? SI[s] + " " + s : s)),
        datasets: rooms.map((room, i) => {
          const sc = room.comfortScores || {};
          return {
            label:           room.roomName || "?",
            data:            SENSES.map((s) => (sc[s] || 0) * 100),
            backgroundColor: colors[i % colors.length].replace("0.85","0.07"),
            borderColor:     colors[i % colors.length],
            borderWidth:     1.5, pointRadius:0, pointHoverRadius:3,
          };
        }),
      },
      options: {
        responsive: true,
        scales: { r: {
          min:0, max:100,
          ticks:       { color:"rgba(240,237,232,0.20)", font:{size:8}, backdropColor:"transparent" },
          pointLabels: { color:"rgba(240,237,232,0.60)", font:{size:10, family:"'IBM Plex Mono', monospace"} },
          grid:        { color:"rgba(240,237,232,0.08)" },
          angleLines:  { color:"rgba(240,237,232,0.08)" },
        }},
        plugins: { legend:{ labels:{ color:"rgba(240,237,232,0.55)", font:{size:9}, padding:10, boxWidth:12, usePointStyle:true } } },
      },
    });
    return () => { try { chart.destroy(); } catch { /* noop */ } };
  }, [rooms]);
  return <canvas ref={ref} style={{ width:"100%", minHeight:260 }} />;
}

// ── Collapsible specialist narrative block ────────────────────────────────────
function Specialist({ title, text }) {
  const [open, setOpen] = useState(false);
  if (!text || !text.trim()) return null;
  return (
    <div className="ap-specialist-block" style={{ display:"block" }}>
      <div className="ap-specialist-header" onClick={() => setOpen((o) => !o)}>
        <span className="ap-specialist-title">{title}</span>
        <span className={"ap-specialist-chevron" + (open ? " open" : "")}>▼</span>
      </div>
      {open && <div className="ap-specialist-body">{text}</div>}
    </div>
  );
}

// ── Main panel ────────────────────────────────────────────────────────────────
export default function AnalysisPanel({ data, open, onClose, selectedRoom, onSelectRoom }) {
  const scores      = useMemo(() => parse(data && data.scores_json),      [data]);
  const conflicts   = useMemo(() => parse(data && data.conflicts_json),   [data]);
  const suggestions = useMemo(() => parse(data && data.suggestions_json), [data]);
  const depth  = (data && data.analysis_depth) || "analyze";
  const rooms  = (scores && scores.rooms)               || [];
  const flagged = (conflicts && conflicts.flaggedRooms)  || [];

  const [view,     setView]     = useState("bars");
  const [allRooms, setAllRooms] = useState(false);

  useEffect(() => { if (rooms.length) setAllRooms(false); }, [data]); // eslint-disable-line

  if (!open || !scores) return <div id="analysis-panel-right" />;

  const focusRoom        = rooms.find((r) => r.roomName === selectedRoom);
  const conflictsShown   = depth === "detect" || depth === "full";
  const suggestionsShown = depth === "full";

  return (
    <div id="analysis-panel-right" className="open">

      {/* Header */}
      <div className="ap-header">
        <span className="ap-header-label">analysis</span>
        <span className="ap-depth-tag">{depth}</span>
        <div className="ap-view-toggle">
          {["bars","radar"].map((v) => (
            <button key={v} className={"ap-toggle-btn" + (view === v ? " ap-toggle-active" : "")} onClick={() => setView(v)}>{v}</button>
          ))}
        </div>
        <button className="ap-close" onClick={onClose}>×</button>
      </div>

      <div className="ap-scroll">

        {/* Room chips */}
        {rooms.length >= 2 && (
          <div id="ap-room-selector">
            <div className="ap-section-label" style={{ marginTop:0 }}>rooms</div>
            <div className="ap-room-strip">
              {rooms.map((room) => {
                const o     = room.overallScore || 0;
                const color = scoreColor(o);
                return (
                  <button
                    key={room.roomName}
                    className={"ap-room-chip" + (selectedRoom === room.roomName ? " active" : "")}
                    onClick={() => { onSelectRoom(room.roomName); setAllRooms(false); }}
                  >
                    <span className="ap-room-chip-dot" style={{ background:color, opacity:0.75 }} />
                    <span className="ap-room-chip-name">{room.roomName || "?"}</span>
                  </button>
                );
              })}
            </div>
          </div>
        )}

        {/* Scores — bars or radar */}
        <div id="ap-scores">
          {view === "radar" ? (
            <>
              <div className="ap-section-label">scores — radar</div>
              <Radar rooms={rooms} />
            </>
          ) : (
            <>
              <div className="ap-section-label">scores</div>
              {selectedRoom && !allRooms && focusRoom ? (
                <>
                  <RoomBars room={focusRoom} />
                  <button className="ap-all-rooms-toggle" onClick={() => setAllRooms(true)}>↓  all rooms</button>
                </>
              ) : (
                <>
                  {rooms.map((room) => <RoomBars key={room.roomName} room={room} />)}
                  {selectedRoom && allRooms && (
                    <button className="ap-all-rooms-toggle" onClick={() => setAllRooms(false)}>↑  collapse</button>
                  )}
                </>
              )}
            </>
          )}
        </div>

        <Specialist title="what this means" text={data && data.score_interpretation} />

        {/* Conflicts */}
        {conflictsShown && (
          <div id="ap-conflicts">
            <div className="ap-section-label">conflicts</div>
            {(() => {
              const filtered = selectedRoom ? flagged.filter((r) => r.roomName === selectedRoom) : flagged;
              if (!filtered.length) return (
                <div className="ap-empty">{selectedRoom ? "no conflicts in this room" : "no conflicts detected"}</div>
              );
              return filtered.map((room) => (
                <div className="ap-conflict-room" key={room.roomName}>
                  <span className="ap-room-label">{room.roomName || "?"}</span>
                  {sensesFromConflicts(room.conflicts).map((s) => (
                    <span className="ap-conflict-flag" data-sense={s} key={s}>{s}</span>
                  ))}
                </div>
              ));
            })()}
          </div>
        )}
        {conflictsShown && <Specialist title="why it's failing" text={data && data.conflict_reasoning} />}

        {/* Suggestions */}
        {suggestionsShown && (
          <div id="ap-suggestions">
            <div className="ap-section-label">suggestions</div>
            {(() => {
              const imps  = (suggestions && suggestions.improvements) || [];
              const items = [];
              imps.forEach((room) => {
                if (selectedRoom && room.roomName !== selectedRoom) return;
                (room.suggestions || []).forEach((s) => items.push({ room:room.roomName, ...s }));
              });
              if (!items.length) return (
                <div className="ap-empty">{selectedRoom ? "no suggestions for this room" : "no suggestions generated"}</div>
              );
              return items.map((s, i) => (
                <div className="ap-suggestion-item" key={i}>
                  <span className="ap-suggestion-room">{s.room || "?"}</span>
                  <span className="ap-suggestion-sense" data-sense={s.sense || ""}>{s.sense || ""}</span>
                  <span className="ap-suggestion-text">{s.suggestion || ""}</span>
                </div>
              ));
            })()}
          </div>
        )}
        {suggestionsShown && <Specialist title="what to watch out for" text={data && data.suggestion_critique} />}

      </div>
    </div>
  );
}
