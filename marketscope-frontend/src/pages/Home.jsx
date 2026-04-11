import React, { useEffect, useRef, useState } from 'react';
import L from 'leaflet';
import 'leaflet/dist/leaflet.css';

// Fix for Vite + Leaflet default icon bug
delete L.Icon.Default.prototype._getIconUrl;
L.Icon.Default.mergeOptions({
  iconRetinaUrl: '', iconUrl: '', shadowUrl: ''
});

export default function Home({ onMapTap, theme }) {
  const mapRef = useRef(null);
  const mapInstance = useRef(null);
  const markerInstance = useRef(null);
  const tileLayerInstance = useRef(null);
  const [selectedCoord, setSelectedCoord] = useState(null);

  // 1. Initialize Map (Runs once)
  useEffect(() => {
    if (!mapInstance.current) {
      mapInstance.current = L.map(mapRef.current, {
        center: [7.3075, 125.6811], // Centered on Panabo
        zoom: 15,
        zoomControl: false 
      });

      // Handle map clicks
      mapInstance.current.on('click', (e) => {
        // Foolproof, self-contained inline-styled marker
        const customIcon = L.divIcon({
          className: 'clear-custom-pin',
          html: `<div style="
            width: 24px; 
            height: 24px; 
            background-color: #a855f7; 
            border: 3px solid white; 
            border-radius: 50%; 
            box-shadow: 0 0 10px rgba(0,0,0,0.5);
            transform: translate(-50%, -50%);
          "></div>`,
          iconSize: [24, 24],
          iconAnchor: [0, 0]
        });

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

  // 2. Handle Dark/Light Theme Switching dynamically
  useEffect(() => {
    if (mapInstance.current) {
      // Remove old tile layer to prevent stacking memory leaks
      if (tileLayerInstance.current) {
        mapInstance.current.removeLayer(tileLayerInstance.current);
      }

      // CARTO tiles are highly optimized for dashboards. Dark by default.
      const tileUrl = theme === 'light' 
        ? 'https://{s}.basemaps.cartocdn.com/rastertiles/voyager/{z}/{x}/{y}{r}.png'
        : 'https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png';

      tileLayerInstance.current = L.tileLayer(tileUrl, {
        attribution: '&copy; CARTO &copy; OpenStreetMap',
        maxZoom: 19
      }).addTo(mapInstance.current);
    }
  }, [theme]);

  return (
    <div className="home-container fade-in" style={{ height: '100%', position: 'relative' }}>
      
      {/* Search Header */}
      <div className="search-overlay" style={{ position: 'absolute', top: '20px', width: '100%', zIndex: 1000, padding: '0 20px' }}>
        <div className="search-bar" style={{ background: theme === 'dark' ? 'rgba(20,20,20,0.9)' : 'white', borderRadius: '12px', padding: '12px 20px', display: 'flex', alignItems: 'center', boxShadow: '0 4px 20px rgba(0,0,0,0.2)' }}>
          <svg viewBox="0 0 24 24" fill="none" stroke={theme === 'dark' ? '#a1a1aa' : '#666'} strokeWidth="2" style={{ width: '20px', height: '20px', marginRight: '10px' }}>
            <circle cx="11" cy="11" r="8"></circle>
            <line x1="21" y1="21" x2="16.65" y2="16.65"></line>
          </svg>
          <input 
            type="text" 
            placeholder="Search target location in Panabo..." 
            style={{ border: 'none', background: 'transparent', width: '100%', color: theme === 'dark' ? 'white' : 'black', outline: 'none' }}
          />
        </div>
      </div>

      {/* THE MAP (Enforced sizing) */}
      <div ref={mapRef} style={{ width: '100%', height: 'calc(100vh - 60px)', zIndex: 1 }}></div>

      {/* DYNAMIC ACTION BAR (Appears only when user clicks the map) */}
      {selectedCoord && (
        <div style={{ position: 'absolute', bottom: '80px', left: '50%', transform: 'translateX(-50%)', zIndex: 1000, width: '90%' }}>
          <button 
            className="primary-btn w-full" 
            style={{ padding: '16px', fontSize: '1.1rem', boxShadow: '0 8px 30px rgba(168, 85, 247, 0.4)' }}
            onClick={() => onMapTap(selectedCoord)}
          >
            Analyze Site Viability
          </button>
        </div>
      )}
    </div>
  );
}