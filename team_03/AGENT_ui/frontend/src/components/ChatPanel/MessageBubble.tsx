import React from 'react';
import { useTheme } from '../common/ThemeToggle';
import ToolCallCard, { ToolCallCardProps } from './ToolCallCard';

export interface ToolCall extends ToolCallCardProps {}

export interface Message {
  id: string;
  role: 'user' | 'agent';
  content: string;
  timestamp: number;
  toolCalls?: ToolCall[];
}

export interface MessageBubbleProps {
  message: Message;
}

const UserIcon: React.FC = () => (
  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2" />
    <circle cx="12" cy="7" r="4" />
  </svg>
);

const AgentIcon: React.FC = () => (
  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <rect x="2" y="7" width="20" height="14" rx="2" />
    <path d="M16 7V5a2 2 0 0 0-2-2h-4a2 2 0 0 0-2 2v2" />
    <line x1="12" y1="12" x2="12" y2="12" strokeWidth="3" />
    <path d="M8 12h.01M16 12h.01" strokeWidth="3" />
  </svg>
);

const formatTimestamp = (ts: number): string => {
  const d = new Date(ts);
  const h = d.getHours().toString().padStart(2, '0');
  const m = d.getMinutes().toString().padStart(2, '0');
  return `${h}:${m}`;
};

const MessageBubble: React.FC<MessageBubbleProps> = ({ message }) => {
  const { colors, theme } = useTheme();
  const isDark = theme === 'dark';
  const isUser = message.role === 'user';

  const wrapperStyle: React.CSSProperties = {
    display: 'flex',
    flexDirection: isUser ? 'row-reverse' : 'row',
    alignItems: 'flex-start',
    gap: '10px',
    marginBottom: '14px',
    fontFamily: colors.font,
  };

  const iconWrapperStyle: React.CSSProperties = {
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    width: '30px',
    height: '30px',
    borderRadius: '50%',
    flexShrink: 0,
    background: isUser
      ? colors.accentDim
      : (isDark ? 'rgba(255, 255, 255, 0.05)' : 'rgba(0, 0, 0, 0.05)'),
    border: isUser
      ? `1px solid ${colors.accent}66`
      : `1px solid ${isDark ? 'rgba(255, 255, 255, 0.08)' : 'rgba(0, 0, 0, 0.08)'}`,
    color: isUser ? colors.accent : colors.muted,
    marginTop: '2px',
  };

  const bubbleStyle: React.CSSProperties = {
    maxWidth: '75%',
    background: isUser
      ? colors.accentDim
      : (isDark ? 'rgba(255, 255, 255, 0.04)' : 'rgba(0, 0, 0, 0.03)'),
    border: isUser
      ? `1px solid ${colors.accent}4d`
      : `1px solid ${isDark ? 'rgba(255, 255, 255, 0.07)' : 'rgba(0, 0, 0, 0.07)'}`,
    borderRadius: isUser ? '12px 4px 12px 12px' : '4px 12px 12px 12px',
    padding: '10px 14px',
  };

  const contentStyle: React.CSSProperties = {
    color: colors.text,
    fontSize: '13.5px',
    lineHeight: '1.55',
    whiteSpace: 'pre-wrap',
    wordBreak: 'break-word',
  };

  const timestampStyle: React.CSSProperties = {
    color: colors.muted,
    fontSize: '10px',
    marginTop: '6px',
    textAlign: isUser ? 'right' : 'left',
  };

  return (
    <div style={wrapperStyle}>
      <div style={iconWrapperStyle}>
        {isUser ? <UserIcon /> : <AgentIcon />}
      </div>
      <div style={bubbleStyle}>
        <div style={contentStyle}>{message.content}</div>
        {message.toolCalls && message.toolCalls.length > 0 && (
          <div style={{ marginTop: '8px' }}>
            {message.toolCalls.map((tc, i) => (
              <ToolCallCard
                key={`${tc.name}-${i}`}
                name={tc.name}
                status={tc.status}
                args={tc.args}
                result={tc.result}
              />
            ))}
          </div>
        )}
        <div style={timestampStyle}>{formatTimestamp(message.timestamp)}</div>
      </div>
    </div>
  );
};

export default React.memo(MessageBubble);
