import React, { useEffect, useRef, useState } from 'react';
import L from 'leaflet';
import 'leaflet/dist/leaflet.css';

// Fix for Vite + Leaflet image bug
delete L.Icon.Default.prototype._getIconUrl;
L.Icon.Default.mergeOptions({
  iconRetinaUrl: '',
  iconUrl: '',
  shadowUrl: ''
});

const PANABO_BOUNDS = {
  south: 7.269,
  north: 7.333,
  west: 125.636,
  east: 125.742
};

const FLOOD_ZONES = [
  { name: 'Very High Flood Susceptibility', bounds: [7.3080, 125.6750, 7.3120, 125.6800], score: 0 },
  { name: 'High Flood Susceptibility', bounds: [7.3050, 125.6720, 7.3140, 125.6850], score: 10 },
  { name: 'Moderate Flood Susceptibility', bounds: [7.2990, 125.6700, 7.3150, 125.6860], score: 18 }
];

export default function Home({ onMapTap }) {
  const mapRef = useRef(null);
  const mapInstance = useRef(null);
  const hazardLayerGroup = useRef(null);
  const hazardLayersRef = useRef([]);
  const selectedMarkerRef = useRef(null);
  const [selectedCoord, setSelectedCoord] = useState(null);
  const [mapViewMode, setMapViewMode] = useState('normal');
  const [outOfBounds, setOutOfBounds] = useState(false);

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

      L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
        attribution: '&copy; OpenStreetMap contributors',
        maxZoom: 19
      }).addTo(mapInstance.current);

      const boundaryCoords = [
        [PANABO_BOUNDS.south, PANABO_BOUNDS.west],
        [PANABO_BOUNDS.south, PANABO_BOUNDS.east],
        [PANABO_BOUNDS.north, PANABO_BOUNDS.east],
        [PANABO_BOUNDS.north, PANABO_BOUNDS.west],
        [PANABO_BOUNDS.south, PANABO_BOUNDS.west]
      ];

      L.polygon(boundaryCoords, {
        color: '#a855f7',
        weight: 3,
        opacity: 0.8,
        fill: false,
        dashArray: '5, 5'
      }).addTo(mapInstance.current);

      hazardLayerGroup.current = L.layerGroup().addTo(mapInstance.current);
      hazardLayersRef.current = [];

      FLOOD_ZONES.forEach((zone) => {
        const [south, west, north, east] = zone.bounds;
        const rectangle = L.rectangle(
          [[south, west], [north, east]],
          {
            color: zone.score <= 0 ? '#dc2626' : zone.score <= 10 ? '#f97316' : '#f59e0b',
            weight: zone.score <= 0 ? 2.5 : 1.5,
            fillColor: zone.score <= 0 ? '#ef4444' : zone.score <= 10 ? '#fb7185' : '#fbbf24',
            fillOpacity: zone.score <= 0 ? 0.26 : zone.score <= 10 ? 0.18 : 0.12,
            opacity: zone.score <= 0 ? 0.95 : 0.82,
            dashArray: zone.score <= 0 ? null : '6 6'
          }
        );

        hazardLayersRef.current.push(rectangle);
      });

      mapInstance.current.on('click', (e) => {
        const { lat, lng } = e.latlng;

        if (!isWithinBounds(lat, lng)) {
          setOutOfBounds(true);
          setTimeout(() => setOutOfBounds(false), 3000);
          return;
        }

        setSelectedCoord(e.latlng);
        mapInstance.current.panTo(e.latlng);
      });
    }

    return () => {
      if (selectedMarkerRef.current) {
        selectedMarkerRef.current.remove();
        selectedMarkerRef.current = null;
      }
      hazardLayerGroup.current = null;
      hazardLayersRef.current = [];
      if (mapInstance.current) {
        mapInstance.current.remove();
        mapInstance.current = null;
      }
    };
  }, []);

  useEffect(() => {
    if (!mapInstance.current || !hazardLayerGroup.current) return;

    hazardLayersRef.current.forEach((layer) => {
      const onMap = mapInstance.current.hasLayer(layer);
      if (mapViewMode === 'flood' && !onMap) {
        layer.addTo(hazardLayerGroup.current);
      } else if (mapViewMode !== 'flood' && onMap) {
        hazardLayerGroup.current.removeLayer(layer);
      }
    });
  }, [mapViewMode]);

  useEffect(() => {
    if (!mapInstance.current) return;

    if (selectedMarkerRef.current) {
      selectedMarkerRef.current.remove();
      selectedMarkerRef.current = null;
    }

    if (!selectedCoord) return;

    const selectedMarker = L.marker(selectedCoord, {
      icon: L.divIcon({
        className: 'custom-selected-marker',
        html: `
          <div class="pure-css-mark">
            <div class="pure-pulse"></div>
            <div class="pure-ring"></div>
            <svg class="pure-pin" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
              <path d="M12 2C8.14 2 5 5.14 5 9c0 4.38 4.62 9.44 6.29 11.16.37.38.98.38 1.35 0C14.38 18.44 19 13.38 19 9c0-3.86-3.14-7-7-7zm0 9.5A2.5 2.5 0 1 1 12 6a2.5 2.5 0 0 1 0 5.5z"></path>
            </svg>
          </div>
        `,
        iconSize: [40, 40],
        iconAnchor: [20, 36]
      })
    }).addTo(mapInstance.current);

    selectedMarkerRef.current = selectedMarker;

    return () => {
      if (selectedMarkerRef.current) {
        selectedMarkerRef.current.remove();
        selectedMarkerRef.current = null;
      }
    };
  }, [selectedCoord]);

  return (
    <div className="home-container relative page-enter overflow-hidden bg-[radial-gradient(circle_at_top_left,rgba(168,85,247,0.12),transparent_30%),radial-gradient(circle_at_bottom_right,rgba(14,165,233,0.08),transparent_26%)]">
      <div className="osm-map-wrapper" ref={mapRef} style={{ height: '100%', width: '100%', zIndex: 0 }} />

      {outOfBounds && (
        <div className="out-of-bounds-warning rounded-full border border-red-300/25 bg-red-500 px-5 py-3 text-center text-sm font-semibold text-white shadow-[0_12px_30px_rgba(239,68,68,0.28)]">
          Click within Panabo City boundary only
        </div>
      )}

      <div className="map-legend rounded-2xl border border-white/10 bg-slate-950/75 p-4 shadow-[0_18px_40px_rgba(2,6,23,0.35)] backdrop-blur-xl">
        <h4 className="legend-title mb-3 text-[0.72rem] font-bold uppercase tracking-[0.16em] text-slate-400">Panabo City Boundary</h4>
        <div className="legend-item flex items-center gap-3 py-1.5">
          <span className="legend-color boundary-line"></span>
          <span className="legend-text text-sm font-medium text-slate-100">Scanning Area</span>
        </div>
        <div className="legend-item flex items-center gap-3 py-1.5">
          <span className="legend-color flood-critical"></span>
          <span className="legend-text text-sm font-medium text-slate-100">Very High Flood Danger</span>
        </div>
        <div className="legend-item flex items-center gap-3 py-1.5">
          <span className="legend-color flood-high"></span>
          <span className="legend-text text-sm font-medium text-slate-100">High Flood Danger</span>
        </div>
        <div className="legend-item flex items-center gap-3 py-1.5">
          <span className="legend-color flood-moderate"></span>
          <span className="legend-text text-sm font-medium text-slate-100">Moderate Flood Danger</span>
        </div>
      </div>

      <div className="map-mode-toggle" role="tablist" aria-label="Map view mode">
        <button
          type="button"
          className={`map-mode-btn ${mapViewMode === 'normal' ? 'active' : ''}`}
          onClick={() => setMapViewMode('normal')}
        >
          Normal Map
        </button>
        <button
          type="button"
          className={`map-mode-btn ${mapViewMode === 'flood' ? 'active' : ''}`}
          onClick={() => setMapViewMode('flood')}
        >
          Flood Zones
        </button>
      </div>

      {selectedCoord && (
        <div className="map-action-bar rounded-full border border-white/10 bg-slate-950/80 p-2 shadow-[0_20px_50px_rgba(2,6,23,0.35)] backdrop-blur-xl">
          <button
            className="primary-btn map-analyze-btn flex items-center gap-3 rounded-full bg-gradient-to-r from-violet-600 via-violet-500 to-fuchsia-500 px-4 py-4 text-white shadow-[0_14px_34px_rgba(168,85,247,0.35)] transition hover:-translate-y-0.5"
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
