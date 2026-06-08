import React, { useState, useCallback } from 'react';
import { useTheme } from '../common/ThemeToggle';
import type { CheckpointState } from '../../hooks/useAgentState';

export interface ChatOptionsPanelProps {
  checkpoint: CheckpointState | null;
  onDecision: (value: string) => void;
}


const MONO = '"Share Tech Mono", "SF Mono", "Fira Code", ui-monospace, monospace';

const sectionLabel: (color: string) => React.CSSProperties = (color) => ({
  fontSize: 10,
  fontWeight: 700,
  letterSpacing: '0.16em',
  textTransform: 'uppercase',
  color,
  opacity: 0.85,
  margin: '0 0 6px',
  fontFamily: MONO,
});

const ChatOptionsPanel: React.FC<ChatOptionsPanelProps> = ({ checkpoint, onDecision }) => {
  const { colors, theme } = useTheme();
  const isDark = theme === 'dark';
  const [ruleText, setRuleText] = useState('');

  const awaiting = !!checkpoint;

  // Score delta vs the previous checkpoint (mirrors the terminal's ▲/▼).
  const delta = (checkpoint?.score != null && checkpoint?.prevScore != null)
    ? checkpoint.score - checkpoint.prevScore
    : null;

  const addRule = useCallback(() => {
    const t = ruleText.trim();
    if (!t) return;
    onDecision(`rule: ${t}`);
    setRuleText('');
  }, [ruleText, onDecision]);

  const chipStyle = (accent = false): React.CSSProperties => ({
    display: 'block',
    width: '100%',
    textAlign: 'left',
    padding: '7px 9px',
    marginBottom: 5,
    borderRadius: 7,
    border: `1px solid ${accent ? colors.accent + '66' : colors.border}`,
    background: accent ? colors.accent + '1f' : (isDark ? 'rgba(255,255,255,0.03)' : 'rgba(0,0,0,0.02)'),
    color: accent ? colors.accent : colors.text,
    fontSize: 10,
    lineHeight: 1.35,
    letterSpacing: '0.02em',
    cursor: awaiting ? 'pointer' : 'not-allowed',
    opacity: awaiting ? 1 : 0.4,
    fontFamily: MONO,
    transition: 'background 0.15s, border-color 0.15s',
  });

  const containerStyle: React.CSSProperties = {
    width: 208,
    flexShrink: 0,
    borderLeft: `1px solid ${colors.border}`,
    background: isDark ? 'rgba(15,9,30,0.55)' : 'rgba(248,249,251,0.7)',
    backdropFilter: 'blur(8px)',
    WebkitBackdropFilter: 'blur(8px)',
    display: 'flex',
    flexDirection: 'column',
    overflowY: 'auto',
    padding: '12px 12px 16px',
  };

  return (
    <div style={containerStyle}>
      {/* Header + score */}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 10 }}>
        <span style={{ ...sectionLabel(colors.muted), margin: 0 }}>Options</span>
        {checkpoint?.score != null && (
          <span style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
            <span style={{
              fontFamily: MONO, fontSize: 10, fontWeight: 700,
              color: checkpoint.score >= 80 ? colors.success : checkpoint.score >= 50 ? '#FBBF24' : colors.error,
            }}>
              {Math.round(checkpoint.score)}/100{checkpoint.grade ? ` ${checkpoint.grade}` : ''}
            </span>
            {delta != null && Math.abs(delta) >= 0.05 && (
              <span style={{
                fontFamily: MONO, fontSize: 9, fontWeight: 700,
                color: delta > 0 ? colors.success : colors.error,
              }}>
                {delta > 0 ? `▲ +${delta.toFixed(1)}` : `▼ ${delta.toFixed(1)}`}
              </span>
            )}
          </span>
        )}
      </div>


      {!awaiting && (
        <div style={{ fontSize: 10, color: colors.muted, fontFamily: MONO, lineHeight: 1.5 }}>
          The agent's suggestions, memory rules and actions will appear here when it
          pauses for your decision.
        </div>
      )}

      {/* Suggestions */}
      {awaiting && checkpoint!.suggestions.length > 0 && (
        <div style={{ marginBottom: 14 }}>
          <div style={sectionLabel(colors.accent)}>Suggestions</div>
          {checkpoint!.suggestions.map(s => (
            <button key={s.key} style={chipStyle(true)} disabled={!awaiting}
              onClick={() => onDecision(s.key)} title={`Apply ${s.key}`}>
              <span style={{ opacity: 0.7, fontWeight: 700, marginRight: 6 }}>{s.key}</span>
              {s.label}
            </button>
          ))}
        </div>
      )}

      {/* Collision violations */}
      {awaiting && checkpoint!.violations.length > 0 && (
        <div style={{ marginBottom: 14 }}>
          <div style={sectionLabel(colors.error)}>Violations ({checkpoint!.violations.length})</div>
          {checkpoint!.violations.map((v, i) => (
            <div key={i} style={{
              display: 'flex', alignItems: 'flex-start', gap: 6, marginBottom: 4,
              fontSize: 9.5, color: colors.text, fontFamily: MONO, lineHeight: 1.3,
            }}>
              <span style={{ color: colors.error, flexShrink: 0 }}>–</span>
              <span style={{ flex: 1 }}>{v}</span>
            </div>
          ))}
        </div>
      )}

      {/* Furniture changes */}
      {awaiting && checkpoint!.changes.length > 0 && (
        <div style={{ marginBottom: 14 }}>
          <div style={sectionLabel(colors.accent)}>Changes ({checkpoint!.changes.length})</div>
          {checkpoint!.changes.map((c, i) => (
            <div key={i} style={{
              display: 'flex', alignItems: 'flex-start', gap: 6, marginBottom: 4,
              fontSize: 9.5, color: colors.text, fontFamily: MONO, lineHeight: 1.3,
            }}>
              <span style={{
                flexShrink: 0, fontWeight: 700,
                color: c.action === 'ADDED' ? colors.success : '#FBBF24',
              }}>{c.action}</span>
              <span style={{ flex: 1 }}>{c.text}</span>
            </div>
          ))}
        </div>
      )}

      {/* Door changes */}
      {awaiting && checkpoint!.doorChanges.length > 0 && (
        <div style={{ marginBottom: 14 }}>
          <div style={sectionLabel('#FBBF24')}>Door changes</div>
          {checkpoint!.doorChanges.map((d, i) => (
            <div key={i} style={{
              fontSize: 9.5, color: colors.text, fontFamily: MONO, lineHeight: 1.3, marginBottom: 4,
            }}>{d}</div>
          ))}
        </div>
      )}

      {/* Memory */}
      {awaiting && (
        <div style={{ marginBottom: 14 }}>
          <div style={sectionLabel(colors.accent)}>Memory rules</div>
          {checkpoint!.rules.length === 0 && (
            <div style={{ fontSize: 10, color: colors.muted, fontFamily: MONO, marginBottom: 6 }}>
              (no rules saved)
            </div>
          )}
          {checkpoint!.rules.map((r, i) => (
            <div key={i} style={{
              display: 'flex', alignItems: 'flex-start', gap: 6, marginBottom: 5,
              fontSize: 10, color: colors.text, fontFamily: MONO, lineHeight: 1.35,
            }}>
              <span style={{ color: colors.accent, flexShrink: 0 }}>{i + 1}.</span>
              <span style={{ flex: 1 }}>{r}</span>
              <button
                onClick={() => onDecision(`forget: ${i + 1}`)}
                title="Forget this rule"
                style={{
                  flexShrink: 0, background: 'none', border: 'none', cursor: 'pointer',
                  color: colors.muted, fontSize: 12, lineHeight: 1, padding: '0 2px',
                }}
              >×</button>
            </div>
          ))}
          <div style={{ display: 'flex', gap: 5, marginTop: 6 }}>
            <input
              value={ruleText}
              onChange={e => setRuleText(e.target.value)}
              onKeyDown={e => { if (e.key === 'Enter') addRule(); }}
              placeholder="add a rule…"
              style={{
                flex: 1, minWidth: 0, background: colors.inputBg,
                border: `1px solid ${colors.border}`, borderRadius: 6,
                padding: '5px 7px', color: colors.text, fontSize: 10, fontFamily: MONO,
                outline: 'none',
              }}
            />
            <button onClick={addRule} title="Save rule"
              style={{
                flexShrink: 0, border: `1px solid ${colors.accent}55`, borderRadius: 6,
                background: colors.accent + '1f', color: colors.accent, cursor: 'pointer',
                fontSize: 12, padding: '0 8px', fontFamily: MONO,
              }}>+</button>
          </div>
        </div>
      )}

      {/* Actions */}
      {awaiting && (
        <div>
          <div style={sectionLabel(colors.accent)}>Actions</div>
          {checkpoint!.actions.yes && (
            <button style={chipStyle(false)} onClick={() => onDecision('yes')}>▸ Yes — next zone</button>
          )}
          {checkpoint!.actions.approve && (
            <button style={chipStyle(false)} onClick={() => onDecision('approve')}>✓ Approve layout</button>
          )}
          {checkpoint!.actions.end && (
            <button style={chipStyle(false)} onClick={() => onDecision('end')}>■ End &amp; save</button>
          )}
        </div>
      )}
    </div>
  );
};

export default React.memo(ChatOptionsPanel);
