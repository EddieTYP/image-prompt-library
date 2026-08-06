import React from 'react';
import { createRoot } from 'react-dom/client';
import App from './App';
import { applyStoredAppearance } from './utils/appearance';
import './styles.css';

applyStoredAppearance();
createRoot(document.getElementById('root')!).render(<React.StrictMode><App /></React.StrictMode>);
