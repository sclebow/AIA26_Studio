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

// ─── Persona palette ──────────────────────────────────────────────────────────
export const PERSONA_COLORS = ['#4A7CA8', '#F5A020', '#00C7D4', '#D94020', '#7A8FA3']

// ─── Time-of-day palette ────────────────────────────────────────────────────────
// 9 steps matching ROUTINE_TIMES (06:00–22:00), mirrored around midday.
export const TOD_COLORS = [
  '#4A7CA8',  // 06:00 bedroom blue
  '#7A8FA3',  // 08:00 bathroom cyan
  '#C8F4F0',  // 10:00 light yellow
  '#F5E68A',  // 12:00 peak yellow
  '#F0D050',  // 14:00 light yellow
  '#F5E68A',  // 16:00 bathroom cyan
  '#C8F4F0',  // 18:00 bedroom blue
  '#7A8FA3',  // 20:00 bedroom blue
  '#4A7CA8',  // 22:00 bedroom blue
]

export const DAYLIGHT_PALETTE = [
  { max: 0.5, color: '#4A7CA8' },
  { max: 1.0, color: '#7A8FA3' },
  { max: 1.5, color: '#C8F4F0' },
  { max: 2.0, color: '#F5E68A' },
  { max: 2.5, color: '#F0D050' },
  { max: 3.0, color: '#F5A020' },
  { max: Infinity, color: '#D94020' },
]

export function toNumericValue(value) {
  if (typeof value === 'number') return Number.isFinite(value) ? value : null
  if (typeof value === 'string' && value.trim()) {
    const parsed = Number(value)
    return Number.isFinite(parsed) ? parsed : null
  }
  return null
}

/**
 * Returns the palette hex colour for a given Daylight Autonomy value (0–1).
 * @param {number} value  DA value
 * @returns {string}      hex colour string
 */
export function getDaylightColor(value) {
  const numericValue = toNumericValue(value) ?? 0
  for (const stop of DAYLIGHT_PALETTE) {
    if (numericValue <= stop.max) return stop.color
  }
  return DAYLIGHT_PALETTE[DAYLIGHT_PALETTE.length - 1].color
}

/**
 * Formats a DA value as a display string.
 * @param {number} value
 * @returns {string}  e.g. "0.42 DA"
 */
export function formatDaylight(value) {
  const numericValue = toNumericValue(value)
  if (numericValue == null) return '–'
  return `${numericValue.toFixed(2)} DA`
}

const PROGRAM_LABELS = {
  bed: ['bedroom', 'bedrooms'],
  bath: ['bathroom', 'bathrooms'],
  living: ['living', 'living'],
  kitchen: ['kitchen', 'kitchens'],
  foyer: ['foyer', 'foyers'],
  extra: ['extra', 'extra'],
  study: ['study', 'studies'],
}

export function formatRoomProgram(program, count = null) {
  if (typeof program !== 'string' || !program.trim()) return ''
  const normalized = program.trim().toLowerCase()
  const [singular, plural] = PROGRAM_LABELS[normalized] ?? [normalized, `${normalized}s`]
  if (typeof count === 'number') {
    const label = count === 1 ? singular : plural
    return `${count} ${label}`
  }
  return singular
}

export function getRoomDisplayName(room) {
  const programLabel = formatRoomProgram(room?.attributes?.program)
  if (programLabel) return programLabel

  const rawName = room?.name
  return typeof rawName === 'string' ? rawName.trim().toLowerCase() : ''
}

// ─── Layout (program) palette ─────────────────────────────────────────────────
// Keyed by `attributes.program` string.

export const PROGRAM_COLORS = {
  bed:     '#0082c2ff',
  bath:    '#C8F4F0',
  living:  '#00e0cdff',
  foyer:   '#009fa6ff',
  extra:   '#00c7d4ff',
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
    return getDaylightColor(room.attributes?.daylight)
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
  if (viewMode === 'routine') return ''
  const area = toNumericValue(room.attributes?.area)
  return area != null ? `${area.toFixed(1)} m²` : ''
}
