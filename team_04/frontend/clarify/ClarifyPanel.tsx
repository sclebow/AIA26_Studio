/**
 * ClarifyPanel — renders the agent's structured clarification question as chips
 * and collects the user's answers.
 *
 * The backend pauses and returns a `ClarificationRequest` (summary + fields, each
 * with suggested chip `options`) when a placement-critical detail is missing —
 * building shape, preferred side, view side, size, use, count. The user picks
 * chips (or types a custom value where allowed); on submit we POST to
 * `/sessions/{id}/clarify`, then the caller resumes the design with a `/chat`
 * turn. This is the front-end half of the "agent asks back" loop.
 */
import { useState } from 'react';

import type { ClarificationAnswers, ClarificationField, ClarificationRequest } from '../api/types';

export interface ClarifyPanelProps {
  request: ClarificationRequest;
  onSubmit: (answers: ClarificationAnswers) => void | Promise<void>;
  submitting?: boolean;
}

const CRITICAL = '#c0392b';
const ACCENT = '#2980b9';

function FieldRow({
  field,
  value,
  onChange,
}: {
  field: ClarificationField;
  value: string | string[] | undefined;
  onChange: (v: string | string[]) => void;
}): JSX.Element {
  const selected = new Set(Array.isArray(value) ? value : value ? [value] : []);

  const toggle = (opt: string) => {
    if (field.multi) {
      const next = new Set(selected);
      next.has(opt) ? next.delete(opt) : next.add(opt);
      onChange([...next]);
    } else {
      onChange(opt);
    }
  };

  return (
    <div style={{ marginBottom: 12 }}>
      <div style={{ fontSize: 12, fontWeight: 600, color: '#2c3e50', marginBottom: 4 }}>
        {field.question}
        {field.critical && (
          <span style={{ color: CRITICAL, fontSize: 10, marginLeft: 6 }}>● required</span>
        )}
      </div>
      <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
        {field.options.map((opt) => {
          const on = selected.has(opt);
          return (
            <button
              key={opt}
              type="button"
              onClick={() => toggle(opt)}
              style={{
                padding: '3px 10px',
                borderRadius: 14,
                border: `1px solid ${on ? ACCENT : '#cdd5dd'}`,
                background: on ? ACCENT : '#fff',
                color: on ? '#fff' : '#34495e',
                fontSize: 11,
                cursor: 'pointer',
              }}
            >
              {opt}
            </button>
          );
        })}
        {field.allow_custom && (
          <input
            placeholder="custom…"
            onBlur={(e) => {
              const v = e.target.value.trim();
              if (v) (field.multi ? onChange([...selected, v]) : onChange(v));
            }}
            style={{
              padding: '3px 8px',
              borderRadius: 14,
              border: '1px dashed #cdd5dd',
              fontSize: 11,
              width: 90,
            }}
          />
        )}
      </div>
    </div>
  );
}

export function ClarifyPanel({ request, onSubmit, submitting = false }: ClarifyPanelProps): JSX.Element {
  const [answers, setAnswers] = useState<ClarificationAnswers>({});

  const setField = (key: string, v: string | string[]) =>
    setAnswers((prev) => ({ ...prev, [key]: v }));

  const missingCritical = request.fields.filter(
    (f) => f.critical && !answers[f.key]?.length,
  );
  const canSubmit = missingCritical.length === 0 && !submitting;

  return (
    <div
      style={{
        border: `2px solid ${ACCENT}`,
        borderRadius: 10,
        background: '#fff',
        padding: 14,
        maxWidth: 360,
        fontFamily: 'system-ui, sans-serif',
      }}
    >
      <div style={{ fontSize: 11, fontWeight: 700, letterSpacing: 0.5, color: ACCENT, marginBottom: 4 }}>
        ✋ THE AGENT NEEDS A FEW DETAILS
      </div>
      <div style={{ fontSize: 12, color: '#5d6d7e', marginBottom: 12 }}>{request.summary}</div>

      {request.fields.map((f) => (
        <FieldRow key={f.key} field={f} value={answers[f.key]} onChange={(v) => setField(f.key, v)} />
      ))}

      <button
        type="button"
        disabled={!canSubmit}
        onClick={() => void onSubmit(answers)}
        style={{
          marginTop: 6,
          width: '100%',
          padding: '7px 0',
          borderRadius: 8,
          border: 'none',
          background: canSubmit ? ACCENT : '#bdc8d2',
          color: '#fff',
          fontSize: 12,
          fontWeight: 600,
          cursor: canSubmit ? 'pointer' : 'not-allowed',
        }}
      >
        {submitting
          ? 'Submitting…'
          : missingCritical.length
            ? `Answer ${missingCritical.length} required field(s)`
            : 'Submit & continue'}
      </button>
    </div>
  );
}

export default ClarifyPanel;
