import React, { createContext, useContext, useState, useEffect } from 'react';
import { darkTheme, lightTheme, type ThemeColors } from '../../styles/theme';

type Theme = 'dark' | 'light';

interface ThemeContextValue {
  theme: Theme;
  colors: ThemeColors;
  toggleTheme: () => void;
}

export const ThemeContext = createContext<ThemeContextValue>({
  theme: 'light',
  colors: lightTheme,
  toggleTheme: () => {},
});

export const useTheme = () => useContext(ThemeContext);

export const ThemeProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [theme, setTheme] = useState<Theme>('light');
  const colors = theme === 'dark' ? darkTheme : lightTheme;

  const toggleTheme = () => {
    setTheme(prev => (prev === 'dark' ? 'light' : 'dark'));
  };

  // Apply CSS variables to document root so global styles respond
  useEffect(() => {
    const root = document.documentElement;
    root.style.setProperty('--bg', colors.bg);
    root.style.setProperty('--text', colors.text);
    root.style.setProperty('--muted', colors.muted);
    root.style.setProperty('--accent', colors.accent);
    root.style.setProperty('--accent-dim', colors.accentDim);
    root.style.setProperty('--border', colors.border);
    root.style.setProperty('--panel-bg', colors.panelBg);
    root.style.setProperty('--card-bg', colors.cardBg);
    root.style.setProperty('--input-bg', colors.inputBg);
    root.style.setProperty('--ok', colors.ok);
    root.style.setProperty('--warning', colors.warning);
    root.style.setProperty('--error', colors.error);
    root.style.setProperty('--success', colors.success);
    root.style.setProperty('--font', colors.font);
    document.body.style.background = colors.bg;
    document.body.style.color = colors.text;
  }, [colors]);

  return (
    <ThemeContext.Provider value={{ theme, colors, toggleTheme }}>
      {children}
    </ThemeContext.Provider>
  );
};

const SunIcon: React.FC = () => (
  <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <circle cx="12" cy="12" r="5" />
    <line x1="12" y1="1" x2="12" y2="3" />
    <line x1="12" y1="21" x2="12" y2="23" />
    <line x1="4.22" y1="4.22" x2="5.64" y2="5.64" />
    <line x1="18.36" y1="18.36" x2="19.78" y2="19.78" />
    <line x1="1" y1="12" x2="3" y2="12" />
    <line x1="21" y1="12" x2="23" y2="12" />
    <line x1="4.22" y1="19.78" x2="5.64" y2="18.36" />
    <line x1="18.36" y1="5.64" x2="19.78" y2="4.22" />
  </svg>
);

const MoonIcon: React.FC = () => (
  <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z" />
  </svg>
);

const ThemeToggle: React.FC = () => {
  const { theme, colors, toggleTheme } = useTheme();

  const buttonStyle: React.CSSProperties = {
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    width: '36px',
    height: '36px',
    borderRadius: '8px',
    border: `1px solid ${colors.border}`,
    background: colors.cardBg,
    color: colors.accent,
    cursor: 'pointer',
    transition: 'background 0.2s, border-color 0.2s, color 0.2s',
    outline: 'none',
    fontFamily: colors.font,
  };

  return (
    <button
      style={buttonStyle}
      onClick={toggleTheme}
      title={theme === 'dark' ? 'Switch to light mode (placeholder)' : 'Switch to dark mode'}
      aria-label="Toggle theme"
    >
      {theme === 'dark' ? <SunIcon /> : <MoonIcon />}
    </button>
  );
};

export default React.memo(ThemeToggle);
