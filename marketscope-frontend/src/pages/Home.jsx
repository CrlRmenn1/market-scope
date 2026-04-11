import React, { useEffect, useRef, useState } from 'react';
import L from 'leaflet';
import 'leaflet/dist/leaflet.css';

// Fix for Vite + Leaflet image bug
delete L.Icon.Default.prototype._getIconUrl;
L.Icon.Default.mergeOptions({
  iconRetinaUrl: '', iconUrl: '', shadowUrl: ''
});

export default function Home({ onMapTap, theme }) {
  const mapRef = useRef(null);
  const mapInstance = useRef(null);
  const markerInstance = useRef(null);
  const tileLayerInstance = useRef(null); // We use this to switch tiles dynamically
  const [selectedCoord, setSelectedCoord] = useState(null);

  // Initialize the map (Runs only once)
  useEffect(() => {
    if (!mapInstance.current) {
      mapInstance.current = L.map(mapRef.current, {
        center: [7.3075, 125.6811],
        zoom: 15,
        zoomControl: false 
      });

      const customIcon = L.divIcon({
        className: 'custom-pin-wrapper',
        html: `
          <div class="pure-css-mark">
            <div class="pure-pulse"></div>
            <div class="pure-ring"></div>
            <svg class="pure-pin" viewBox="0 0 24 24" fill="currentColor">
              <path d="M12 2C8.13 2 5 5.13 5 9c0 5.25 7 13 7 13s7-7.75 7-13c0-3.87-3.13-7-7-7zm0 9.5c-1.38 0-2.5-1.12-2.5-2.5s1.12-2.5 2.5-2.5 2.5 1.12 2.5 2.5-1.12 2.5-2.5 2.5z"/>
            </svg>
          </div>
        `,
        iconSize: [40, 40],
        iconAnchor: [20, 40]
      });

      mapInstance.current.on('click', (e) => {
        if (markerInstance.current) {
          markerInstance.current.setLatLng(e.latlng);
        } else {
          markerInstance.current = L.marker(e.latlng, { icon: customIcon }).addTo(mapInstance.current);
        }
        setSelectedCoord(e.latlng);
        mapInstance.current.panTo(e.latlng);
      });
    }

    return () => {
      if (mapInstance.current) {
        mapInstance.current.remove();
        mapInstance.current = null;
      }
    };
  }, [onMapTap]);

  // Handle Dynamic Theme Switching (Light/Dark Mode)
  useEffect(() => {
    if (mapInstance.current) {
      // Remove old tile layer if it exists to avoid overlapping maps
      if (tileLayerInstance.current) {
        mapInstance.current.removeLayer(tileLayerInstance.current);
      }

      // Check current theme and apply the correct tiles
      const tileUrl = theme === 'light' 
        ? 'https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png'
        : 'https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png';

      tileLayerInstance.current = L.tileLayer(tileUrl, {
        attribution: '&copy; OpenStreetMap contributors',
        maxZoom: 19
      }).addTo(mapInstance.current);
    }
  }, [theme]); // This runs every time the theme changes

  return (
    <div className="home-container fade-in">
      {/* Search Header */}
      <div className="search-overlay">
        <div className="search-bar">
          <svg className="search-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><circle cx="11" cy="11" r="8"></circle><line x1="21" y1="21" x2="16.65" y2="16.65"></line></svg>
          <input type="text" placeholder="Search target location in Panabo..." />
        </div>
      </div>

      <div ref={mapRef} className="map-view"></div>

      {/* Dynamic Legend based on Theme */}
      <div className="map-legend" style={{ background: theme === 'dark' ? 'rgba(10, 10, 10, 0.85)' : 'rgba(255, 255, 255, 0.9)'}}>
        <h4 className="legend-title" style={{color: theme === 'dark' ? '#fff' : '#000'}}>Panabo Geodata</h4>
        <div className="legend-item">
          <span className="legend-color" style={{ background: '#f2dad9', border: '1px solid #e2caca' }}></span>
          <span className="legend-text" style={{color: theme === 'dark' ? '#a1a1aa' : '#4b5563'}}>Commercial/Retail Zone</span>
        </div>
        <div className="legend-item">
          <span className="legend-color" style={{ background: '#f6c467' }}></span>
          <span className="legend-text" style={{color: theme === 'dark' ? '#a1a1aa' : '#4b5563'}}>High Traffic (Main Roads)</span>
        </div>
        <div className="legend-item">
          <span className="legend-color" style={{ background: '#d9d0c9' }}></span>
          <span className="legend-text" style={{color: theme === 'dark' ? '#a1a1aa' : '#4b5563'}}>Infrastructure (Buildings)</span>
        </div>
        <div className="legend-item">
          <span className="legend-color" style={{ background: '#aad3df' }}></span>
          <span className="legend-text" style={{color: theme === 'dark' ? '#a1a1aa' : '#4b5563'}}>Water Hazard Proxy</span>
        </div>
      </div>

      {/* DYNAMIC ACTION BAR */}
      {selectedCoord && (
        <div className="map-action-bar">
          <button 
            className="primary-btn map-analyze-btn" 
            onClick={() => onMapTap(selectedCoord)}
          >
            <svg className="analyze-check-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round">
              <polyline points="20 6 9 17 4 12"></polyline>
            </svg>
            Analyze Site Viability
          </button>
        </div>
      )}
    </div>
  );
}