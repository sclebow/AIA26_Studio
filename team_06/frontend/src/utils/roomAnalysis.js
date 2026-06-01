/**
 * roomAnalysis.js
 *
 * Utility functions for analysing and visualising room attributes.
 * Designed to be extended as new analysis modes are added (e.g. noise, energy).
 *
 * Current modes: 'layout' (program colour) | 'daylight' (DA value → heat map)
 */

// ─── Daylight palette ─────────────────────────────────────────────────────────
// 6-stop ramp: cool blues/teals (low DA) → yellow → orange → red (high DA).
// Thresholds are upper bounds of each band (scale: 0 – 0.6 DA).

export const DAYLIGHT_PALETTE = [
  { max: 0.10, color: '#1A3A5C', label: '< 10%' },
  { max: 0.20, color: '#2272B4', label: '10 – 20%' },
  { max: 0.35, color: '#00B4C6', label: '20 – 35%' },
  { max: 0.45, color: '#F0D050', label: '35 – 45%' },
  { max: 0.55, color: '#F5A020', label: '45 – 55%' },
  { max: Infinity, color: '#D94020', label: '> 55%' },
]

/**
 * Returns the palette hex colour for a given Daylight Autonomy value (0–1).
 * @param {number} value  DA value
 * @returns {string}      hex colour string
 */
export function getDaylightColor(value) {
  for (const stop of DAYLIGHT_PALETTE) {
    if (value <= stop.max) return stop.color
  }
  return DAYLIGHT_PALETTE[DAYLIGHT_PALETTE.length - 1].color
}

/**
 * Formats a DA value as a display string.
 * @param {number} value
 * @returns {string}  e.g. "0.42 DA"
 */
export function formatDaylight(value) {
  if (value == null) return '–'
  return `${value.toFixed(2)} DA`
}

// ─── Layout (program) palette ─────────────────────────────────────────────────
// Keyed by `attributes.program` string.

export const PROGRAM_COLORS = {
  bed:     '#4A7CA8',
  bath:    '#C8F4F0',
  kitchen: '#00C7D4',
  living:  '#009FA6',
  foyer:   '#0082C2',
  study:   '#5A8FAF',
  extra:   '#7A8FA3',
}

/**
 * Returns the fill colour for a room given the current view mode.
 * Extend here when new analysis layers are added.
 *
 * @param {object} room       room object with `attributes`
 * @param {'layout'|'daylight'} viewMode
 * @returns {string}          hex colour
 */
export function getRoomColor(room, viewMode) {
  if (viewMode === 'daylight') {
    return getDaylightColor(room.attributes?.daylight ?? 0)
  }
  return PROGRAM_COLORS[room.attributes?.program] ?? '#ddd'
}

/**
 * Returns the secondary label text (below room name) for a given view mode.
 *
 * @param {object} room
 * @param {'layout'|'daylight'} viewMode
 * @returns {string}
 */
export function getRoomSecondaryLabel(room, viewMode) {
  if (viewMode === 'daylight') {
    return formatDaylight(room.attributes?.daylight)
  }
  const area = room.attributes?.area
  return area != null ? `${area.toFixed(1)} m²` : ''
}
