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
  const [outOfBounds, setOutOfBounds] = useState(false);

  // Panabo City boundary (from updated PBF file)
  const PANABO_BOUNDS = {
    south: 7.269,
    north: 7.333,
    west: 125.636,
    east: 125.742
  };

  const isWithinBounds = (lat, lng) => {
    return lat >= PANABO_BOUNDS.south && lat <= PANABO_BOUNDS.north &&
           lng >= PANABO_BOUNDS.west && lng <= PANABO_BOUNDS.east;
  };

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

      // Add Panabo City boundary polygon (using bounding box as polygon)
      const boundaryCoords = [
        [PANABO_BOUNDS.south, PANABO_BOUNDS.west], // SW
        [PANABO_BOUNDS.south, PANABO_BOUNDS.east], // SE
        [PANABO_BOUNDS.north, PANABO_BOUNDS.east], // NE
        [PANABO_BOUNDS.north, PANABO_BOUNDS.west], // NW
        [PANABO_BOUNDS.south, PANABO_BOUNDS.west]  // back to SW to close polygon
      ];

      const boundary = L.polygon(boundaryCoords, {
        color: '#a855f7',
        weight: 3,
        opacity: 0.8,
        fill: false, // Remove fill, just outline
        dashArray: '5, 5'
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
        const { lat, lng } = e.latlng;
        
        if (!isWithinBounds(lat, lng)) {
          setOutOfBounds(true);
          setTimeout(() => setOutOfBounds(false), 3000);
          return;
        }

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
    <div className="home-container relative page-enter">
      {/* The map container (CSS will handle the dark mode inversion automatically) */}
      <div className="osm-map-wrapper" ref={mapRef} style={{ height: '100%', width: '100%', zIndex: 0 }}></div>
      
      {/* OUT OF BOUNDS WARNING */}
      {outOfBounds && (
        <div className="out-of-bounds-warning">
           Click within Panabo City boundary only
        </div>
      )}
      
      {/* NATIVE OSM LEGEND */}
      <div className="map-legend">
        <h4 className="legend-title">Panabo City Boundary</h4>
        <div className="legend-item">
          <span className="legend-color boundary-line"></span>
          <span className="legend-text">Scanning Area</span>
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
