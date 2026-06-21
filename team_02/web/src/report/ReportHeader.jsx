import SensiAvatar from "../components/SensiAvatar.jsx";

/*
 * ReportHeader — sticky top bar for the Report (Act 3). Carries the way back to
 * explore and the two exports (PNG snapshot of the report · JSON bundle).
 */
export default function ReportHeader({ onBack, onExportPng, onExportJson, busy }) {
  return (
    <div className="report-header">
      <div className="report-header-left">
        <SensiAvatar size={24} />
        <span className="top-bar-label">sensi</span>
        <span className="top-bar-sep">|</span>
        <span className="top-bar-act">the vision</span>
      </div>
      <div className="report-actions">
        <button className="report-back" onClick={onBack}>‹ back to explore</button>
        <button className="layer-pill" onClick={onExportPng} disabled={busy} title="export the report as a PNG image">⤓ image</button>
        <button className="layer-pill" onClick={onExportJson} title="download layout + scores + prompts as JSON">⤓ json</button>
      </div>
    </div>
  );
}
