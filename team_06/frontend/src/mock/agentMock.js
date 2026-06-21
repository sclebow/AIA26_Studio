/**
 * agentMock.js
 *
 * Simulates the backend agent. All functions here return an AgentResponse:
 *
 *   {
 *     message:          string,       // agent's reply text
 *     suggestedPrompts: string[],     // optional follow-up chips
 *     parsedInput: {                  // full current understanding — null = no change
 *       households: [{ name, relationship? }],
 *       activities:  [{ type, time? }],
 *       rooms:       [{ id, name, size? }],
 *       brief:       string
 *     } | null,
 *     layout: {                       // full current layout — null = no change
 *       layoutId: string,
 *       rooms: [{ id, name, geometry: number[][], attributes: { program, area } }]
 *     } | null
 *   }
 *
 * To connect a real agent, replace getAgentResponse() and getAgentResponseForSidebarAdd()
 * with API calls that return the same shape.
 */

// ─── Geometry registry ────────────────────────────────────────────────────────
// Fixed 13×7 floor plate — no overlaps regardless of room combination:
//
//  x:  0    4    7    10   13
//      +----+----+----+----+
//  y=4 | Kitchen | Bed(s)  | Study
//      +----+----+----+----+
//  y=0 |  Living Room  |Bath|
//      +---------------+----+
//
// Overflow rooms tile below y=7, staying attached to the footprint.

const ROOM_GEO = {
  'Kitchen':     { geometry: [[0,0],[0,4],[4,4],[4,0],[0,0]],     attributes: { program: 'kitchen', area: 16, daylight: 4.4 } },
  'Bedroom':     { geometry: [[4,0],[4,4],[10,4],[10,0],[4,0]],   attributes: { program: 'bed',     area: 24, daylight: 4.1 } },
  'Bedroom 1':   { geometry: [[4,0],[4,4],[7,4],[7,0],[4,0]],     attributes: { program: 'bed',     area: 12, daylight: 3.8 } },
  'Bedroom 2':   { geometry: [[7,0],[7,4],[10,4],[10,0],[7,0]],   attributes: { program: 'bed',     area: 12, daylight: 4.3 } },
  'Bedroom 3':   { geometry: [[4,0],[4,2],[10,2],[10,0],[4,0]],   attributes: { program: 'bed',     area:  8, daylight: 3.5 } },
  'Study':       { geometry: [[10,0],[10,4],[13,4],[13,0],[10,0]], attributes: { program: 'study',   area: 12, daylight: 5.0 } },
  'Living': { geometry: [[0,4],[0,7],[10,7],[10,4],[0,4]],   attributes: { program: 'living',  area: 30, daylight: 5.0 } },
  'Bathroom':    { geometry: [[10,4],[10,7],[13,7],[13,4],[10,4]], attributes: { program: 'bath',    area:  9, daylight: 1.4 } },
}

function getRoomGeo(name, overflowIndex) {
  if (ROOM_GEO[name]) return ROOM_GEO[name]
  // Overflow rooms attach below the main footprint at y=7
  const x = (overflowIndex % 3) * 4
  const y = 7 + Math.floor(overflowIndex / 3) * 3
  return {
    geometry: [[x,y],[x,y+3],[x+4,y+3],[x+4,y],[x,y]],
    attributes: { program: 'extra', area: 12, daylight: 1.2 }
  }
}

let overflowCounter = 0

let layoutCounter = 1

export function buildLayout(rooms) {
  overflowCounter = 0
  const roomList = rooms.map((r, i) => {
    const geo = getRoomGeo(r.name, overflowCounter)
    if (!ROOM_GEO[r.name]) overflowCounter++
    return { id: r.id ?? i + 1, name: r.name, ...geo }
  })
  const programs = [...new Set(roomList.map(r => r.attributes?.program).filter(Boolean))]
  const counts = {}
  roomList.forEach(r => { counts[r.name] = (counts[r.name] || 0) + 1 })
  const desc = Object.entries(counts).map(([name, n]) => `${n} ${name.toLowerCase()}${n > 1 ? 's' : ''}`).join(', ')
  return {
    layoutId: `Layout-${String(layoutCounter++).padStart(3, '0')}`,
    attributes: { description: desc },
    rooms: roomList
  }
}

// ─── Routine builder ─────────────────────────────────────────────────────────
// Only returns a routine when activities are present AND a layout exists.
// Each persona gets morning/afternoon/evening steps as room ID strings.

import { PERSONA_COLORS } from '../utils/roomAnalysis.js'

// Time slots: 06:00–22:00 every 2 hours (9 steps, index 0–8)
export const ROUTINE_TIMES = ['06:00', '08:00', '10:00', '12:00', '14:00', '16:00', '18:00', '20:00', '22:00']

export function buildRoutine(parsedInput, layout) {
  if (!parsedInput?.activities?.length || !layout?.rooms?.length) return null

  const findId = (program) => {
    const r = layout.rooms.find(r => r.attributes?.program === program)
    return r ? String(r.id) : null
  }

  const bed     = findId('bed')
  const bath    = findId('bath')
  const kitchen = findId('kitchen')
  const living  = findId('living')
  const study   = findId('study')

  if (!bed && !kitchen) return null

  const fallback = (...ids) => ids.find(Boolean) ?? null

  // Build a schedule for a single persona based on their workStyle
  // workStyle: 'office' | 'home' | 'none'
  function scheduleFor(workStyle) {
    // 9 slots: 06, 08, 10, 12, 14, 16, 18, 20, 22
    if (workStyle === 'office') return [
      fallback(bed, living),            // 06:00 — sleep
      fallback(bath, bed),              // 08:00 — bathroom then leave
      null,                             // 10:00 — away (office)
      null,                             // 12:00 — away (office)
      null,                             // 14:00 — away (office)
      null,                             // 16:00 — away (office)
      fallback(kitchen, living),        // 18:00 — home, cook
      fallback(living, kitchen),        // 20:00 — evening
      fallback(bed, living),            // 22:00 — sleep
    ]
    if (workStyle === 'home') return [
      fallback(bed, living),                                            // 06:00 — sleep
      fallback(kitchen, living),                                        // 08:00 — breakfast
      fallback(study, living),                                          // 10:00 — work from home
      fallback(kitchen, living),                                        // 12:00 — lunch break
      fallback(study, living),                                          // 14:00 — work from home
      fallback(study, living),                                          // 16:00 — wrapping up
      fallback(kitchen, living),                                        // 18:00 — cook
      fallback(living, kitchen),                                        // 20:00 — evening
      fallback(bed, living),                                            // 22:00 — sleep
    ]
    // workStyle === 'none' — stays home, no formal work
    return [
      fallback(bed, living),            // 06:00 — sleep
      fallback(kitchen, bath),          // 08:00 — breakfast
      fallback(living, kitchen),        // 10:00 — relax
      fallback(kitchen, living),        // 12:00 — lunch
      fallback(living, study),          // 14:00 — leisure
      fallback(living, kitchen),        // 16:00 — relax
      fallback(kitchen, living),        // 18:00 — cook
      fallback(living, kitchen),        // 20:00 — evening
      fallback(bed, living),            // 22:00 — sleep
    ]
  }

  const personas = parsedInput.households?.length
    ? parsedInput.households
    : [{ name: 'Resident', workStyle: 'none' }]

  return personas.map((h, i) => ({
    persona: h.name,
    color: PERSONA_COLORS[i % PERSONA_COLORS.length],
    steps: scheduleFor(h.workStyle ?? 'none')
  }))
}

// ─── Brief generator ──────────────────────────────────────────────────────────
export function generateBrief(p) {
  if (!p) return ''
  const who        = (p.households || []).map(h => h.name).join(' and ')
  const activities = (p.activities  || []).map(a => a.type.toLowerCase()).join(', ')
  const rooms      = (p.rooms       || []).map(r => r.name).join(', ')
  let brief = ''
  if (who)        brief += `${who} live together.`
  if (activities) brief += ` They enjoy ${activities}.`
  if (rooms)      brief += ` Their home should include: ${rooms}.`
  return brief.trim()
}

// ─── Scenario definitions ─────────────────────────────────────────────────────
// Evaluated top-to-bottom; first match wins.
// Each scenario gets the latest user message and the full current state.

const SCENARIOS = [
  // ── Intro: user describes who they are and lifestyle ──
  {
    match: (msg, _state) => /partner|couple|family|flatmate|roommate|we cook|cook a lot|john|sarah|live with/i.test(msg),
    respond(msg, _state) {
      const defaultRooms = [
        { id: 1, name: 'Kitchen',     size: 'medium' },
        { id: 2, name: 'Living', size: 'medium' },
        { id: 3, name: 'Bedroom',     size: 'double' },
        { id: 4, name: 'Bathroom',    size: 'small'  },
      ]
      const parsedInput = {
        households: [
          { name: 'John', relationship: 'self',    workStyle: 'office' },
          { name: 'Sarah', relationship: 'partner', workStyle: 'none'   }
        ],
        activities: [{ type: 'Cooking', time: 'often' }],
        rooms: defaultRooms
      }
      parsedInput.brief = generateBrief(parsedInput)
      const layout = buildLayout(defaultRooms)
      const routine = buildRoutine(parsedInput, layout)
      if (routine) parsedInput.routine = routine
      return {
        message: "Nice to meet you, John and Sarah! I've put together a first layout with a kitchen, living room, bedroom and bathroom. How many bedrooms are you thinking of?",
        parsedInput,
        layout,
        suggestedPrompts: ['One bedroom', 'Two bedrooms', 'Three bedrooms']
      }
    }
  },

  // ── Bedroom count: user specifies number of bedrooms ──
  {
    match: (msg, state) => {
      const hasHouseholds = state.parsedInput?.households?.length > 0
      const mentionsBeds = /\bbed(room)?s?\b|sleep/i.test(msg)
      const mentionsNumber = /\b(one|two|three|four|1|2|3|4)\b/i.test(msg)
      return hasHouseholds && (mentionsBeds || mentionsNumber)
    },
    respond(msg, state) {
      const n = /three|3/i.test(msg) ? 3 : /two|2/i.test(msg) ? 2 : 1
      // Replace any existing bedroom entries, keep all other rooms
      const nonBedrooms = (state.parsedInput?.rooms ?? []).filter(r => !/bedroom/i.test(r.name))
      const bedrooms = n === 1
        ? [{ name: 'Bedroom', size: 'double' }]
        : Array.from({ length: n }, (_, i) => ({ name: `Bedroom ${i + 1}`, size: 'double' }))
      const rooms = [...nonBedrooms, ...bedrooms].map((r, i) => ({ ...r, id: i + 1 }))
      const parsedInput = { ...(state.parsedInput ?? {}), rooms }
      parsedInput.brief = generateBrief(parsedInput)
      const layout = buildLayout(rooms)
      const routine = buildRoutine(parsedInput, layout)
      if (routine) parsedInput.routine = routine
      return {
        message: n === 1
          ? "Kept one bedroom. Does this layout work for you?"
          : `Updated to ${n} bedrooms. Does this layout work for you?`,
        parsedInput,
        layout,
        suggestedPrompts: ["Add a study", "Add a bathroom", "Looks good!"]
      }
    }
  },

  // ── Add a specific room type (chat path) ──
  {
    match: (msg, _state) => /study|office|workspace|work.?room|work from home|home.?office|extra room|bathroom|bath\b|wc|toilet|storage|balcon/i.test(msg),
    respond(msg, state) {
      const nameMap = [
        [/study|office|workspace|work.?room|work from home|home.?office|extra room/i, 'Study'],
        [/bathroom|bath\b|wc|toilet/i, 'Bathroom'],
        [/storage/i,                   'Storage'],
        [/balcon/i,                    'Balcony'],
      ]
      const newName = (nameMap.find(([re]) => re.test(msg)) ?? [])[1] ?? 'Room'
      const existing = state.parsedInput?.rooms ?? []
      const rooms = existing.some(r => r.name === newName)
        ? existing
        : [...existing, { id: existing.length + 1, name: newName, size: 'medium' }]
      // Add work activity when working from home, update matching persona's workStyle
      const existingActivities = state.parsedInput?.activities ?? []
      const isWFH = /work from home|home.?office/i.test(msg)
      const activities = isWFH && !existingActivities.some(a => /work/i.test(a.type))
        ? [...existingActivities, { type: 'Work', time: 'weekdays' }]
        : existingActivities

      // If a persona name appears in the message, update only that persona;
      // otherwise update only the 'self' persona (the speaker)
      const households = (state.parsedInput?.households ?? []).map(h => {
        const anyNameMentioned = (state.parsedInput?.households ?? []).some(p => new RegExp(`\\b${p.name}\\b`, 'i').test(msg))
        if (anyNameMentioned) {
          const nameInMsg = new RegExp(`\\b${h.name}\\b`, 'i').test(msg)
          if (!nameInMsg) return h
        } else {
          // No name — only update the speaker ('self')
          if (h.relationship !== 'self') return h
        }
        if (isWFH) return { ...h, workStyle: 'home' }
        return h
      })
      const parsedInput = { ...(state.parsedInput ?? {}), rooms, activities, households }
      parsedInput.brief = generateBrief(parsedInput)
      const layout = buildLayout(rooms)
      const routine = buildRoutine(parsedInput, layout)
      if (routine) parsedInput.routine = routine
      return {
        message: `Done — I've added a ${newName.toLowerCase()} to the layout. Anything else?`,
        parsedInput,
        layout,
        suggestedPrompts: ["Add a bathroom", "Make the kitchen bigger", "That's all, thanks!"]
      }
    }
  },

  // ── Qualitative / lifestyle notes → extras ──
  {
    match: (msg, state) => {
      // Must have some context already (not the very first message)
      const hasContext = !!state.parsedInput
      const isQualitative = /light|natural|guest|dog|cat|pet|child|baby|music|garden|quiet|noise|privacy|open.?plan|we like|we love|we have|we are|we often|we want|planning to|lot of/i.test(msg)
      // Don't fire if it already matched a room or bedroom scenario
      const isRoom = /study|office|workspace|bathroom|storage|balcon|bed(room)?|sleep/i.test(msg)
      return hasContext && isQualitative && !isRoom
    },
    respond(msg, state) {
      // Capitalise first letter, trim trailing punctuation
      const note = msg.trim().replace(/[.!?]+$/, '')
      const note2 = note.charAt(0).toUpperCase() + note.slice(1)
      const existingExtras = state.parsedInput?.extras ?? []
      const extras = existingExtras.some(e => e.toLowerCase() === note2.toLowerCase())
        ? existingExtras
        : [...existingExtras, note2]
      const parsedInput = { ...(state.parsedInput ?? {}), extras }
      parsedInput.brief = generateBrief(parsedInput)
      return {
        message: `Noted — I'll keep that in mind: "${note2}". Anything else?`,
        parsedInput,
        layout: null,
        suggestedPrompts: []
      }
    }
  },

  // ── Confirmation / happy ──
  {
    match: (msg, _state) => /\b(yes|yeah|great|good|happy|looks good|perfect|ok|okay|fine)\b/i.test(msg),
    respond(_msg, _state) {
      return {
        message: "Great! Is there anything else you'd like to add or adjust?",
        parsedInput: null,
        layout: null,
        suggestedPrompts: ["Add a study", "Add a bathroom", "That's all!"]
      }
    }
  },

  // ── Fallback ──
  {
    match: () => true,
    respond(_msg, _state) {
      return {
        message: "Noted! Is there anything else you'd like to add or change?",
        parsedInput: null,
        layout: null,
        suggestedPrompts: []
      }
    }
  }
]

// ─── Public API ───────────────────────────────────────────────────────────────

/**
 * Returns an AgentResponse for a user chat message.
 * @param {string} latestMessage - the user's latest message text
 * @param {{ parsedInput: object|null, layout: object|null }} currentState
 * @returns {AgentResponse}
 */
export function getAgentResponse(latestMessage, currentState) {
  const scenario = SCENARIOS.find(s => s.match(latestMessage, currentState))
  return scenario.respond(latestMessage, currentState)
}

/**
 * Returns an AgentResponse when the user adds an item via the sidebar.
 * parsedInput is already merged by the caller before this is invoked —
 * so this only needs to produce a message and optionally update the layout.
 * @param {string} section - 'households' | 'activities' | 'rooms'
 * @param {object} item
 * @param {{ parsedInput: object, layout: object|null }} currentState - already includes the new item
 * @returns {AgentResponse}
 */
export function getAgentResponseForSidebarAdd(section, item, currentState) {
  const label = typeof item === 'string' ? item : (item.name || item.type || 'item')
  const sectionLabel = { households: 'household member', activities: 'activity', rooms: 'room', extras: 'note' }[section]
  const hasLayout = !!currentState.layout

  let message = `Got it — I've added "${label}" as a new ${sectionLabel} and updated the brief.`
  if (section === 'rooms' && hasLayout) {
    message += ' Updating the layout now.'
  }
  if (section === 'extras') {
    message = `Noted — I'll keep "${label}" in mind.`
  }

  let updatedParsedInput = null
  let updatedLayout = null
  if (section === 'rooms' && hasLayout) {
    updatedLayout = buildLayout(currentState.parsedInput.rooms)
    const routine = buildRoutine(currentState.parsedInput, updatedLayout)
    if (routine) {
      updatedParsedInput = { ...currentState.parsedInput, routine }
    }
  }

  return {
    message,
    parsedInput: updatedParsedInput, // null unless routine changed
    layout: updatedLayout,
    suggestedPrompts: []
  }
}
