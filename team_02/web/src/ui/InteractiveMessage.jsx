import { useMemo } from "react";
import { SENSES, SC, SI, scoreColor } from "../lib/constants.js";
import { useSelection } from "../lib/selection.jsx";

/*
 * InteractiveMessage — renders a Sensi reply as a NAVIGABLE INDEX into the canvas.
 *
 * Research-grounded (brushing-and-linking, deixis, Strobelt cue rules): the message
 * is not a dashboard — it POINTS. Three deterministic cues over a CLOSED vocabulary,
 * each its own NON-INTERFERING channel (no cue-stacking):
 *   - rooms  → a neutral underline + halo (hover lights the room on the plan, and back)
 *   - senses → their spectral glyph (∿ △ ○ □ ≈ ∶) in the sense hue (hover lights the lens)
 *   - scores → the 0-1 number tinted by pass/warn/fail, so a weak spot catches the eye
 * No LLM markup contract, no hallucinated UI.
 */

const HEADER_RE = /^(For\s+[^,\n]+\([^)]+\)[^:\n]*:)\s*/;
const SENSE_SET = new Set(SENSES);
const SCORE_RE = /^[01]\.\d/;

const escapeRe = (s) => s.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");

function buildVocab(roomNames) {
  const rooms = (roomNames || []).filter(Boolean);
  const roomByLower = new Map(rooms.map((r) => [r.toLowerCase(), r]));
  // longest-first so "Living Area" wins over a bare "Area"; senses are single words;
  // plus a 0-1 score pattern (0.15, 0.87, 1.00) for the tinted-number cue.
  const terms = [...new Set([...rooms, ...SENSES])].sort((a, b) => b.length - a.length).map(escapeRe);
  const re = new RegExp(`\\b(${[...terms, "[01]\\.\\d{1,2}"].join("|")})\\b`, "gi");
  return { re, roomByLower };
}

function RoomSpan({ name }) {
  const { focusRoom, activeRoom, setHoverRoom, setActiveRoom } = useSelection();
  const active = focusRoom != null && focusRoom.toLowerCase() === name.toLowerCase();
  return (
    <span className={"msg-room" + (active ? " is-active" : "")}
      onMouseEnter={() => setHoverRoom(name)}
      onMouseLeave={() => setHoverRoom(null)}
      onClick={() => setActiveRoom(activeRoom === name ? null : name)}>
      {name}
    </span>
  );
}

function SenseSpan({ sense, raw }) {
  const { focusSense, setHoverSense, toggleSense } = useSelection();
  const active = focusSense === sense;
  return (
    <span className={"msg-sense" + (active ? " is-active" : "")}
      style={{ "--sense": SC[sense] }}
      onMouseEnter={() => setHoverSense(sense)}
      onMouseLeave={() => setHoverSense(null)}
      onClick={() => toggleSense(sense)}>
      <span className="msg-sense-glyph">{SI[sense]}</span>{raw}
    </span>
  );
}

function ScoreSpan({ raw }) {
  const v = parseFloat(raw);
  return <span className="msg-score" style={{ color: scoreColor(v) }}>{raw}</span>;
}

function linkify(text, vocab, key) {
  if (!vocab.re || !text) return [text];
  const out = [];
  let last = 0, m, i = 0;
  vocab.re.lastIndex = 0;
  while ((m = vocab.re.exec(text)) !== null) {
    if (m.index > last) out.push(text.slice(last, m.index));
    const raw = m[0];
    const lower = raw.toLowerCase();
    if (SCORE_RE.test(raw)) {
      out.push(<ScoreSpan key={`${key}-n${i}`} raw={raw} />);
    } else if (SENSE_SET.has(lower)) {
      out.push(<SenseSpan key={`${key}-s${i}`} sense={lower} raw={raw} />);
    } else if (vocab.roomByLower.has(lower)) {
      out.push(<RoomSpan key={`${key}-r${i}`} name={vocab.roomByLower.get(lower)} />);
    } else {
      out.push(raw);
    }
    last = m.index + raw.length;
    i++;
  }
  if (last < text.length) out.push(text.slice(last));
  return out;
}

// **bold** segments, with linkify inside each segment (port of formatChatMessage)
function renderParagraph(text, vocab, key) {
  return text.split(/(\*\*[^*]+\*\*)/g).filter(Boolean).map((p, i) =>
    p.startsWith("**") && p.endsWith("**")
      ? <strong key={`${key}-b${i}`}>{linkify(p.slice(2, -2), vocab, `${key}-b${i}`)}</strong>
      : <span key={`${key}-t${i}`}>{linkify(p, vocab, `${key}-t${i}`)}</span>
  );
}

export default function InteractiveMessage({ text, rooms }) {
  const vocab = useMemo(() => buildVocab(rooms), [rooms]);
  const t = String(text ?? "");

  let header = null, body = t;
  const hm = t.match(HEADER_RE);
  if (hm) { header = hm[1]; body = t.slice(hm[0].length); }

  const paras = body.split(/\n\n+/).map((p) => p.trim()).filter(Boolean);

  return (
    <>
      {header && <span className="bubble-msg-header">{header}</span>}
      {paras.map((p, i) => (
        <p className="bubble-msg-para" key={`p${i}`}>{renderParagraph(p, vocab, `p${i}`)}</p>
      ))}
    </>
  );
}
