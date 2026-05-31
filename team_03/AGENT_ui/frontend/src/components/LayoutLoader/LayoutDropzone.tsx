import React, { useState, useRef, useCallback } from 'react';
import { useTheme } from '../common/ThemeToggle';

export interface LayoutDropzoneProps {
  onUpload: (file: File) => void;
}

const LayoutDropzone: React.FC<LayoutDropzoneProps> = ({ onUpload }) => {
  const { colors } = useTheme();
  const [isDragOver, setIsDragOver] = useState(false);
  const [uploadedFileName, setUploadedFileName] = useState<string | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const processFile = useCallback((file: File) => {
    if (!file.name.endsWith('.json')) return;
    setUploadedFileName(file.name);
    onUpload(file);
  }, [onUpload]);

  const handleDrop = useCallback((e: React.DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    setIsDragOver(false);
    const file = e.dataTransfer.files?.[0];
    if (file) processFile(file);
  }, [processFile]);

  const handleClick = useCallback(() => { fileInputRef.current?.click(); }, []);

  const handleFileInput = useCallback((e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) processFile(file);
    e.target.value = '';
  }, [processFile]);

  const dropzoneStyle: React.CSSProperties = {
    display: 'flex',
    flexDirection: 'column',
    alignItems: 'center',
    justifyContent: 'center',
    gap: '8px',
    padding: '20px 16px',
    borderRadius: '8px',
    border: `1.5px dashed ${isDragOver ? colors.accent : colors.border}`,
    background: isDragOver ? colors.accentDim : 'transparent',
    cursor: 'pointer',
    transition: 'border-color 0.2s, background 0.2s, box-shadow 0.2s',
    boxShadow: isDragOver ? `0 0 16px ${colors.accentDim}, inset 0 0 12px ${colors.accentDim}` : 'none',
    fontFamily: colors.font,
    userSelect: 'none',
  };

  return (
    <div>
      <div
        style={dropzoneStyle}
        onDrop={handleDrop}
        onDragOver={e => { e.preventDefault(); setIsDragOver(true); }}
        onDragLeave={() => setIsDragOver(false)}
        onClick={handleClick}
        role="button"
        tabIndex={0}
        aria-label="Upload JSON layout file"
        onKeyDown={e => e.key === 'Enter' && handleClick()}
      >
        <svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke={isDragOver ? colors.accent : colors.muted} strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" style={{ transition: 'stroke 0.2s' }}>
          <polyline points="16 16 12 12 8 16" />
          <line x1="12" y1="12" x2="12" y2="21" />
          <path d="M20.39 18.39A5 5 0 0 0 18 9h-1.26A8 8 0 1 0 3 16.3" />
        </svg>
        <span style={{ color: isDragOver ? colors.accent : colors.muted, fontSize: '12px', transition: 'color 0.2s', textAlign: 'center' }}>
          {isDragOver ? 'Drop to upload' : 'Or drag & drop a JSON layout file'}
        </span>
        <span style={{ color: colors.muted, fontSize: '10px', opacity: 0.7, textAlign: 'center' }}>
          Accepts .json files only
        </span>
      </div>

      {uploadedFileName && (
        <div style={{
          display: 'flex',
          alignItems: 'center',
          gap: '6px',
          marginTop: '6px',
          padding: '4px 10px',
          borderRadius: '4px',
          background: `${colors.success}1a`,
          border: `1px solid ${colors.success}40`,
          color: colors.success,
          fontSize: '11px',
          fontFamily: '"SF Mono", "Fira Code", monospace',
        }}>
          <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke={colors.success} strokeWidth="3">
            <polyline points="20 6 9 17 4 12" />
          </svg>
          {uploadedFileName}
        </div>
      )}

      <input
        ref={fileInputRef}
        type="file"
        accept=".json"
        style={{ display: 'none' }}
        onChange={handleFileInput}
      />
    </div>
  );
};

export default React.memo(LayoutDropzone);
