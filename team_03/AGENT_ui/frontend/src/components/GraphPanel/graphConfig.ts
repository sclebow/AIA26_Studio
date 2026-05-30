// ── Welcome-page lavender palette (purple/violet family + teal/rose accents) ─
// Cohesive with WelcomePage/Onboarding: lavender #a78bfa, purple #8b5cf6,
// pale #c4b5fd, deep indigo #4c4470. Differentiation by hue + shape + glow.

export const NODE_COLORS = {
  room: '#a78bfa',      // lavender (hero)
  door: '#f0abfc',      // orchid — stands out as connector
  wall: '#4c4470',      // deep muted indigo — structural, recessive
  window: '#c4b5fd',    // pale lavender
  furniture: '#8b5cf6', // vivid purple
  mep: '#5eead4',       // teal — utility systems, complements purple
} as const;

export const EDGE_COLORS = {
  contained_in: '#4c4470',    // structural, dim indigo
  door_connects: '#f0abfc',   // orchid (door color)
  adjacent: '#a78bfa',        // lavender (room connectivity)
  near: '#8b5cf6',            // purple (proximity)
  near_wall: '#4c4470',       // structural indigo
  near_window: '#c4b5fd',     // pale lavender
  sightline: '#5eead4',       // teal for visible
  blocks: '#fb7185',          // rose for obstructions (warning)
  path: '#818cf8',            // indigo for paths
} as const;

export const NODE_SHAPES: Record<string, string> = {
  room: 'dot',
  door: 'diamond',
  wall: 'dot',
  window: 'dot',
  furniture: 'square',
  mep: 'dot',
};

export const NODE_SIZES: Record<string, number> = {
  room: 25,
  door: 10,
  wall: 8,
  window: 8,
  furniture: 15,
  mep: 12,
};

export const EDGE_DASHES: Record<string, boolean | number[]> = {
  contained_in: true,
  door_connects: false,
  adjacent: false,
  near: false,
  near_wall: true,
  near_window: true,
  sightline: [6, 4, 2, 4],
  blocks: false,
  path: false,
};

export const STRUCTURAL_EDGES = new Set([
  'contained_in', 'door_connects', 'adjacent', 'near_wall', 'near_window',
]);

export const NODE_DESCRIPTIONS: Record<string, string> = {
  room: 'A space enclosed by walls and accessible through doors.',
  door: 'An opening element connecting two spaces.',
  wall: 'A structural boundary element that encloses and separates spaces.',
  window: 'An opening in a wall providing natural light and ventilation.',
  furniture: 'A placed object occupying floor area with clearance requirements.',
  mep: 'Mechanical, Electrical, or Plumbing element.',
};

export const EDGE_DESCRIPTIONS: Record<string, string> = {
  contained_in: 'element belongs to room',
  door_connects: 'door links to room',
  adjacent: 'rooms share a door',
  near: 'furniture < 3m apart',
  near_wall: 'furniture < 3m from wall',
  near_window: 'furniture < 3m from window',
  blocks: 'object blocks access to another',
  sightline: 'direct line of sight',
  path: 'navigable route with distance',
};

// ── Vis.js network options ──────────────────────────────────────────────────

const FONT_FACE = '"Share Tech Mono", "SF Mono", "Fira Code", ui-monospace, monospace';

export const NETWORK_OPTIONS = {
  physics: { enabled: false },
  interaction: {
    hover: true,
    tooltipDelay: 150,
    dragNodes: false,
    // Left-drag pan disabled to match the 3D viewport (left = select only);
    // panning is bound to middle/right mouse buttons in GraphPanel instead.
    dragView: false,
    zoomView: true,
    multiselect: false,
  },
  nodes: {
    shape: 'dot',
    font: {
      color: '#F5F5F7',
      size: 10,
      face: FONT_FACE,
      align: 'center' as const,
    },
    borderWidth: 2,
    shadow: {
      enabled: true,
      size: 22,
      x: 0,
      y: 0,
      color: 'rgba(139, 92, 246, 0.35)',
    },
  },
  edges: {
    smooth: { type: 'continuous' as const, roundness: 0.3 },
    font: {
      color: '#86868B',
      size: 8,
      face: FONT_FACE,
    },
  },
} as const;

// ── Theme constants ─────────────────────────────────────────────────────────

export interface GraphTheme {
  panelBg: string;
  panelBorder: string;
  text: string;
  muted: string;
  accent: string;
  ok: string;
  fail: string;
  warn: string;
  canvasBg: string;
  nodeFontColor: string;
}

const DARK_THEME: GraphTheme = {
  panelBg: 'rgba(15, 9, 30, 0.92)',
  panelBorder: 'rgba(139, 92, 246, 0.22)',
  text: '#f5f3ff',
  muted: '#9a8cc8',
  accent: '#a78bfa',
  ok: '#5eead4',
  fail: '#fb7185',
  warn: '#fbbf24',
  canvasBg: '#0a0612',
  nodeFontColor: '#f5f3ff',
};

const LIGHT_THEME: GraphTheme = {
  panelBg: 'rgba(255, 255, 255, 0.82)',
  panelBorder: 'rgba(0, 0, 0, 0.06)',
  text: '#1D1D1F',
  muted: '#86868B',
  accent: '#7C3AED',
  ok: '#059669',
  fail: '#DC2626',
  warn: '#D97706',
  canvasBg: '#F5F5F7',
  nodeFontColor: '#1D1D1F',
};

/** Returns the graph theme for the given dark/light mode. */
export function getTheme(isDark: boolean): GraphTheme {
  return isDark ? DARK_THEME : LIGHT_THEME;
}

export const THEME = DARK_THEME;
