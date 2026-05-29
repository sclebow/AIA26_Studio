import { useRef, useState } from "react";
import * as api from "../api/client.js";

export const EXAMPLE_LAYOUTS = [
  { id: "201", name: "City Apartment",  subtitle: "Thermal & Acoustic Conflicts" },
  { id: "202", name: "Studio Loft",     subtitle: "Acoustic & Olfactory Conflicts" },
  { id: "203", name: "Family Villa",    subtitle: "Multi-Sense Conflicts" },
];

export default function LayoutPicker({ layoutId, onSelect, onUpload }) {
  const [open, setOpen]         = useState(false);
  const [uploading, setUploading] = useState(false);
  const fileRef = useRef(null);

  const current = EXAMPLE_LAYOUTS.find((l) => String(layoutId).includes(l.id));

  const pick = async (id) => {
    setOpen(false);
    try {
      await api.selectLayout(id);
      onSelect && onSelect(id);
    } catch (err) {
      console.error("layout select failed", err);
    }
  };

  const handleFile = async (e) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setUploading(true);
    setOpen(false);
    try {
      const data = await api.uploadLayout(file);
      if (data.ok) onUpload && onUpload(data.layout_id, data.name);
    } catch (err) {
      console.error("layout upload failed", err);
    } finally {
      setUploading(false);
      e.target.value = "";
    }
  };

  return (
    <div className="layout-picker">
      <button
        className={"lp-trigger" + (open ? " open" : "")}
        onClick={() => setOpen((o) => !o)}
        title="switch layout"
      >
        <span className="lp-dot" />
        <span className="lp-name">
          {uploading ? "uploading…" : current ? current.name : layoutId ? `layout ${layoutId}` : "select layout"}
        </span>
        <span className="lp-caret">▾</span>
      </button>

      {open && (
        <div className="lp-dropdown">
          <div className="lp-section-label">example layouts</div>
          {EXAMPLE_LAYOUTS.map((l) => (
            <button
              key={l.id}
              className={"lp-option" + (current?.id === l.id ? " selected" : "")}
              onClick={() => pick(l.id)}
            >
              <span className="lp-option-name">{l.name}</span>
              <span className="lp-option-sub">{l.subtitle}</span>
            </button>
          ))}

          <div className="lp-divider" />
          <button
            className="lp-option lp-upload-btn"
            onClick={() => fileRef.current?.click()}
          >
            <span className="lp-option-name">↑ upload layout.json</span>
            <span className="lp-option-sub">your own layout file</span>
          </button>
          <input
            ref={fileRef}
            type="file"
            accept=".json"
            style={{ display: "none" }}
            onChange={handleFile}
          />
        </div>
      )}
    </div>
  );
}
