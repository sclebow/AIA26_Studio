import { useEffect, useRef, useState } from "react";
import SensiAvatar from "../components/SensiAvatar.jsx";
import Thinking from "../components/Thinking.jsx";
import * as api from "../api/client.js";

let _pid = 0;
const nextId = () => ++_pid;

// SUB-STEP 3a: functional profile-review chat (the profileChat endpoint is
// simple text). The compact profile summary strip is fleshed out in 3c.
export default function ProfileChatScreen({ persona, onConfirm }) {
  const p = persona || {};
  const [messages, setMessages] = useState([]);
  const [draft, setDraft] = useState("");
  const [thinking, setThinking] = useState(false);
  const ref = useRef(null);

  useEffect(() => {
    const name = p.name || "you";
    const top = (p.sensory_priorities || []).slice(0, 3).join(", ");
    const opener =
      `Your profile is live, ${name}.` +
      (top ? ` Your top comfort drivers are ${top}.` : "") +
      ` Ask me anything — why a weight landed where it did, what the evidence baseline means, or whether something feels off.`;
    setMessages([{ id: nextId(), role: "s", text: opener }]);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    const t = setTimeout(() => { if (ref.current) ref.current.scrollTop = ref.current.scrollHeight; }, 50);
    return () => clearTimeout(t);
  }, [messages, thinking]);

  const send = async () => {
    const text = draft.trim();
    if (!text) return;
    setDraft("");
    setMessages((m) => [...m, { id: nextId(), role: "u", text }]);
    setThinking(true);
    try {
      const data = await api.profileChat(text);
      setThinking(false);
      setMessages((m) => [...m, { id: nextId(), role: "s", text: data.message || "" }]);
    } catch {
      setThinking(false);
      setMessages((m) => [...m, { id: nextId(), role: "s", text: "Something went wrong — try asking again." }]);
    }
  };

  let lastSensiId = null;
  messages.forEach((m) => { if (m.role === "s") lastSensiId = m.id; });

  return (
    <div className="screen active">
      <div className="top-bar">
        <div className="top-bar-pill top-bar-pill--wide">
          <SensiAvatar size={26} className="" />
          <span className="top-bar-label">sensi</span>
          <span className="top-bar-section" style={{ marginLeft: 4 }}>profile review</span>
        </div>
      </div>

      <div className="thread" ref={ref}>
        <div className="thread-inner">
          {messages.map((m) =>
            m.role === "s" ? (
              <div className="bubble-wrap" key={m.id}>
                {m.id === lastSensiId && !thinking ? <SensiAvatar size={28} /> : <div className="sensi-avatar-static" />}
                <p className="bubble-s">{m.text}</p>
              </div>
            ) : (
              <div className="bubble-u" key={m.id}>{m.text}</div>
            )
          )}
          {thinking && <Thinking />}
        </div>
      </div>

      <div className="input-area" style={{ maxWidth: 560, margin: "0 auto", width: "100%" }}>
        <div className="send-row">
          <textarea
            className="sensi-input" placeholder="ask about your profile, weights, or formula…"
            value={draft} onChange={(e) => setDraft(e.target.value)}
            onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); send(); } }}
          />
          <button className="btn-send" onClick={send}>→</button>
        </div>
        <button className="btn-action" onClick={onConfirm} style={{ marginTop: 10 }}>profile looks good →</button>
      </div>
    </div>
  );
}
