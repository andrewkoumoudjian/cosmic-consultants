import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import '@fontsource/geist-sans/400.css';
import '@fontsource/geist-sans/500.css';
import '@fontsource/geist-mono/400.css';
import '@fontsource/source-serif-4/300.css';
import '@fontsource/source-serif-4/400.css';
import '@fontsource/source-serif-4/600.css';
import './styles.css';
import radioEmpty from './assets/radio-empty.svg';
import radioSelected from './assets/radio-selected.svg';
import { App } from './App.tsx';

// The Figma radio assets, used as CSS masks so they take the ink colour (DESIGN.md).
document.documentElement.style.setProperty('--radio-empty', `url("${radioEmpty}")`);
document.documentElement.style.setProperty('--radio-selected', `url("${radioSelected}")`);

createRoot(document.getElementById('root')!).render(<StrictMode><App /></StrictMode>);
