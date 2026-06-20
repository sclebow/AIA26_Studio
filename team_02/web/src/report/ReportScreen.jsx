import { useCallback, useEffect, useRef, useState } from "react";
import * as api from "../api/client.js";
import ReportHeader from "./ReportHeader.jsx";
import ReportPersonaHeader from "./ReportPersonaHeader.jsx";
import DwellingStory from "./DwellingStory.jsx";
import RoomReportCard from "./RoomReportCard.jsx";
import { exportReportPng } from "./exportReportPng.js";
import { exportBundle } from "./exportBundle.js";

/*
 * ReportScreen — Act 3. The deliverable: a dwelling-level ripple story, then every
 * room as a score→prompt→image loop. Assembles from /api/report (per-room scores +
 * the prompts those scores generate, cheap, no images) and renders images on demand
 * via /api/render-room — featured rooms (worst / edited) eagerly, the rest on expand.
 */
export default function ReportScreen({ turn, persona, layoutId, onBack }) {
  const [report, setReport] = useState({ loading: true, data: null, error: null });
  const [images, setImages] = useState({});   // roomName -> {status, url, prompt, error}
  const [pngBusy, setPngBusy] = useState(false);
  const contentRef = useRef(null);

  const requestRender = useCallback((name, force = false) => {
    setImages((prev) => {
      const cur = prev[name];
      if (!force && cur && (cur.status === "loading" || cur.status === "done")) return prev;
      return { ...prev, [name]: { status: "loading", url: cur?.url, prompt: cur?.prompt, error: null } };
    });
    api.renderRoom(name, force)
      .then((d) => setImages((prev) => ({
        ...prev,
        [name]: d.ok
          ? { status: "done", url: d.image_base64, prompt: d.prompt, error: null }
          : { status: "error", error: d.error || "render failed" },
      })))
      .catch((e) => setImages((prev) => ({ ...prev, [name]: { status: "error", error: String(e.message || e) } })));
  }, []);

  useEffect(() => {
    let alive = true;
    api.getReport()
      .then((d) => {
        if (!alive) return;
        if (d.ok) {
          setReport({ loading: false, data: d, error: null });
          (d.featured || []).forEach((n) => requestRender(n));
        } else {
          setReport({ loading: false, data: null, error: d.error || "could not build the report" });
        }
      })
      .catch((e) => { if (alive) setReport({ loading: false, data: null, error: String(e.message || e) }); });
    return () => { alive = false; };
  }, [requestRender]);

  const rooms = report.data?.rooms || [];
  const featured = new Set(report.data?.featured || []);
  const moodboardUrls = report.data?.moodboard_urls || [];

  const onExportPng = async () => {
    if (!contentRef.current) return;
    setPngBusy(true);
    try { await exportReportPng(contentRef.current, `sensi-report-${layoutId || "layout"}.png`); }
    finally { setPngBusy(false); }
  };
  const onExportJson = () => exportBundle({ turn, rooms, layoutId, persona, moodboardUrls });

  return (
    <div className="report-screen">
      <ReportHeader onBack={onBack} onExportPng={onExportPng} onExportJson={onExportJson} busy={pngBusy} />
      <div className="report-scroll">
        <div className="report-content" ref={contentRef}>
          {report.loading && <div className="report-empty">composing your report…</div>}
          {report.error && <div className="report-empty">{report.error}</div>}
          {report.data && (
            <>
              <ReportPersonaHeader persona={persona} moodboardUrls={moodboardUrls} />
              <DwellingStory turn={turn} />
              <div className="report-rooms">
                {rooms.map((room) => (
                  <RoomReportCard
                    key={room.room_name}
                    room={room}
                    turn={turn}
                    persona={persona}
                    img={images[room.room_name]}
                    defaultOpen={featured.has(room.room_name)}
                    onRequestRender={requestRender}
                  />
                ))}
              </div>
              <div className="report-signature">✦ the vision · {layoutId || "your layout"} · read by sensi</div>
            </>
          )}
        </div>
      </div>
    </div>
  );
}
