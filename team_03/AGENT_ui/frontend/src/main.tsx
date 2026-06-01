import React from 'react';
import ReactDOM from 'react-dom/client';
import { ThemeProvider } from './components/common/ThemeToggle';
import App from './App';
import './styles/index.css';

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <ThemeProvider>
      <App />
    </ThemeProvider>
  </React.StrictMode>
);
