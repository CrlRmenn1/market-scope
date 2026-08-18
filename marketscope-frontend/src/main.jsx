import React from 'react'
import ReactDOM from 'react-dom/client'
// IMPORTANT: Leaflet CSS MUST be imported before App and index.css
import App from './App'
import './index.css'
import 'leaflet/dist/leaflet.css';

// Persistent tile cache (see public/sw.js) - only intercepts OSM tile
// requests, so this is safe to register in dev too without interfering
// with Vite's own asset serving/HMR.
if ('serviceWorker' in navigator) {
  window.addEventListener('load', () => {
    navigator.serviceWorker.register('/sw.js').catch((err) => {
      console.warn('Tile cache service worker registration failed:', err);
    });
  });
}

ReactDOM.createRoot(document.getElementById('root')).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
)