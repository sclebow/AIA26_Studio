// Selectors for a turn's JSON blobs. A "turn" carries its analysis as JSON
// strings (scores_json, suggestions_json, conflicts_json); these decode that
// shape in ONE place instead of re-parsing and reaching into `.rooms.find(…)`
// across SensePlan, FocusCard, and the layout screen.
function parse(s) { try { return s ? JSON.parse(s) : null; } catch { return null; } }

export function roomScores(turn) {
  return parse(turn?.scores_json)?.rooms || [];
}

export function roomByName(turn, name) {
  return roomScores(turn).find((r) => r.roomName === name) || null;
}

export function suggestionsFor(turn, name) {
  return parse(turn?.suggestions_json)?.improvements?.find((r) => r.roomName === name)?.suggestions || [];
}

export function conflictCount(turn) {
  return parse(turn?.conflicts_json)?.flaggedRooms?.length || 0;
}

// Distil the (layout-wide) narrative into a few SHORT bullet points relevant to
// one room — the per-room FocusCard should not dump the whole interpretation.
// score_interpretation is room-sectioned ("Room\n- sense: …"); we pull that
// room's bullets, then add any conflict-reasoning sentences that name the room.
export function narrativeBullets(turn, roomName) {
  if (!roomName) return [];
  const out = [];
  const has = (s) => s.toLowerCase().includes(roomName.toLowerCase());

  const interp = turn?.score_interpretation || "";
  if (interp) {
    let inRoom = false;
    for (const raw of interp.split(/\r?\n/)) {
      const line = raw.trim();
      if (!line) continue;
      const isBullet = /^[-•*]\s+/.test(line);
      if (!isBullet) { inRoom = has(line); continue; }   // heading line
      if (inRoom) out.push(line.replace(/^[-•*]\s+/, ""));
    }
    // Fallback: no structured per-room block — take sentences naming the room.
    if (!out.length) {
      interp.split(/(?<=[.!?])\s+/).forEach((s) => { if (has(s) && s.trim()) out.push(s.trim()); });
    }
  }

  const cr = turn?.conflict_reasoning || "";
  if (cr) cr.split(/(?<=[.!?])\s+/).forEach((s) => { if (has(s) && s.trim()) out.push(s.trim()); });

  const seen = new Set();
  return out.filter((b) => { const k = b.toLowerCase(); if (seen.has(k)) return false; seen.add(k); return true; }).slice(0, 6);
}
