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
  border: string;
  cardBg: string;
  inputBg: string;
}

export const darkTheme: ThemeColors = {
  bg: '#12131a',
  panelBg: 'rgba(18, 19, 26, 0.94)',
  text: '#F5F5F7',
  muted: '#86868B',
  accent: '#8B9CC0',
  accentDim: 'rgba(139, 156, 192, 0.12)',
  ok: '#7EA68B',
  warning: '#C4896E',
  error: '#D07070',
  success: '#7EA68B',
  font: '-apple-system, BlinkMacSystemFont, "SF Pro Display", "SF Pro Text", system-ui, sans-serif',
  border: 'rgba(255, 255, 255, 0.08)',
  cardBg: 'rgba(18, 19, 26, 0.96)',
  inputBg: 'rgba(14, 15, 22, 0.85)',
};

export const lightTheme: ThemeColors = {
  bg: '#F5F5F7',
  panelBg: 'rgba(245, 245, 247, 0.95)',
  text: '#1D1D1F',
  muted: '#86868B',
  accent: '#6B7B9E',
  accentDim: 'rgba(107, 123, 158, 0.10)',
  ok: '#7EA68B',
  warning: '#C4896E',
  error: '#C06060',
  success: '#7EA68B',
  font: '-apple-system, BlinkMacSystemFont, "SF Pro Display", "SF Pro Text", system-ui, sans-serif',
  border: 'rgba(0, 0, 0, 0.06)',
  cardBg: 'rgba(255, 255, 255, 0.97)',
  inputBg: 'rgba(245, 245, 247, 0.9)',
};

export const theme = darkTheme;
