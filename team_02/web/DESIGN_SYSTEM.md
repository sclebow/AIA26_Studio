# Sensi Design System

A small, documented design system for the Sensi frontend (`team_02/web/src`).
Three layers: **tokens + logic** (`lib/`, `styles/`), **generic primitives** (`ui/`),
and **domain primitives** (`viz/`, `canvas/`). Screens are assembled from these.

---

## 1. The sense-encoding language

Sensi encodes six senses on a dark canvas with a consistent visual grammar:

| Channel | Means | Where it's defined |
|---|---|---|
| **Hue** | which sense | `SENSE_REGISTRY` in `lib/senses.js` |
| **Intensity / opacity** | health (0..1 score) | `INTENSITY` + `scoreOpacity()` in `lib/senses.js` |
| **Glyph** | sense shorthand (△ ○ ∿ □ ≈ ∶) | `SENSE_REGISTRY.glyph` |
| **Line-style + icon** | provenance (research/physics/personality) | `basisDash()` / `basisBorder()` / `BASIS_ICON` in `lib/senseModel.js` |
| **Status color** | pass / warn / fail (score health only) | `STATUS` / `scoreColor()` in `lib/senses.js` |

**Core principle:** a sense always owns its hue; comfort is shown by how *vivid* it
is (opacity), never a red→green hue shift.

### Single source of truth
- **`lib/senses.js`** is the one authored place for hues, glyphs, baselines,
  status palette, and the intensity ladder. `SENSES`, `SC`, `SI`, `BASELINES`
  are derived from one `SENSE_REGISTRY` array. **To add or retune a sense, edit
  one row.**
- CSS gets these values via **`hydrateCssTokens()`** (`lib/tokens.js`), which
  injects `--thermal…--tactile`, `--status-*`, and `--i-0…4` onto `:root` at
  startup. The `~1,800`-line `global.css` keeps using `var(--thermal)` etc.,
  but there is **no second hand-maintained copy** — JS is the source.
- `lib/constants.js` is a **barrel**: it re-exports the encoding from `senses.js`
  and adds non-visual UI copy (onboarding steps, role implications, overlay
  phrases). Import the encoding from either; `constants.js` is the legacy path.

---

## 2. Design tokens

| Token group | File | Notes |
|---|---|---|
| Sense hues / status / intensity | `lib/senses.js` → injected to `:root` | JS source of truth |
| Radius, spacing, motion, ambient opacity, fg/bg | `styles/tokens.css` (`:root`) | bespoke CSS ladders |
| Tailwind utility tokens (font, radius, bg/fg) | `styles/global.css` (`@theme`) | must stay in the Tailwind entry |
| Motion (JS mirror for Framer) | `lib/motion.js` (`DUR`, `EASE`) | Framer can't read CSS vars |

**Typeface** is a single-token swap: change `--font-sans` / `--font-mono` in the
`@theme` block of `global.css` **and** the matching `<link>` in `index.html`.
Every rule references `var(--font-sans/mono)` — there are no hardcoded families.
Current: **Inter** (sans) + **JetBrains Mono** (mono).

**Rule of thumb:** colors → sense registry; spacing/radius/motion → CSS token
ladders; Framer durations/eases → `lib/motion.js`. Never retype a magic value
that already has a token.

---

## 3. Component library

### `ui/` — generic primitives (no sense knowledge)
| Component | Purpose | Key props |
|---|---|---|
| `TopBar` | brand pill (avatar + "sensi") shell, used by all 5 screens | `wide`, `children` |
| `ChatThread` | Sensi/user bubble thread, animated last avatar, auto-scroll | `messages`, `thinking`, `format?` |
| `Collapsible` | **headless** open/close + conditional body; caller renders its own trigger via the `trigger(open, toggle)` render-prop | `defaultOpen`, `trigger`, `bodyClassName`, `bodyStyle` |

### `viz/` — sense-aware primitives
| Component | Purpose | Key props |
|---|---|---|
| `SenseSignature` *(components/)* | the 6-petal "rose" fingerprint — the lingua franca | `scores`, `baseScores?`, `size`, `showGlyphs`, `activeSense` |
| `SenseBar` | one sense spectrum bar (the old `pbar-row`) | `sense`, `value`, `baseline?`, `opacity?` |
| `SenseGraph` *(components/)* | sense-coupling ring graph | `rooms` |
| `SensiAvatar` *(components/)* | concentric six-ring brand mark | `size`, `animate`, `strokeWidth?`, `centerR?` |

### `canvas/` — the SVG floor-plan instrument (two-tier model)
`SensePlan` is a thin **container** (loads layout, derives the view transform +
per-room lookups, holds hover state) composing presentational layers in two tiers:

- **Base** (`layers.plan`): the architecture — `WallsLayer` · `RoomsLayer` (wall
  outline + label + hit area) · `OpeningsLayer` · `FurnitureLayer`. Toggle off to
  **isolate** a graph lens. Hovering a room/furniture raises a `PlanTooltip`.
- **Lenses**:
  - `comfort` — `RoomsLayer` fill tint + a per-room **comfort ring** (overall
    score as an animated arc + number, top-right corner). The full 6-petal
    `SenseSignature` now renders **only in the FocusCard** (an unreadable blob at
    canvas scale).
  - `flow` / `topology` — **mutually exclusive** graph lenses drawn on the shared
    `RoomGraph` node substrate. `FlowLayer` = directional bleed arrows (worse→
    better, severity thickness, glyph·score labels, animated). `TopologyLayer` =
    adjacency edges driven by backend `graph_data`. When a graph lens is active
    the base dims. North is docked in the `Legend`.

**Layer control model.** Three orthogonal control *kinds*, kept visually distinct:
the **sense selector** (`SenseMixer`, recolors the active lens), the **layer rail**
(`LayerToggles`: plan / comfort / flow / topology), and **nav** (chat, sense
graph). A lens declares what it `requires` (`scores` / `graph` — see
`LAYER_REQUIRES` in `LayoutModeScreen`); the toggle derives *active / available /
needs-run*, and clicking an unavailable lens **asks Sensi to run** that analysis
(`LAYER_RUN_MSG`) instead of toggling an empty layer. The `Legend` is strictly
per-active-lens.

Pure geometry helpers live in `lib/geometry.js` (`polyPoints`, `centroid`,
`dims`, `swingPath`); `failingTransmissive()` lives in `lib/senseModel.js`.

---

## 4. State & data

- **Selection bus** — `lib/selection.jsx` (`SelectionProvider` + `useSelection`).
  One React Context holds `activeRoom` / `activeSense` / `hoverSense`;
  `focusSense = hoverSense ?? activeSense` ("hover previews, click pins"). Every
  view cross-highlights from this. Wraps only the layout phase.
- **Layer toggles** — local `useState` in `LayoutModeScreen` (layout-phase-only,
  no cross-highlight, so intentionally not in the bus).
- **Turn selectors** — `lib/turn.js` (`roomScores`, `roomByName`,
  `suggestionsFor`, `conflictCount`) decode a turn's JSON blobs in one place.
- **API** — all network calls in `api/client.js`; no inline `fetch`.

---

## 5. Two intentional non-abstractions

Documented so nobody "fixes" them later:

- **`sense-pill` (quiz grid) vs `mix-pill` (control rail)** are two distinct pill
  treatments. They share only the sense token (hue + glyph), which is already
  centralized. They were *not* merged into one `<SensePill variant>` — that would
  be a switch statement masquerading as reuse.
- **`fc-row` (FocusCard) vs `pbar-row` (SenseBar)** look similar but carry
  different content (FocusCard adds personalized thresholds + base→effective
  deltas + provenance icons). Only the `pbar-row` shape was extracted to
  `SenseBar`; `fc-row` stays bespoke.

---

## 6. Known follow-up

`styles/global.css` is still a single ~1,800-line stylesheet (ported verbatim
from the original PyQt UI, faculty-validated). The **token layer** has been
split out to `styles/tokens.css`; the per-component rules were deliberately left
intact to avoid regressing validated design. A future increment can co-locate
component CSS (CSS Modules) next to each component, one block at a time.
