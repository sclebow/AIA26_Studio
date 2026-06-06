import React, { useRef, useEffect, useState, useCallback } from 'react';
import { useTheme } from '../common/ThemeToggle';
import MessageBubble, { Message } from './MessageBubble';
import ChatOptionsPanel from './ChatOptionsPanel';
import type { CheckpointState } from '../../hooks/useAgentState';

export type { Message };

export interface ChatPanelProps {
  messages: Message[];
  onSend: (text: string) => void;
  isAgentRunning: boolean;
  onReset: () => void;
  onCancel: () => void;
  checkpoint?: CheckpointState | null;
  onDecision?: (value: string) => void;
  statusText?: string | null;
  ws: { send: (data: any) => void; subscribe: (cb: (msg: any) => void) => () => void };
}

const TypingIndicator: React.FC<{ statusText?: string | null }> = ({ statusText }) => {
  const { colors } = useTheme();
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 3, padding: '8px 0 4px 8px' }}>
      <style>{`
        @keyframes typingBounce {
          0%, 80%, 100% { transform: translateY(0); opacity: 0.4; }
          40% { transform: translateY(-4px); opacity: 1; }
        }
        @keyframes statusFade { from { opacity: 0; } to { opacity: 1; } }
      `}</style>
      <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
        {[0, 1, 2].map(i => (
          <span key={i} style={{
            display: 'inline-block', width: 6, height: 6, borderRadius: '50%',
            background: colors.accent,
            animation: `typingBounce 1.2s ease-in-out ${i * 0.2}s infinite`,
          }} />
        ))}
        <span style={{ color: colors.muted, fontSize: 12, marginLeft: 4, fontFamily: colors.font }}>
          Agent is thinking
        </span>
      </div>
      {statusText && (
        <span key={statusText} style={{
          color: colors.accent, fontSize: 12, marginLeft: 8,
          fontFamily: colors.font, opacity: 0.85, fontStyle: 'italic',
          animation: 'statusFade 0.3s ease',
        }}>
          {statusText}
        </span>
      )}
    </div>
  );
};

const SendIcon = () => (
  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <line x1="22" y1="2" x2="11" y2="13" /><polygon points="22 2 15 22 11 13 2 9 22 2" />
  </svg>
);

const TrashIcon = () => (
  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <polyline points="3 6 5 6 21 6" />
    <path d="M19 6l-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6" />
    <path d="M10 11v6M14 11v6M9 6V4a1 1 0 0 1 1-1h4a1 1 0 0 1 1 1v2" />
  </svg>
);

const StopIcon = () => (
  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <rect x="3" y="3" width="18" height="18" rx="2" ry="2" />
  </svg>
);

type ChatMode = 'agent' | 'chat';
type ModelKey = 'haiku' | 'sonnet';

interface PureChatMessage {
  id: string;
  role: 'user' | 'assistant';
  content: string;
}

const ChatPanel: React.FC<ChatPanelProps> = ({
  messages, onSend, isAgentRunning, onReset, onCancel,
  checkpoint, onDecision, statusText, ws,
}) => {
  const { colors, theme } = useTheme();
  const isDark = theme === 'dark';
  const [inputValue, setInputValue] = useState('');
  const [chatMode, setChatMode] = useState<ChatMode>('agent');
  const [modelKey, setModelKey] = useState<ModelKey>('haiku');
  const [pureChatMessages, setPureChatMessages] = useState<PureChatMessage[]>([]);
  const [pureLoading, setPureLoading] = useState(false);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);

  // Subscribe to WebSocket messages for pure_chat_response + model_switch_ack
  useEffect(() => {
    return ws.subscribe((msg: any) => {
      if (!msg) return;
      if (msg.type === 'pure_chat_response') {
        setPureLoading(false);
        setPureChatMessages(prev => [...prev, {
          id: Date.now().toString(),
          role: 'assistant',
          content: msg.content,
        }]);
      }
      if (msg.type === 'model_switch_ack' && msg.status === 'ok') {
        setModelKey(msg.model as ModelKey);
      }
    });
  }, []);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, pureChatMessages, isAgentRunning, pureLoading]);

  const handleModelSwitch = useCallback((key: ModelKey) => {
    setModelKey(key);
    ws.send({ type: 'model_switch', model: key });
  }, [ws]);

  const handleModeSwitch = useCallback((mode: ChatMode) => {
    setChatMode(mode);
    setInputValue('');
  }, []);

  const handleSend = useCallback(() => {
    const text = inputValue.trim();
    if (!text) return;

    if (chatMode === 'agent') {
      if (isAgentRunning) return;
      onSend(text);
    } else {
      // Pure chat mode
      const userMsg: PureChatMessage = {
        id: Date.now().toString(),
        role: 'user',
        content: text,
      };
      setPureChatMessages(prev => {
        const updated = [...prev, userMsg];
        // Send history (excluding the new message) + new content
        ws.send({
          type: 'pure_chat',
          content: text,
          history: prev.map(m => ({ role: m.role, content: m.content })),
        });
        return updated;
      });
      setPureLoading(true);
    }
    setInputValue('');
  }, [inputValue, chatMode, isAgentRunning, onSend, ws]);

  const handleKeyDown = useCallback((e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  }, [handleSend]);

  const handleReset = useCallback(() => {
    if (chatMode === 'agent') onReset();
    else setPureChatMessages([]);
  }, [chatMode, onReset]);

  const isDisabled = chatMode === 'agent' ? isAgentRunning : pureLoading;

  // ── Styles ────────────────────────────────────────────────────────────────

  const pill = (active: boolean, danger = false): React.CSSProperties => ({
    padding: '3px 10px', borderRadius: 6, border: 'none',
    fontSize: 10, fontWeight: 600, letterSpacing: '0.06em',
    textTransform: 'uppercase', cursor: 'pointer',
    fontFamily: colors.font, transition: 'all 0.15s',
    background: active
      ? (danger ? colors.error + '22' : colors.accentDim)
      : 'transparent',
    color: active
      ? (danger ? colors.error : colors.accent)
      : colors.muted,
    outline: 'none',
  });

  const modelPill = (active: boolean): React.CSSProperties => ({
    padding: '2px 8px', borderRadius: 4,
    border: `1px solid ${active ? colors.accent + '55' : colors.border}`,
    fontSize: 9, fontWeight: 700, letterSpacing: '0.08em',
    textTransform: 'uppercase', cursor: 'pointer',
    fontFamily: colors.font, transition: 'all 0.15s',
    background: active ? colors.accentDim : 'transparent',
    color: active ? colors.accent : colors.muted,
    outline: 'none',
  });

  const headerActionBtn = (enabled: boolean, danger = false): React.CSSProperties => ({
    display: 'flex', alignItems: 'center', justifyContent: 'center',
    width: 20, height: 20, borderRadius: 5,
    border: `1px solid ${enabled ? (danger ? colors.warning + '55' : colors.border) : colors.border}`,
    background: 'transparent',
    color: enabled ? (danger ? colors.warning : colors.muted) : colors.border,
    cursor: enabled ? 'pointer' : 'not-allowed',
    opacity: enabled ? 1 : 0.35,
    transition: 'all 0.15s', flexShrink: 0, outline: 'none',
  });

  return (
    <>
      <style>{`
        @keyframes agentPulse { 0%, 100% { opacity: 1; } 50% { opacity: 0.3; } }
        .chat-textarea:focus { border-color: ${colors.accent} !important; }
      `}</style>

      <div style={{ display: 'flex', flexDirection: 'column', height: '100%', overflow: 'hidden' }}>

        {/* ── HEADER ──────────────────────────────────────────────────── */}
        <div style={{
          display: 'flex', alignItems: 'center', gap: 8,
          padding: '7px 12px', borderBottom: `1px solid ${colors.border}`, flexShrink: 0,
        }}>
          {/* Status dot */}
          <span style={{
            width: 6, height: 6, borderRadius: '50%', flexShrink: 0,
            background: isAgentRunning ? '#FBBF24' : '#34D399',
            boxShadow: isAgentRunning ? '0 0 8px #FBBF24' : '0 0 8px #34D399',
            animation: isAgentRunning ? 'agentPulse 1s ease-in-out infinite' : 'none',
          }} />

          {/* Mode toggle — Agent | Chat */}
          <div style={{
            display: 'flex', gap: 2,
            background: isDark ? 'rgba(255,255,255,0.04)' : 'rgba(0,0,0,0.04)',
            borderRadius: 8, padding: 2,
            border: `1px solid ${colors.border}`,
          }}>
            {(['agent', 'chat'] as ChatMode[]).map(m => (
              <button key={m} onClick={() => handleModeSwitch(m)} style={pill(chatMode === m)}>
                {m === 'agent' ? 'Agent' : 'Chat'}
              </button>
            ))}
          </div>

          {/* Right actions */}
          <div style={{ marginLeft: 'auto', display: 'flex', gap: 6, alignItems: 'center' }}>
            <button style={headerActionBtn(true)} onClick={handleReset} title="Clear messages">
              <TrashIcon />
            </button>
            {chatMode === 'agent' && (
              <button
                style={headerActionBtn(isAgentRunning, true)}
                onClick={isAgentRunning ? onCancel : undefined}
                disabled={!isAgentRunning}
                title="Cancel agent"
              >
                <StopIcon />
              </button>
            )}
          </div>
        </div>

        {/* ── BODY ────────────────────────────────────────────────────── */}
        <div style={{ flex: 1, minHeight: 0, display: 'flex', flexDirection: 'row' }}>

          {/* Conversation column */}
          <div style={{ flex: 1, minWidth: 0, display: 'flex', flexDirection: 'column' }}>

            {/* Messages */}
            <div style={{
              flex: 1, overflowY: 'auto', padding: '14px 16px',
              scrollbarWidth: 'thin', scrollbarColor: `${colors.accentDim} transparent`,
            }}>
              {chatMode === 'agent' ? (
                <>
                  {messages.length === 0 ? (
                    <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', height: '100%', color: colors.muted, fontSize: 12, gap: 8, fontFamily: colors.font }}>
                      <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke={colors.accentDim} strokeWidth="1.5">
                        <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z" />
                      </svg>
                      <span>Send a message to start the workflow</span>
                    </div>
                  ) : (
                    messages.map(msg => <MessageBubble key={msg.id} message={msg} />)
                  )}
                  {isAgentRunning && <TypingIndicator statusText={statusText} />}
                </>
              ) : (
                <>
                  {pureChatMessages.length === 0 ? (
                    <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', height: '100%', color: colors.muted, fontSize: 12, gap: 8, fontFamily: colors.font }}>
                      <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke={colors.accentDim} strokeWidth="1.5">
                        <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z" />
                      </svg>
                      <span>Ask anything about your design</span>
                      <span style={{ fontSize: 10, opacity: 0.6 }}>No workflow runs in this mode</span>
                    </div>
                  ) : (
                    pureChatMessages.map(msg => (
                      <MessageBubble
                        key={msg.id}
                        message={{ id: msg.id, role: msg.role, content: msg.content, type: 'text' } as any}
                      />
                    ))
                  )}
                  {pureLoading && <TypingIndicator />}
                </>
              )}
              <div ref={messagesEndRef} />
            </div>

            {/* Model toggle + input area */}
            <div style={{ borderTop: `1px solid ${colors.border}`, flexShrink: 0 }}>

              {/* Model toggle strip */}
              <div style={{
                display: 'flex', alignItems: 'center', gap: 6,
                padding: '6px 16px 0',
              }}>
                <span style={{ fontSize: 9, color: colors.muted, letterSpacing: '0.08em', textTransform: 'uppercase', fontFamily: colors.font }}>
                  Model
                </span>
                <button onClick={() => handleModelSwitch('haiku')} style={modelPill(modelKey === 'haiku')}>
                  Haiku
                </button>
                <button onClick={() => handleModelSwitch('sonnet')} style={modelPill(modelKey === 'sonnet')}>
                  Sonnet
                </button>
                <span style={{ marginLeft: 'auto', fontSize: 9, color: colors.muted, opacity: 0.5, fontFamily: colors.font }}>
                  {modelKey === 'sonnet' ? 'Smarter · slower' : 'Faster · cheaper'}
                </span>
              </div>

              {/* Input row */}
              <div style={{ padding: '8px 16px 12px', display: 'flex', gap: 10, alignItems: 'flex-end' }}>
                <textarea
                  ref={inputRef}
                  className="chat-textarea"
                  style={{
                    flex: 1, background: colors.inputBg,
                    border: `1px solid ${colors.border}`, borderRadius: 8,
                    padding: '9px 12px', color: colors.text, fontSize: 12,
                    fontFamily: colors.font, resize: 'none', outline: 'none',
                    lineHeight: 1.5, minHeight: 38, maxHeight: 120, overflowY: 'auto',
                    opacity: isDisabled ? 0.5 : 1, transition: 'border-color 0.15s, opacity 0.2s',
                  }}
                  value={inputValue}
                  onChange={e => setInputValue(e.target.value)}
                  onKeyDown={handleKeyDown}
                  placeholder={
                    isDisabled
                      ? (chatMode === 'agent' ? 'Agent is running...' : 'Waiting for reply...')
                      : (chatMode === 'agent' ? 'Message the agent... (Enter to send)' : 'Ask anything... (Enter to send)')
                  }
                  disabled={isDisabled}
                  rows={1}
                />
                <button
                  style={{
                    display: 'flex', alignItems: 'center', justifyContent: 'center',
                    width: 38, height: 38, borderRadius: 8, border: 'none',
                    background: isDisabled || !inputValue.trim() ? colors.accentDim : colors.accent + '33',
                    color: isDisabled || !inputValue.trim() ? colors.muted : colors.accent,
                    cursor: isDisabled || !inputValue.trim() ? 'not-allowed' : 'pointer',
                    transition: 'all 0.15s', flexShrink: 0, outline: 'none',
                  }}
                  onClick={handleSend}
                  disabled={isDisabled || !inputValue.trim()}
                  title="Send"
                >
                  <SendIcon />
                </button>
              </div>
            </div>
          </div>

          {/* Options panel — agent mode only */}
          {chatMode === 'agent' && onDecision && (
            <ChatOptionsPanel checkpoint={checkpoint ?? null} onDecision={onDecision} />
          )}
        </div>
      </div>
    </>
  );
};

export default React.memo(ChatPanel);