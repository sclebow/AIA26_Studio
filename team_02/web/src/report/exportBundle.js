import * as api from "../api/client.js";

// JSON bundle export — the "real tool" artifact: the layout, its comfort scores,
// conflicts, suggestions, and the per-room render prompts, in one downloadable file.
// Pure client; layout comes from /api/layout, the analysis comes off the turn.
function parse(s) { try { return s ? JSON.parse(s) : null; } catch { return null; } }

export async function exportBundle({ turn, rooms = [], layoutId }) {
  let layout = null;
  try { const d = await api.getLayout(); layout = d?.layout || null; } catch { /* best effort */ }

  const bundle = {
    layoutId: layoutId || null,
    exportedAt: new Date().toISOString(),
    layout,
    scores: parse(turn?.scores_json),
    conflicts: parse(turn?.conflicts_json),
    suggestions: parse(turn?.suggestions_json),
    prompts: rooms.map((r) => ({
      room: r.room_name,
      room_type: r.room_type,
      overall_score: r.overall_score,
      comfort_scores: r.comfort_scores,
      prompt: r.prompt,
    })),
  };

  const blob = new Blob([JSON.stringify(bundle, null, 2)], { type: "application/json" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = `sensi-report-${layoutId || "layout"}.json`;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}
