export interface ThemeColors {
  bg: string;
  panelBg: string;
  text: string;
  muted: string;
  accent: string;
  accentDim: string;
  ok: string;
  warning: string;
  error: string;
  success: string;
  font: string;
  /** Display font for titles/headers (sci-fi). Body/data uses `font`. */
  fontHeading: string;
  border: string;
  cardBg: string;
  inputBg: string;
}

// Body/data = Share Tech Mono (monospace); headers = Orbitron. Loaded in index.html.
const BODY_FONT = '"Share Tech Mono", "SF Mono", "Fira Code", ui-monospace, monospace';
const HEADING_FONT = '"Orbitron", "Share Tech Mono", system-ui, sans-serif';

// Welcome-page "sci-fi" palette: deep purple-black + lavender accents + glow/glass.
export const darkTheme: ThemeColors = {
  bg: '#0a0612',
  panelBg: 'rgba(15, 9, 30, 0.92)',
  text: '#f5f3ff',
  muted: '#9a8cc8',
  accent: '#a78bfa',
  accentDim: 'rgba(139, 92, 246, 0.15)',
  ok: '#5eead4',
  warning: '#fbbf24',
  error: '#fb7185',
  success: '#5eead4',
  font: BODY_FONT,
  fontHeading: HEADING_FONT,
  border: 'rgba(139, 92, 246, 0.22)',
  cardBg: 'rgba(15, 9, 30, 0.96)',
  inputBg: 'rgba(139, 92, 246, 0.06)',
};

export const lightTheme: ThemeColors = {
  bg: '#F5F5F7',
  panelBg: 'rgba(245, 245, 247, 0.95)',
  text: '#1D1D1F',
  muted: '#86868B',
  accent: '#7C3AED',
  accentDim: 'rgba(124, 58, 237, 0.10)',
  ok: '#059669',
  warning: '#D97706',
  error: '#DC2626',
  success: '#059669',
  font: BODY_FONT,
  fontHeading: HEADING_FONT,
  border: 'rgba(0, 0, 0, 0.06)',
  cardBg: 'rgba(255, 255, 255, 0.97)',
  inputBg: 'rgba(245, 245, 247, 0.9)',
};

export const theme = darkTheme;

/**
 * Standardized studio font scale — 3 sizes only.
 *   label (10): captions, data values, section/panel headers (Orbitron caps), legend, log
 *   body  (12): chat messages, descriptions, inputs, buttons, properties values
 *   title (14): the app logo / brand
 * Large dashboard numerals (score/grade, ~16–28) are intentional display figures,
 * not part of the text scale. The welcome/onboarding pages keep their own sizes.
 */
export const fontSize = { label: 10, body: 12, title: 14 } as const;
