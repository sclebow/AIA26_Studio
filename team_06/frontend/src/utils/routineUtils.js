// routineUtils.js — Canonical activity taxonomy + schedule derivation.
//
// Single source of truth for activity names. Both the frontend routine
// visualization and any future backend parser should agree on these keys.
//
// Canonical activities: sleeping | bathing | eating | cooking | working |
//                       studying | relaxing | exercising

// ---------------------------------------------------------------------------
// Normalization — maps any free-text variant → canonical key
// ---------------------------------------------------------------------------
const VARIANTS = {
  // sleeping
  sleep: 'sleeping', sleeping: 'sleeping',
  // bathing
  bath: 'bathing', bathing: 'bathing', shower: 'bathing', showering: 'bathing', washing: 'bathing',
  // eating
  eat: 'eating', eating: 'eating', dining: 'eating', breakfast: 'eating', lunch: 'eating', dinner: 'eating',
  // cooking
  cook: 'cooking', cooking: 'cooking', preparing: 'cooking',
  // working
  work: 'working', working: 'working', remote: 'working',
  // studying
  study: 'studying', studying: 'studying', reading: 'studying', learning: 'studying',
  // relaxing
  relax: 'relaxing', relaxing: 'relaxing', resting: 'relaxing', watching: 'relaxing', leisure: 'relaxing',
  // exercising
  exercise: 'exercising', exercising: 'exercising', workout: 'exercising', sport: 'exercising',
}

/**
 * Normalize a free-text activity string to a canonical key.
 * Returns null if unrecognized.
 * @param {string} raw
 * @returns {string|null}
 */
export function normalizeActivity(raw) {
  if (!raw) return null
  return VARIANTS[raw.trim().toLowerCase()] ?? null
}

// ---------------------------------------------------------------------------
// Activity → room program mapping
// ---------------------------------------------------------------------------
// Room programs match the keys in PROGRAM_COLORS (roomAnalysis.js):
//   bed | bath | kitchen | living | foyer | study | extra

const ACTIVITY_TO_PROGRAM = {
  sleeping:   'bed',
  bathing:    'bath',
  eating:     'kitchen',
  cooking:    'kitchen',
  working:    'study',
  studying:   'study',
  relaxing:   'living',
  exercising: null,   // no specific room type — skipped in visualization
}

/**
 * Map a canonical activity to a room program key.
 * Returns null if no room maps to this activity.
 * @param {string} canonical
 * @returns {string|null}
 */
export function activityToProgram(canonical) {
  return ACTIVITY_TO_PROGRAM[canonical] ?? null
}

/**
 * Given a raw activity string, return the room program or null.
 * Convenience: normalizeActivity + activityToProgram in one call.
 * @param {string} raw
 * @returns {string|null}
 */
export function rawActivityToProgram(raw) {
  const canonical = normalizeActivity(raw)
  if (!canonical) return null
  return activityToProgram(canonical)
}

// ---------------------------------------------------------------------------
// Default schedule — used when backend sends no routine
// ---------------------------------------------------------------------------
// Values are canonical activity keys.
export const DEFAULT_SCHEDULE = {
  morning:   ['sleeping', 'bathing', 'eating'],
  afternoon: ['working',  'eating',  'working'],
  evening:   ['cooking',  'relaxing', 'sleeping'],
}

// ---------------------------------------------------------------------------
// Schedule builder
// ---------------------------------------------------------------------------
/**
 * Build a per-slot sequence of room programs from a routine object.
 * Skips any activity that has no room mapping or whose program is not
 * present in the available rooms list.
 *
 * @param {Object} routine  - { morning: string[], afternoon: string[], evening: string[] }
 *                            Values may be raw or canonical activity strings.
 * @param {string[]} availablePrograms - programs that actually exist in parsedInput.rooms
 * @returns {{ morning: string[], afternoon: string[], evening: string[] }}
 */
export function buildProgramSchedule(routine, availablePrograms) {
  const available = new Set(availablePrograms)
  const resolve = (activities) =>
    activities
      .map(a => rawActivityToProgram(a) ?? activityToProgram(normalizeActivity(a)) ?? null)
      .filter(p => p !== null && available.has(p))

  return {
    morning:   resolve(routine.morning   ?? DEFAULT_SCHEDULE.morning),
    afternoon: resolve(routine.afternoon ?? DEFAULT_SCHEDULE.afternoon),
    evening:   resolve(routine.evening   ?? DEFAULT_SCHEDULE.evening),
  }
}
