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
  const [selectedCoord, setSelectedCoord] = useState(null);

  useEffect(() => {
    if (!mapInstance.current) {
      mapInstance.current = L.map(mapRef.current, {
        center: [7.3075, 125.6811],
        zoom: 15,
        zoomControl: false 
      });

      // Switch to the OFFICIAL OpenStreetMap Standard Tiles
      // This natively includes Commercial Zoning, Buildings, Roads, and Water bodies!
      L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
        attribution: '&copy; OpenStreetMap contributors',
        maxZoom: 19
      }).addTo(mapInstance.current);

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
  }, []);

  return (
    <div className="home-container relative">
      {/* The map container (CSS will handle the dark mode inversion automatically) */}
      <div className="osm-map-wrapper" ref={mapRef} style={{ height: '100%', width: '100%', zIndex: 0 }}></div>
      
      {/* NATIVE OSM LEGEND */}
      <div className="map-legend">
        <h4 className="legend-title">OSM Native Layers</h4>
        <div className="legend-item">
          <span className="legend-color" style={{ background: '#f2dad9', border: '1px solid #e2caca' }}></span>
          <span className="legend-text">Commercial/Retail Zone</span>
        </div>
        <div className="legend-item">
          <span className="legend-color" style={{ background: '#f6c467' }}></span>
          <span className="legend-text">High Traffic (Main Roads)</span>
        </div>
        <div className="legend-item">
          <span className="legend-color" style={{ background: '#d9d0c9' }}></span>
          <span className="legend-text">Infrastructure (Buildings)</span>
        </div>
        <div className="legend-item">
          <span className="legend-color" style={{ background: '#aad3df' }}></span>
          <span className="legend-text">Water Hazard Proxy</span>
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
            <span className="analyze-btn-text">Lock on this location</span>
          </button>
        </div>
      )}
    </div>
  );
}
