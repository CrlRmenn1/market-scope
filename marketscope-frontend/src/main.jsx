import React from 'react'
import ReactDOM from 'react-dom/client'
// IMPORTANT: Leaflet CSS MUST be imported before App and index.css
import App from './App'
import './index.css' 
import 'leaflet/dist/leaflet.css';
ReactDOM.createRoot(document.getElementById('root')).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
)