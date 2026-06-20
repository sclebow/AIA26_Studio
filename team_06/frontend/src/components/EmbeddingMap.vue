<script setup>
import { computed, ref, watch, onMounted } from 'vue'
import { PROGRAM_COLORS } from '../utils/roomAnalysis.js'
import { fetchLayoutById } from '../api/agentClient.js'

const props = defineProps({
  embeddingMap:  { type: Object, required: true },
  searchResults: { type: Array,  default: () => [] },
})
const emit = defineEmits(['selectLayout', 'previewLayout'])

const VW = 800
const VH = 520
const PAD = 52
const MINI_SIZE = 46    // SVG data units for miniature
const GRID_COLS = 5
const GRID_ROWS = 4

const zoom        = ref(1)
const pan         = ref({ x: 0, y: 0 })
const dragging    = ref(false)
const clickOrigin = ref(null)
const dragStart   = ref({ x: 0, y: 0, px: 0, py: 0 })
const svgEl       = ref(null)
const wrapperRef  = ref(null)
const hovered     = ref(null)
const mousePos    = ref({ x: 0, y: 0 })
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

const resultSet = computed(() => new Set(props.embeddingMap?.result_ids ?? []))
const rankMap   = computed(() => {
  const m = {}
  ;(props.embeddingMap?.result_ids ?? []).forEach((id, i) => { m[id] = i + 1 })
  return m
})
const queryPoint = computed(() => {
  const qc = props.embeddingMap?.query_coord
  if (!qc || !B.value) return null
  return _toSvg(qc.x, qc.y, B.value)
})

// ── dot color: teal→blue brand gradient ──────────────────────────────────────

function dotColor(sx, sy) {
  const t   = Math.max(0, Math.min(1, (sx - PAD) / (VW - 2 * PAD)))
  const hue = Math.round(175 + t * 35)
  const sat = Math.round(55  + t * 20)
  const lgt = Math.round(62  - t * 10)
  return `hsl(${hue}, ${sat}%, ${lgt}%)`
}

// ── layout geometry sources ───────────────────────────────────────────────────

const resultLayoutMap = computed(() =>
  Object.fromEntries(props.searchResults.map(r => [r.layoutId, r.layout]))
)
function layoutFor(id) {
  return resultLayoutMap.value[id] ?? layoutCache.value[id] ?? null
}

// ── miniature polygons (Y-down, matching Konva, no flip needed) ───────────────

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

// Precomputed only for dots that have geometry — always visible, not zoom-gated
const miniCache = computed(() => {
  const result = {}
  for (const p of allPoints.value) {
    const layout = layoutFor(p.id)
    if (layout) result[p.id] = miniPaths(layout)
  }
  return result
})

// Separate non-result and result points so results render on top
const bgPoints     = computed(() => allPoints.value.filter(p => !resultSet.value.has(p.id)))
const resultPoints = computed(() => allPoints.value.filter(p =>  resultSet.value.has(p.id)))

// ── grid-sampled pre-fetch on mount ──────────────────────────────────────────

function gridSampledIds() {
  const coords = props.embeddingMap?.all_coords
  if (!coords) return []
  const entries = Object.entries(coords)
  const xs = entries.map(([, c]) => c.x), ys = entries.map(([, c]) => c.y)
  const minX = Math.min(...xs), maxX = Math.max(...xs)
  const minY = Math.min(...ys), maxY = Math.max(...ys)
  const rx = maxX - minX || 1, ry = maxY - minY || 1
  const buckets = {}
  for (const [id, { x, y }] of entries) {
    const bx = Math.min(GRID_COLS - 1, Math.floor((x - minX) / rx * GRID_COLS))
    const by = Math.min(GRID_ROWS - 1, Math.floor((y - minY) / ry * GRID_ROWS))
    const key = `${bx},${by}`
    if (!buckets[key]) buckets[key] = id
  }
  return Object.values(buckets)
}

onMounted(() => {
  const sampled = gridSampledIds().filter(id =>
    !resultLayoutMap.value[id] && !layoutCache.value[id]
  )
  for (const id of sampled) {
    if (fetchingIds.has(id)) continue
    fetchingIds.add(id)
    fetchLayoutById(id)
      .then(data => {
        if (data?.layout) layoutCache.value = { ...layoutCache.value, [id]: data.layout }
      })
      .catch(() => {})
      .finally(() => fetchingIds.delete(id))
  }
})

// hover-triggered fetch for dots not in the pre-sample
watch(() => hovered.value?.id, async (id) => {
  if (!id || resultLayoutMap.value[id] || layoutCache.value[id] || fetchingIds.has(id)) return
  fetchingIds.add(id)
  try {
    const data = await fetchLayoutById(id)
    if (data?.layout) layoutCache.value = { ...layoutCache.value, [id]: data.layout }
  } catch { /* silent */ } finally { fetchingIds.delete(id) }
})

// zoom/pan triggered fetch for newly visible dots
function fetchVisible() {
  const x0 = -pan.value.x / zoom.value
  const y0 = -pan.value.y / zoom.value
  const x1 = x0 + VW / zoom.value
  const y1 = y0 + VH / zoom.value
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

const popupDesc = computed(() => {
  const id = hovered.value?.id
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
  const popupH = popupDesc.value ? 130 : 40
  let x = mousePos.value.x + 20
  let y = mousePos.value.y + 20
  if (x + POPUP_W > rect.width  - 8) x = mousePos.value.x - POPUP_W - 12
  if (y + popupH  > rect.height - 8) y = mousePos.value.y - popupH  - 12
  return { left: x + 'px', top: y + 'px' }
})

// ── zoom & pan ────────────────────────────────────────────────────────────────

const DRAG_THRESHOLD = 5

function svgCursor(e) {
  const r = svgEl.value.getBoundingClientRect()
  return { x: (e.clientX - r.left) / r.width * VW, y: (e.clientY - r.top) / r.height * VH }
}
function onWheel(e) {
  const f  = e.deltaY < 0 ? 1.18 : 1 / 1.18
  const nz = Math.min(10, Math.max(0.25, zoom.value * f))
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
  if (resultSet.value.has(id)) emit('selectLayout', id)
  else emit('previewLayout', id)
}

const transform = computed(() =>
  `translate(${pan.value.x}, ${pan.value.y}) scale(${zoom.value})`
)
</script>

<template>
  <div ref="wrapperRef" class="embedding-map" @mousemove="trackMouse">

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
    >
      <g :transform="transform">

        <!-- Background dots (non-results) -->
        <g
          v-for="p in bgPoints"
          :key="p.id"
          :transform="`translate(${p.sx}, ${p.sy})`"
          style="cursor: pointer"
          @mouseenter="hovered = { id: p.id, rank: null }"
          @mouseleave="hovered = null"
          @click="onDotClick($event, p.id)"
        >
          <template v-if="miniCache[p.id]">
            <rect
              :x="-MINI_SIZE/2 - 2" :y="-MINI_SIZE/2 - 2"
              :width="MINI_SIZE + 4" :height="MINI_SIZE + 4"
              rx="6" fill="white" stroke="#D9D9D9" stroke-width="1" vector-effect="non-scaling-stroke"
            />
            <polygon
              v-for="(room, i) in miniCache[p.id]"
              :key="i" :points="room.pts" :fill="room.fill"
              stroke="#333" stroke-width="0.35"
            />
          </template>
          <circle v-else cx="0" cy="0" r="4"
            :fill="dotColor(p.sx, p.sy)" />
        </g>

        <!-- Result miniatures / dots — rendered on top so they're never hidden -->
        <g
          v-for="p in resultPoints"
          :key="'res-' + p.id"
          :transform="`translate(${p.sx}, ${p.sy})`"
          style="cursor: pointer"
          @mouseenter="hovered = { id: p.id, rank: rankMap[p.id] ?? null }"
          @mouseleave="hovered = null"
          @click="onDotClick($event, p.id)"
        >
          <template v-if="miniCache[p.id]">
            <rect
              :x="-MINI_SIZE/2 - 2" :y="-MINI_SIZE/2 - 2"
              :width="MINI_SIZE + 4" :height="MINI_SIZE + 4"
              rx="6" fill="white" stroke="#D9D9D9" stroke-width="1" vector-effect="non-scaling-stroke"
            />
            <polygon
              v-for="(room, i) in miniCache[p.id]"
              :key="i" :points="room.pts" :fill="room.fill"
              stroke="#333" stroke-width="0.35"
            />
          </template>
          <circle v-else cx="0" cy="0" r="6"
            fill="var(--color-blue)" stroke="white" stroke-width="1.5" />
          <!-- Rank badge (result dots only) -->
          <g class="rank-badge">
            <circle :cx="-MINI_SIZE/2 + 6" :cy="-MINI_SIZE/2 + 6" r="5" fill="var(--color-blue)"/>
            <text :x="-MINI_SIZE/2 + 6" :y="-MINI_SIZE/2 + 6" text-anchor="middle" dominant-baseline="central" class="rank-num">
              {{ rankMap[p.id] }}
            </text>
          </g>
        </g>

        <!-- Query crosshair -->
        <g v-if="queryPoint" pointer-events="none" class="query-marker">
          <line :x1="queryPoint.sx - 10" :y1="queryPoint.sy" :x2="queryPoint.sx + 10" :y2="queryPoint.sy" />
          <line :x1="queryPoint.sx" :y1="queryPoint.sy - 10" :x2="queryPoint.sx" :y2="queryPoint.sy + 10" />
        </g>

      </g>
    </svg>

    <!-- Hover popup: ID + description only -->
    <div v-if="hovered" class="mini-popup" :style="popupStyle">
      <div class="popup-header">
        <span v-if="hovered.rank" class="popup-rank">{{ hovered.rank }}</span>
        <span class="popup-id">{{ hovered.id }}</span>
      </div>
      <p v-if="popupDesc" class="popup-desc">{{ popupDesc }}</p>
      <div v-if="popupDesc" class="popup-hint">
        {{ hovered.rank ? 'Click to select' : 'Click to preview' }}
      </div>
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
        Search results
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
.rank-badge { pointer-events: none; }
.rank-num {
  font-size: 6.5px;
  font-weight: 700;
  fill: white;
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
.popup-header { display: flex; align-items: center; gap: 6px; }
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
