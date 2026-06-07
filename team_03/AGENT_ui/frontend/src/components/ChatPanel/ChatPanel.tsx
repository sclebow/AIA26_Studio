import React, { useRef, useEffect, useState, useCallback } from 'react';
import GlassPanel from '../common/GlassPanel';
import { useTheme } from '../common/ThemeToggle';
import MessageBubble, { Message } from './MessageBubble';

export type { Message };

export interface ChatPanelProps {
  messages: Message[];
  onSend: (text: string) => void;
  isAgentRunning: boolean;
  onReset: () => void;
  onCancel: () => void;
}

const TypingIndicator: React.FC = () => {
  const { colors } = useTheme();
  return (
    <div style={{
      display: 'flex',
      alignItems: 'center',
      gap: '6px',
      padding: '8px 0 4px 8px',
    }}>
      <style>{`
        @keyframes typingBounce {
          0%, 80%, 100% { transform: translateY(0); opacity: 0.4; }
          40% { transform: translateY(-4px); opacity: 1; }
        }
      `}</style>
      {[0, 1, 2].map(i => (
        <span key={i} style={{
          display: 'inline-block',
          width: '6px',
          height: '6px',
          borderRadius: '50%',
          background: colors.accent,
          animation: `typingBounce 1.2s ease-in-out ${i * 0.2}s infinite`,
        }} />
      ))}
      <span style={{
        color: colors.muted,
        fontSize: '12px',
        marginLeft: '4px',
        fontFamily: colors.font,
      }}>
        Agent is thinking
      </span>
    </div>
  );
};

const SendIcon: React.FC = () => (
  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <line x1="22" y1="2" x2="11" y2="13" />
    <polygon points="22 2 15 22 11 13 2 9 22 2" />
  </svg>
);

const TrashIcon: React.FC = () => (
  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <polyline points="3 6 5 6 21 6" />
    <path d="M19 6l-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6" />
    <path d="M10 11v6" />
    <path d="M14 11v6" />
    <path d="M9 6V4a1 1 0 0 1 1-1h4a1 1 0 0 1 1 1v2" />
  </svg>
);

const StopIcon: React.FC = () => (
  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <rect x="3" y="3" width="18" height="18" rx="2" ry="2" />
  </svg>
);

const ChatPanel: React.FC<ChatPanelProps> = ({ messages, onSend, isAgentRunning, onReset, onCancel }) => {
  const { colors } = useTheme();
  const [inputValue, setInputValue] = useState('');
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, isAgentRunning]);

  const handleSend = useCallback(() => {
    const text = inputValue.trim();
    if (!text || isAgentRunning) return;
    onSend(text);
    setInputValue('');
  }, [inputValue, isAgentRunning, onSend]);

  const handleKeyDown = useCallback((e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  }, [handleSend]);

  const panelStyle: React.CSSProperties = {
    display: 'flex',
    flexDirection: 'column',
    height: '100%',
    padding: 0,
    overflow: 'hidden',
  };

  const headerStyle: React.CSSProperties = {
    display: 'flex',
    alignItems: 'center',
    gap: '8px',
    padding: '14px 16px 12px',
    borderBottom: `1px solid ${colors.border}`,
    flexShrink: 0,
  };

  const headerTitleStyle: React.CSSProperties = {
    color: colors.text,
    fontSize: '13px',
    fontWeight: 600,
    letterSpacing: '0.04em',
    textTransform: 'uppercase',
    fontFamily: colors.font,
  };

  const statusDotStyle: React.CSSProperties = {
    width: '6px',
    height: '6px',
    borderRadius: '50%',
    background: isAgentRunning ? '#FBBF24' : '#34D399',
    boxShadow: isAgentRunning
      ? '0 0 8px #FBBF24, 0 0 2px #FBBF24'
      : '0 0 8px #34D399, 0 0 2px #34D399',
    animation: isAgentRunning ? 'agentPulse 1s ease-in-out infinite' : 'none',
  };

  const headerActionButtonStyle = (enabled: boolean, danger: boolean = false): React.CSSProperties => ({
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    width: '26px',
    height: '26px',
    borderRadius: '6px',
    border: `1px solid ${enabled ? (danger ? colors.warning + '55' : colors.border) : colors.border}`,
    background: 'transparent',
    color: enabled ? (danger ? colors.warning : colors.muted) : colors.border,
    cursor: enabled ? 'pointer' : 'not-allowed',
    opacity: enabled ? 1 : 0.35,
    transition: 'background 0.15s, color 0.15s, border-color 0.15s, opacity 0.15s',
    flexShrink: 0,
    outline: 'none',
  });

  const messagesAreaStyle: React.CSSProperties = {
    flex: 1,
    overflowY: 'auto',
    padding: '14px 16px',
    scrollbarWidth: 'thin',
    scrollbarColor: `${colors.accentDim} transparent`,
  };

  const inputAreaStyle: React.CSSProperties = {
    borderTop: `1px solid ${colors.border}`,
    padding: '12px 16px',
    display: 'flex',
    gap: '10px',
    alignItems: 'flex-end',
    flexShrink: 0,
  };

  const textareaStyle: React.CSSProperties = {
    flex: 1,
    background: colors.inputBg,
    border: `1px solid ${colors.border}`,
    borderRadius: '8px',
    padding: '9px 12px',
    color: colors.text,
    fontSize: '13.5px',
    fontFamily: colors.font,
    resize: 'none',
    outline: 'none',
    lineHeight: '1.5',
    minHeight: '38px',
    maxHeight: '120px',
    overflowY: 'auto',
    opacity: isAgentRunning ? 0.5 : 1,
    transition: 'border-color 0.15s, opacity 0.2s, background 0.3s, color 0.3s',
  };

  const sendButtonStyle: React.CSSProperties = {
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    width: '38px',
    height: '38px',
    borderRadius: '8px',
    border: 'none',
    background: isAgentRunning || !inputValue.trim()
      ? colors.accentDim
      : colors.accent + '33',
    color: isAgentRunning || !inputValue.trim() ? colors.muted : colors.accent,
    cursor: isAgentRunning || !inputValue.trim() ? 'not-allowed' : 'pointer',
    transition: 'background 0.15s, color 0.15s',
    flexShrink: 0,
    outline: 'none',
  };

  const emptyStateStyle: React.CSSProperties = {
    display: 'flex',
    flexDirection: 'column',
    alignItems: 'center',
    justifyContent: 'center',
    height: '100%',
    color: colors.muted,
    fontSize: '13px',
    gap: '8px',
    fontFamily: colors.font,
  };

  return (
    <>
      <style>{`
        @keyframes agentPulse {
          0%, 100% { opacity: 1; }
          50% { opacity: 0.3; }
        }
        .chat-textarea:focus {
          border-color: ${colors.accent} !important;
        }
      `}</style>

      <div style={panelStyle}>
        <div style={headerStyle}>
          <span style={statusDotStyle} />
          <span style={headerTitleStyle}>Agent Chat</span>
          <div style={{ marginLeft: 'auto', display: 'flex', gap: '6px', alignItems: 'center' }}>
            <button
              style={headerActionButtonStyle(true)}
              onClick={onReset}
              title="Clear all messages"
              aria-label="Clear all messages"
            >
              <TrashIcon />
            </button>
            <button
              style={headerActionButtonStyle(isAgentRunning, true)}
              onClick={isAgentRunning ? onCancel : undefined}
              disabled={!isAgentRunning}
              title="Cancel agent"
              aria-label="Cancel agent"
            >
              <StopIcon />
            </button>
          </div>
        </div>

        <div className="chat-messages" style={messagesAreaStyle}>
          {messages.length === 0 ? (
            <div style={emptyStateStyle}>
              <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke={colors.accentDim} strokeWidth="1.5">
                <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z" />
              </svg>
              <span>Send a message to start</span>
            </div>
          ) : (
            messages.map(msg => (
              <MessageBubble key={msg.id} message={msg} />
            ))
          )}
          {isAgentRunning && <TypingIndicator />}
          <div ref={messagesEndRef} />
        </div>

        <div style={inputAreaStyle}>
          <textarea
            ref={inputRef}
            className="chat-textarea"
            style={textareaStyle}
            value={inputValue}
            onChange={e => setInputValue(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder={isAgentRunning ? 'Agent is running...' : 'Message the agent... (Enter to send)'}
            disabled={isAgentRunning}
            rows={1}
          />
          <button
            style={sendButtonStyle}
            onClick={handleSend}
            disabled={isAgentRunning || !inputValue.trim()}
            title="Send message"
            aria-label="Send message"
          >
            <SendIcon />
          </button>
        </div>
      </div>
    </>
  );
};

export default React.memo(ChatPanel);
