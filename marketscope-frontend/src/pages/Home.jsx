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

// Actual hazard zones from Davao del Norte NOAH 5-year flood return period shapefile
const FLOOD_ZONES = [
  { name: 'Very High Flood Hazard (5-Year)', bounds: [7.269, 125.636, 7.333, 125.742], score: 5 },
  { name: 'High Flood Hazard (5-Year)', bounds: [7.269, 125.636, 7.333, 125.73958735603416], score: 12 },
  { name: 'Moderate Flood Hazard (5-Year)', bounds: [7.269, 125.636, 7.333, 125.7389400572897], score: 18 }
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
    <div className="home-container relative page-enter">
      <div className="osm-map-wrapper" ref={mapRef} style={{ height: '100%', width: '100%', zIndex: 0 }} />

      {outOfBounds && (
        <div className="out-of-bounds-warning">
          Click within Panabo City boundary only
        </div>
      )}

      <div className="map-legend">
        <h4 className="legend-title">Panabo City Boundary</h4>
        <div className="legend-item">
          <span className="legend-color boundary-line"></span>
          <span className="legend-text">Scanning Area</span>
        </div>
        <div className="legend-item">
          <span className="legend-color flood-critical"></span>
          <span className="legend-text">Very High Flood Danger</span>
        </div>
        <div className="legend-item">
          <span className="legend-color flood-high"></span>
          <span className="legend-text">High Flood Danger</span>
        </div>
        <div className="legend-item">
          <span className="legend-color flood-moderate"></span>
          <span className="legend-text">Moderate Flood Danger</span>
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
