<script setup>
import { computed, ref, watch, onMounted } from 'vue'
import { PROGRAM_COLORS } from '../utils/roomAnalysis.js'
import { fetchLayoutById } from '../api/agentClient.js'

const props = defineProps({
  embeddingMap:  { type: Object, required: true },
  searchResults: { type: Array,  default: () => [] },
})
const emit = defineEmits(['selectLayout', 'previewLayout', 'findInBetween'])

const VW = 800
const VH = 520
const PAD = 52
const MINI_SIZE = 46

// Zoom thresholds at which each density level of miniatures appears
const ZOOM_A = 1.5   // sparse  — 3×2 grid  (~6 layouts)
const ZOOM_B = 2.5   // medium  — 5×3 grid  (~15 layouts)
const ZOOM_C = 3.5   // dense   — 8×5 grid  (~40 layouts)

const zoom        = ref(1)
const pan         = ref({ x: 0, y: 0 })
const dragging    = ref(false)
const clickOrigin = ref(null)
const dragStart   = ref({ x: 0, y: 0, px: 0, py: 0 })
const svgEl       = ref(null)
const wrapperRef  = ref(null)
const hovered     = ref(null)
const mousePos    = ref({ x: 0, y: 0 })
const clickedId   = ref(null)
const clickedPos  = ref({ x: 0, y: 0 })
const pinnedIds   = ref([])  // ordered, max 2

function togglePin(id) {
  const idx = pinnedIds.value.indexOf(id)
  if (idx !== -1) {
    pinnedIds.value = pinnedIds.value.filter(p => p !== id)
  } else if (pinnedIds.value.length < 2) {
    pinnedIds.value = [...pinnedIds.value, id]
  }
}
function isPinned(id) { return pinnedIds.value.includes(id) }
function pinIndex(id) { return pinnedIds.value.indexOf(id) + 1 }
const layoutCache = ref({})
const fetchingIds = new Set()
let   fetchTimer  = null

// ── coordinate mapping ────────────────────────────────────────────────────────

function _bounds(coords) {
  const xs = Object.values(coords).map(c => c.x)
  const ys = Object.values(coords).map(c => c.y)
  const minX = Math.min(...xs), maxX = Math.max(...xs)
  const minY = Math.min(...ys), maxY = Math.max(...ys)
  return { minX, maxX, minY, maxY, rx: maxX - minX || 1, ry: maxY - minY || 1 }
}
function _toSvg(x, y, b) {
  return {
    sx: PAD + (x - b.minX) / b.rx * (VW - 2 * PAD),
    sy: PAD + (1 - (y - b.minY) / b.ry) * (VH - 2 * PAD),
  }
}

const B = computed(() => {
  const c = props.embeddingMap?.all_coords
  return c ? _bounds(c) : null
})

const allPoints = computed(() => {
  const c = props.embeddingMap?.all_coords
  if (!c || !B.value) return []
  return Object.entries(c).map(([id, { x, y }]) => ({ id, ..._toSvg(x, y, B.value) }))
})

const topResultId = computed(() => props.embeddingMap?.result_ids?.[0] ?? null)
const queryPoint = computed(() => {
  const qc = props.embeddingMap?.query_coord
  if (!qc || !B.value) return null
  return _toSvg(qc.x, qc.y, B.value)
})

// ── layout geometry sources ───────────────────────────────────────────────────

const resultLayoutMap = computed(() =>
  Object.fromEntries(props.searchResults.map(r => [r.layoutId, r.layout]))
)
function layoutFor(id) {
  return resultLayoutMap.value[id] ?? layoutCache.value[id] ?? null
}

// ── dot color ─────────────────────────────────────────────────────────────────

function dotColor(sx) {
  const t   = Math.max(0, Math.min(1, (sx - PAD) / (VW - 2 * PAD)))
  const hue = Math.round(175 + t * 35)
  const sat = Math.round(55  + t * 20)
  const lgt = Math.round(62  - t * 10)
  return `hsl(${hue}, ${sat}%, ${lgt}%)`
}

// ── miniature polygons ────────────────────────────────────────────────────────

function miniPaths(layout) {
  if (!layout?.rooms?.length) return null
  const allPts = layout.rooms.flatMap(r => r.geometry ?? [])
  if (!allPts.length) return null
  const xs = allPts.map(p => p[0]), ys = allPts.map(p => p[1])
  const cx = (Math.min(...xs) + Math.max(...xs)) / 2
  const cy = (Math.min(...ys) + Math.max(...ys)) / 2
  const span = Math.max(Math.max(...xs) - Math.min(...xs), Math.max(...ys) - Math.min(...ys)) || 1
  const s = (MINI_SIZE * 0.82) / span
  return layout.rooms.map(r => ({
    pts:  (r.geometry ?? []).map(([x, y]) => `${(s*(x-cx)).toFixed(1)},${(s*(y-cy)).toFixed(1)}`).join(' '),
    fill: PROGRAM_COLORS[r.attributes?.program] ?? '#ddd',
  }))
}

const miniCache = computed(() => {
  const result = {}
  for (const p of allPoints.value) {
    const layout = layoutFor(p.id)
    if (layout) result[p.id] = miniPaths(layout)
  }
  return result
})


// ── spatial grid sampling ─────────────────────────────────────────────────────

function gridSample(cols, rows) {
  const coords = props.embeddingMap?.all_coords
  if (!coords) return []
  const entries = Object.entries(coords)
  const xs = entries.map(([, c]) => c.x), ys = entries.map(([, c]) => c.y)
  const minX = Math.min(...xs), maxX = Math.max(...xs)
  const minY = Math.min(...ys), maxY = Math.max(...ys)
  const rx = maxX - minX || 1, ry = maxY - minY || 1
  const buckets = {}
  for (const [id, { x, y }] of entries) {
    const bx = Math.min(cols - 1, Math.floor((x - minX) / rx * cols))
    const by = Math.min(rows - 1, Math.floor((y - minY) / ry * rows))
    const key = `${bx},${by}`
    if (!buckets[key]) buckets[key] = id
  }
  return Object.values(buckets)
}

const sampleA = computed(() => new Set(gridSample(3, 2)))
const sampleB = computed(() => new Set(gridSample(5, 3)))
const sampleC = computed(() => new Set(gridSample(8, 5)))

// ── viewport culling ──────────────────────────────────────────────────────────

function isInViewport(sx, sy) {
  const m = MINI_SIZE + 6
  const screenX = pan.value.x + sx * zoom.value
  const screenY = pan.value.y + sy * zoom.value
  return screenX >= -m && screenX <= VW + m && screenY >= -m && screenY <= VH + m
}

// Show miniature for a dot only at appropriate zoom level and if in viewport
function showMini(id, sx, sy) {
  if (!miniCache.value[id]) return false
  if (id === topResultId.value) return zoom.value >= ZOOM_A
  if (zoom.value >= ZOOM_C && sampleC.value.has(id)) return isInViewport(sx, sy)
  if (zoom.value >= ZOOM_B && sampleB.value.has(id)) return isInViewport(sx, sy)
  if (zoom.value >= ZOOM_A && sampleA.value.has(id)) return isInViewport(sx, sy)
  return false
}

// Top result rendered on top layer; everything else is background
const bgPoints  = computed(() => allPoints.value.filter(p => p.id !== topResultId.value))
const topResult = computed(() => allPoints.value.find(p => p.id === topResultId.value) ?? null)

// ── pre-fetch all sample levels on mount ──────────────────────────────────────

onMounted(() => {
  const toFetch = new Set([
    ...gridSample(3, 2),
    ...gridSample(5, 3),
    ...gridSample(8, 5),
  ])
  for (const id of toFetch) {
    if (resultLayoutMap.value[id] || layoutCache.value[id] || fetchingIds.has(id)) continue
    fetchingIds.add(id)
    fetchLayoutById(id)
      .then(data => {
        if (data?.layout) layoutCache.value = { ...layoutCache.value, [id]: data.layout }
      })
      .catch(() => {})
      .finally(() => fetchingIds.delete(id))
  }
})

// Fetch geometry when hovering a dot we don't have yet
watch(() => hovered.value?.id, async (id) => {
  if (!id || resultLayoutMap.value[id] || layoutCache.value[id] || fetchingIds.has(id)) return
  fetchingIds.add(id)
  try {
    const data = await fetchLayoutById(id)
    if (data?.layout) layoutCache.value = { ...layoutCache.value, [id]: data.layout }
  } catch { /* silent */ } finally { fetchingIds.delete(id) }
})

// At high zoom, fetch whatever is now in viewport
function fetchVisible() {
  if (zoom.value < ZOOM_C) return
  const x0 = -pan.value.x / zoom.value, y0 = -pan.value.y / zoom.value
  const x1 = x0 + VW / zoom.value,      y1 = y0 + VH / zoom.value
  const m  = MINI_SIZE
  const toFetch = allPoints.value.filter(p =>
    !resultLayoutMap.value[p.id] &&
    !layoutCache.value[p.id] &&
    !fetchingIds.has(p.id) &&
    p.sx >= x0 - m && p.sx <= x1 + m &&
    p.sy >= y0 - m && p.sy <= y1 + m
  ).slice(0, 10)
  for (const p of toFetch) {
    fetchingIds.add(p.id)
    fetchLayoutById(p.id)
      .then(data => {
        if (data?.layout) layoutCache.value = { ...layoutCache.value, [p.id]: data.layout }
      })
      .catch(() => {})
      .finally(() => fetchingIds.delete(p.id))
  }
}
watch([zoom, pan], () => {
  clearTimeout(fetchTimer)
  fetchTimer = setTimeout(fetchVisible, 400)
}, { deep: true })

// ── popup ─────────────────────────────────────────────────────────────────────

const activePopupId = computed(() => clickedId.value ?? hovered.value?.id ?? null)

const popupDesc = computed(() => {
  const id = activePopupId.value
  if (!id) return null
  return props.embeddingMap?.descriptions?.[id]
    ?? layoutFor(id)?.apartment?.attributes?.description
    ?? layoutFor(id)?.attributes?.description
    ?? null
})

const POPUP_W = 192
const popupStyle = computed(() => {
  if (!wrapperRef.value) return {}
  const rect   = wrapperRef.value.getBoundingClientRect()
  const popupH = popupDesc.value ? 150 : 70
  const pos    = clickedId.value ? clickedPos.value : mousePos.value
  let x = pos.x + 20
  let y = pos.y + 20
  if (x + POPUP_W > rect.width  - 8) x = pos.x - POPUP_W - 12
  if (y + popupH  > rect.height - 8) y = pos.y - popupH  - 12
  return { left: x + 'px', top: y + 'px' }
})

// ── zoom & pan ────────────────────────────────────────────────────────────────

const DRAG_THRESHOLD = 5
const MIN_ZOOM = 1.0
const MAX_ZOOM = 10.0

function svgCursor(e) {
  const r = svgEl.value.getBoundingClientRect()
  return { x: (e.clientX - r.left) / r.width * VW, y: (e.clientY - r.top) / r.height * VH }
}
function onWheel(e) {
  const f  = e.deltaY < 0 ? 1.18 : 1 / 1.18
  const nz = Math.min(MAX_ZOOM, Math.max(MIN_ZOOM, zoom.value * f))
  // Snap to home when fully zoomed out
  if (nz <= MIN_ZOOM) {
    zoom.value = MIN_ZOOM
    pan.value  = { x: 0, y: 0 }
    return
  }
  const m  = svgCursor(e)
  pan.value = {
    x: m.x + (pan.value.x - m.x) * nz / zoom.value,
    y: m.y + (pan.value.y - m.y) * nz / zoom.value,
  }
  zoom.value = nz
}
function onMousedown(e) {
  if (e.button !== 0) return
  dragging.value = true
  clickOrigin.value = { x: e.clientX, y: e.clientY }
  dragStart.value = { x: e.clientX, y: e.clientY, px: pan.value.x, py: pan.value.y }
}
function onSvgMousemove(e) {
  if (!dragging.value || !svgEl.value) return
  const r = svgEl.value.getBoundingClientRect()
  pan.value = {
    x: dragStart.value.px + (e.clientX - dragStart.value.x) * VW / r.width,
    y: dragStart.value.py + (e.clientY - dragStart.value.y) * VH / r.height,
  }
}
function onMouseup()    { dragging.value = false }
function onMouseleave() { dragging.value = false; hovered.value = null }
function trackMouse(e) {
  if (!wrapperRef.value) return
  const r = wrapperRef.value.getBoundingClientRect()
  mousePos.value = { x: e.clientX - r.left, y: e.clientY - r.top }
}
function isDrag(e) {
  if (!clickOrigin.value) return false
  const dx = e.clientX - clickOrigin.value.x
  const dy = e.clientY - clickOrigin.value.y
  return Math.sqrt(dx * dx + dy * dy) > DRAG_THRESHOLD
}
function onDotClick(e, id) {
  e.stopPropagation()
  if (isDrag(e)) return
  if (clickedId.value === id) {
    clickedId.value = null
    return
  }
  clickedId.value = id
  if (wrapperRef.value) {
    const r = wrapperRef.value.getBoundingClientRect()
    clickedPos.value = { x: e.clientX - r.left, y: e.clientY - r.top }
  }
}

function clearClicked() { clickedId.value = null }
function clearPins()   { pinnedIds.value = [] }
function onSvgClick(e) { if (!isDrag(e)) clearClicked() }

const transform = computed(() =>
  `translate(${pan.value.x}, ${pan.value.y}) scale(${zoom.value})`
)
</script>

<template>
  <div ref="wrapperRef" class="embedding-map" @mousemove="trackMouse" @click.self="clearClicked">

    <span class="map-title">Explore layouts</span>

    <svg
      ref="svgEl"
      class="map-svg"
      :viewBox="`0 0 ${VW} ${VH}`"
      preserveAspectRatio="xMidYMid meet"
      :style="{ cursor: dragging ? 'grabbing' : 'grab' }"
      @wheel.prevent="onWheel"
      @mousedown="onMousedown"
      @mousemove="onSvgMousemove"
      @mouseup="onMouseup"
      @mouseleave="onMouseleave"
      @click="onSvgClick"
    >
      <g :transform="transform">

        <!-- All dots except top result -->
        <g
          v-for="p in bgPoints"
          :key="p.id"
          :transform="`translate(${p.sx}, ${p.sy})`"
          style="cursor: pointer"
          @mouseenter="hovered = { id: p.id }"
          @mouseleave="hovered = null"
          @click="onDotClick($event, p.id)"
        >
          <template v-if="showMini(p.id, p.sx, p.sy)">
            <rect
              :x="-MINI_SIZE/2 - 2" :y="-MINI_SIZE/2 - 2"
              :width="MINI_SIZE + 4" :height="MINI_SIZE + 4"
              rx="3" fill="white"
              :stroke="isPinned(p.id) ? '#00B8A8' : '#d0d5dd'"
              :stroke-width="isPinned(p.id) ? '1.5' : '0.8'"
              vector-effect="non-scaling-stroke"
            />
            <polygon
              v-for="(room, i) in miniCache[p.id]"
              :key="i" :points="room.pts" :fill="room.fill" fill-opacity="0.7"
              stroke="#4a4a4a" stroke-width="0.5"
              vector-effect="non-scaling-stroke"
            />
          </template>
          <template v-else>
            <circle cx="0" cy="0" r="4" :fill="dotColor(p.sx)" />
            <circle v-if="isPinned(p.id)" cx="0" cy="0" r="8" fill="none" stroke="#00B8A8" stroke-width="1.5" vector-effect="non-scaling-stroke" />
          </template>
          <text v-if="isPinned(p.id)" x="0" y="-9" text-anchor="middle" font-size="5" fill="#00B8A8" font-weight="bold" vector-effect="non-scaling-stroke">{{ pinIndex(p.id) }}</text>
        </g>

        <!-- Top result — always on top, blue dot or blue-outlined miniature -->
        <g
          v-if="topResult"
          :key="'top-' + topResult.id"
          :transform="`translate(${topResult.sx}, ${topResult.sy})`"
          style="cursor: pointer"
          @mouseenter="hovered = { id: topResult.id }"
          @mouseleave="hovered = null"
          @click="onDotClick($event, topResult.id)"
        >
          <template v-if="showMini(topResult.id, topResult.sx, topResult.sy)">
            <rect
              :x="-MINI_SIZE/2 - 2" :y="-MINI_SIZE/2 - 2"
              :width="MINI_SIZE + 4" :height="MINI_SIZE + 4"
              rx="3" fill="white"
              :stroke="isPinned(topResult.id) ? '#00B8A8' : 'var(--color-blue)'"
              :stroke-width="isPinned(topResult.id) ? '1.5' : '1.2'"
              vector-effect="non-scaling-stroke"
            />
            <polygon
              v-for="(room, i) in miniCache[topResult.id]"
              :key="i" :points="room.pts" :fill="room.fill" fill-opacity="0.7"
              stroke="#4a4a4a" stroke-width="0.5"
              vector-effect="non-scaling-stroke"
            />
          </template>
          <template v-else>
            <circle cx="0" cy="0" r="7" fill="var(--color-blue)" stroke="white" stroke-width="2" vector-effect="non-scaling-stroke" />
            <circle v-if="isPinned(topResult.id)" cx="0" cy="0" r="11" fill="none" stroke="#00B8A8" stroke-width="1.5" vector-effect="non-scaling-stroke" />
          </template>
          <text v-if="isPinned(topResult.id)" x="0" y="-13" text-anchor="middle" font-size="5" fill="#00B8A8" font-weight="bold" vector-effect="non-scaling-stroke">{{ pinIndex(topResult.id) }}</text>
        </g>

        <!-- Query crosshair -->
        <g v-if="queryPoint" pointer-events="none" class="query-marker">
          <line :x1="queryPoint.sx - 10" :y1="queryPoint.sy" :x2="queryPoint.sx + 10" :y2="queryPoint.sy" />
          <line :x1="queryPoint.sx" :y1="queryPoint.sy - 10" :x2="queryPoint.sx" :y2="queryPoint.sy + 10" />
        </g>

      </g>
    </svg>

    <!-- Hover / click popup -->
    <div
      v-if="activePopupId"
      class="mini-popup"
      :class="{ 'mini-popup--sticky': !!clickedId }"
      :style="popupStyle"
      @click.stop
    >
      <div class="popup-header">
        <span class="popup-id">{{ activePopupId }}</span>
        <button v-if="clickedId" class="popup-close" @click="clearClicked">✕</button>
      </div>
      <p v-if="popupDesc" class="popup-desc">{{ popupDesc }}</p>
      <div v-if="!clickedId" class="popup-hint">Click to open</div>
      <div v-if="clickedId" class="popup-actions">
        <button class="popup-select-btn" @click="emit('selectLayout', clickedId); clearClicked()">Select</button>
        <button
          class="popup-pin-btn"
          :class="{ 'popup-pin-btn--active': isPinned(clickedId) }"
          :disabled="!isPinned(clickedId) && pinnedIds.length >= 2"
          @click="togglePin(clickedId); clearClicked()"
        >{{ isPinned(clickedId) ? 'Unpin' : 'Pin' }}</button>
      </div>
    </div>

    <!-- Find in between pill — appears when 2 are pinned -->
    <div v-if="pinnedIds.length === 2" class="find-between-pill" @click="emit('findInBetween', pinnedIds[0], pinnedIds[1]); clearPins()">
      Find in between
    </div>

    <!-- Legend -->
    <div class="map-legend">
      <span class="legend-item">
        <svg width="10" height="10" viewBox="0 0 10 10">
          <circle cx="5" cy="5" r="4" fill="hsl(193,55%,60%)"/>
        </svg>
        All layouts
      </span>
      <span class="legend-item">
        <svg width="10" height="10" viewBox="0 0 10 10">
          <circle cx="5" cy="5" r="5" fill="var(--color-blue)" stroke="white" stroke-width="1.5"/>
        </svg>
        Best match
      </span>
      <span class="legend-item">
        <svg width="12" height="12" viewBox="0 0 12 12">
          <line x1="0" y1="6" x2="12" y2="6" stroke="var(--color-marine)" stroke-width="2.2" stroke-linecap="round"/>
          <line x1="6" y1="0" x2="6" y2="12" stroke="var(--color-marine)" stroke-width="2.2" stroke-linecap="round"/>
        </svg>
        Your query
      </span>
      <span class="legend-hint">Scroll to zoom · Drag to pan</span>
    </div>

  </div>
</template>

<style scoped>
.embedding-map {
  width: 100%;
  height: 100%;
  display: flex;
  flex-direction: column;
  padding: 24px 28px 16px;
  box-sizing: border-box;
  user-select: none;
  position: relative;
}
.map-title {
  font-size: var(--font-size-subtitle);
  color: var(--color-blue);
  margin-bottom: 10px;
  flex-shrink: 0;
}
.map-svg {
  flex: 1 1 auto;
  min-height: 0;
  width: 100%;
  display: block;
}
.query-marker line {
  stroke: var(--color-marine);
  stroke-width: 2.5;
  stroke-linecap: round;
}
/* popup */
.mini-popup {
  position: absolute;
  background: white;
  border: 1px solid var(--color-border);
  border-radius: var(--radius-card);
  box-shadow: var(--shadow-card);
  padding: 10px 12px;
  width: 192px;
  pointer-events: none;
  z-index: 10;
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.mini-popup--sticky {
  pointer-events: auto;
  border-color: var(--color-blue);
}
.popup-actions {
  display: flex;
  gap: 6px;
  margin-top: 2px;
}
.popup-select-btn,
.popup-pin-btn {
  flex: 1;
  padding: 5px 8px;
  border: none;
  border-radius: var(--radius);
  font-size: var(--font-size-small);
  font-weight: 600;
  cursor: pointer;
}
.popup-select-btn {
  background: var(--color-blue);
  color: white;
}
.popup-select-btn:hover { opacity: 0.85; }
.popup-pin-btn {
  background: #e6faf9;
  color: #007a70;
  border: 1px solid #00B8A8;
}
.popup-pin-btn:hover { background: #ccf5f2; }
.popup-pin-btn--active {
  background: #00B8A8;
  color: white;
}
.popup-pin-btn:disabled { opacity: 0.4; cursor: not-allowed; }
.find-between-pill {
  position: absolute;
  top: 20px;
  right: 28px;
  background: #00B8A8;
  color: white;
  font-size: var(--font-size-small);
  font-weight: 700;
  padding: 7px 16px;
  border-radius: 999px;
  cursor: pointer;
  box-shadow: 0 2px 8px rgba(0,184,168,0.35);
  z-index: 20;
  user-select: none;
}
.find-between-pill:hover { opacity: 0.88; }
.popup-header { display: flex; align-items: center; gap: 6px; }
.popup-close {
  margin-left: auto;
  background: none;
  border: none;
  font-size: 11px;
  color: var(--color-text-secondary);
  cursor: pointer;
  padding: 0 2px;
  line-height: 1;
  flex-shrink: 0;
}
.popup-close:hover { color: var(--color-text); }
.popup-rank {
  width: 18px; height: 18px;
  border-radius: 50%;
  background: var(--color-blue);
  color: white;
  font-size: 10px; font-weight: 700;
  display: flex; align-items: center; justify-content: center;
  flex-shrink: 0;
}
.popup-id {
  font-size: var(--font-size-small);
  font-weight: 500;
  color: var(--color-text);
  white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
}
.popup-desc {
  font-size: var(--font-size-small);
  color: var(--color-text-secondary);
  line-height: 1.45; margin: 0;
  display: -webkit-box;
  -webkit-line-clamp: 4;
  line-clamp: 4;
  -webkit-box-orient: vertical;
  overflow: hidden;
}
.popup-hint {
  font-size: var(--font-size-small);
  color: var(--color-blue);
  font-style: italic; text-align: right;
}

/* legend */
.map-legend {
  display: flex; gap: 18px; align-items: center;
  font-size: var(--font-size-small);
  color: var(--color-text-secondary);
  margin-top: 8px; flex-wrap: wrap;
}
.legend-item { display: flex; align-items: center; gap: 6px; }
.legend-hint { margin-left: auto; opacity: 0.6; font-style: italic; }
</style>
