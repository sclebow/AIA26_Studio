// ── Apple-minimalist color palette (purple accent) ──────────────────────────

export const NODE_COLORS = {
  room: '#3D3270',      // deep indigo
  door: '#D4976A',      // warm amber
  wall: '#2A2838',      // dark plum
  window: '#A78BFA',    // lavender
  furniture: '#7C6FAA', // muted purple
  mep: '#5B8A6F',       // sage green
} as const;

export const EDGE_COLORS = {
  contained_in: '#2A2838',    // structural, muted
  door_connects: '#D4976A',   // amber (door color)
  adjacent: '#3D3270',        // room connectivity
  near: '#7C6FAA',            // proximity (muted purple)
  near_wall: '#2A2838',       // structural
  near_window: '#A78BFA',     // lavender
  sightline: '#5B8A6F',       // sage green for visible
  blocks: '#F87171',          // soft rose for obstructions
  path: '#7C6FAA',            // purple for paths
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

const FONT_FACE = '-apple-system, BlinkMacSystemFont, "SF Pro Text", system-ui, sans-serif';

export const NETWORK_OPTIONS = {
  physics: { enabled: false },
  interaction: {
    hover: true,
    tooltipDelay: 150,
    dragNodes: false,
    dragView: true,
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
      size: 10,
      x: 0,
      y: 0,
      color: 'rgba(139, 92, 246, 0.12)',
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
  panelBg: 'rgba(20, 16, 32, 0.72)',
  panelBorder: 'rgba(255, 255, 255, 0.06)',
  text: '#F5F5F7',
  muted: '#86868B',
  accent: '#8B5CF6',
  ok: '#34D399',
  fail: '#F87171',
  warn: '#FBBF24',
  canvasBg: '#08080C',
  nodeFontColor: '#F5F5F7',
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
