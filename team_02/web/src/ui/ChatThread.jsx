import { useEffect, useRef } from "react";
import SensiAvatar from "../components/SensiAvatar.jsx";
import Thinking from "../components/Thinking.jsx";
import CommitBar from "../components/CommitBar.jsx";

// Shared chat thread — was copy-pasted three times (quiz, profile review, layout
// chat). Renders Sensi/user bubbles, keeps the last Sensi avatar animated, and
// auto-scrolls to the bottom. Pass `format` (e.g. formatChatMessage) to render
// Sensi text as HTML; omit it for plain text. The commit-* props are optional —
// only the layout chat passes them, so quiz/profile threads are unaffected.
export default function ChatThread({ messages, thinking, format, renderMessage, hasUncommitted, uncommittedDelta, onCommit }) {
  const ref = useRef(null);
  useEffect(() => {
    const t = setTimeout(() => { if (ref.current) ref.current.scrollTop = ref.current.scrollHeight; }, 50);
    return () => clearTimeout(t);
  }, [messages, thinking]);

  let lastSensiId = null;
  messages.forEach((m) => { if (m.role === "s") lastSensiId = m.id; });

  return (
    <div className="thread" ref={ref}>
      <div className="thread-inner">
        {messages.map((m) =>
          m.role === "s" ? (
            <div className="bubble-wrap" key={m.id}>
              {m.id === lastSensiId && !thinking ? <SensiAvatar size={28} /> : <div className="sensi-avatar-static" />}
              <div className="bubble-s">
                {renderMessage ? renderMessage(m.text)
                  : format ? <div dangerouslySetInnerHTML={{ __html: format(m.text) }} />
                  : m.text}
              </div>
            </div>
          ) : (
            <div className="bubble-u" key={m.id}>{m.text}</div>
          )
        )}
        {hasUncommitted && onCommit && !thinking && (
          <CommitBar delta={uncommittedDelta} onCommit={onCommit} />
        )}
        {thinking && <Thinking />}
      </div>
    </div>
  );
}
