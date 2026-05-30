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
