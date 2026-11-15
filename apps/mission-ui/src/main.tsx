import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import '@fontsource/geist-mono/400.css';
import '@fontsource/geist-mono/500.css';
import '@fontsource/geist-mono/700.css';
import '@fontsource/source-serif-4/400.css';
import '@fontsource/source-serif-4/600.css';
import './styles/tokens.css';
import './styles/base.css';
import './styles/screens.css';
import { App } from './App.tsx';
import { MissionProvider } from './state.tsx';

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <MissionProvider>
      <App />
    </MissionProvider>
  </StrictMode>,
);
