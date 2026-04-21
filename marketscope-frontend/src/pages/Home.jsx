import React, { useEffect, useRef, useState } from 'react';
import L from 'leaflet';
import 'leaflet/dist/leaflet.css';
import { apiUrl } from '../api';

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

const hazardNameByVar = {
  1: 'Very High Flood Hazard (5-Year)',
  2: 'High Flood Hazard (5-Year)',
  3: 'Moderate Flood Hazard (5-Year)'
};

const getHazardStyle = (hazardVar) => {
  if (hazardVar === 1) {
    return {
      color: '#dc2626',
      weight: 2.5,
      fillColor: '#ef4444',
      fillOpacity: 0.28,
      opacity: 0.95
    };
  }
  if (hazardVar === 2) {
    return {
      color: '#f97316',
      weight: 1.7,
      fillColor: '#fb7185',
      fillOpacity: 0.2,
      opacity: 0.85,
      dashArray: '6 6'
    };
  }
  return {
    color: '#f59e0b',
    weight: 1.5,
    fillColor: '#fbbf24',
    fillOpacity: 0.14,
    opacity: 0.8,
    dashArray: '6 6'
  };
};

export default function Home({ onMapTap }) {
  const mapRef = useRef(null);
  const mapInstance = useRef(null);
  const hazardLayerGroup = useRef(null);
  const hazardGeoJsonLayerRef = useRef(null);
  const spaceMarkerLayerGroup = useRef(null);
  const spaceHoverTimers = useRef(new Map());
  const selectedMarkerRef = useRef(null);
  const [selectedCoord, setSelectedCoord] = useState(null);
  const [mapViewMode, setMapViewMode] = useState('normal');
  const mapViewModeRef = useRef('normal');
  const [outOfBounds, setOutOfBounds] = useState(false);

  const getSpaceMarkerTone = (marker) => {
    const sourceType = String(marker?.source_type || '').toLowerCase();
    const guarantee = String(marker?.guarantee_level || '').toLowerCase();

    if (sourceType === 'user') return 'user-guaranteed';
    if (guarantee === 'guaranteed') return 'admin-guaranteed';
    return 'admin-potential';
  };

  const createSpaceMarkerIcon = (marker) => {
    const tone = getSpaceMarkerTone(marker);
    const glyph = tone === 'user-guaranteed' ? 'U' : tone === 'admin-guaranteed' ? 'A' : 'P';
    const badge = tone === 'admin-potential' ? '?' : 'OK';

    return L.divIcon({
      className: 'space-marker-icon-wrapper',
      html: `
        <div class="space-marker space-marker--${tone}">
          <span class="space-marker__glyph">${glyph}</span>
          <span class="space-marker__badge">${badge}</span>
        </div>
      `,
      iconSize: [34, 34],
      iconAnchor: [17, 32],
      tooltipAnchor: [0, -26],
    });
  };

  const buildMarkerBrief = (marker) => {
    const listingMode = String(marker?.listing_mode || '').toLowerCase();
    const modeLabel = listingMode === 'buy' ? 'For Buy' : 'For Rent';
    const sourceLabel = marker?.source_type === 'user' ? 'User Guaranteed' : marker?.guarantee_level === 'guaranteed' ? 'Admin Guaranteed' : 'Admin Potential';
    const priceMin = Number(marker?.price_min || 0);
    const priceMax = Number(marker?.price_max || 0);
    let priceLabel = 'Price not set';

    if (priceMin > 0 && priceMax > 0) {
      priceLabel = `PHP ${priceMin.toLocaleString()} - PHP ${priceMax.toLocaleString()}`;
    } else if (priceMin > 0) {
      priceLabel = `From PHP ${priceMin.toLocaleString()}`;
    } else if (priceMax > 0) {
      priceLabel = `Up to PHP ${priceMax.toLocaleString()}`;
    }

    const title = marker?.title || 'Space listing';
    return `<strong>${title}</strong><br/>${modeLabel} | ${sourceLabel}<br/>${priceLabel}`;
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
      spaceMarkerLayerGroup.current = L.layerGroup().addTo(mapInstance.current);

      fetch(apiUrl('/spaces/map-markers'))
        .then((response) => {
          if (!response.ok) {
            throw new Error('Unable to load map space markers');
          }
          return response.json();
        })
        .then((data) => {
          if (!spaceMarkerLayerGroup.current || !mapInstance.current) return;
          const markers = Array.isArray(data?.markers) ? data.markers : [];

          markers.forEach((item) => {
            const lat = Number(item?.latitude);
            const lng = Number(item?.longitude);
            if (!Number.isFinite(lat) || !Number.isFinite(lng)) return;

            const marker = L.marker([lat, lng], { icon: createSpaceMarkerIcon(item) }).addTo(spaceMarkerLayerGroup.current);
            marker.bindTooltip(buildMarkerBrief(item), {
              className: 'space-brief-tooltip',
              direction: 'top',
              sticky: false,
              opacity: 1,
            });

            marker.on('mouseover', () => {
              const timer = window.setTimeout(() => {
                marker.openTooltip();
              }, 1500);
              spaceHoverTimers.current.set(marker._leaflet_id, timer);
            });

            marker.on('mouseout', () => {
              const timer = spaceHoverTimers.current.get(marker._leaflet_id);
              if (timer) {
                window.clearTimeout(timer);
                spaceHoverTimers.current.delete(marker._leaflet_id);
              }
              marker.closeTooltip();
            });

            marker.on('click', () => {
              const timer = spaceHoverTimers.current.get(marker._leaflet_id);
              if (timer) {
                window.clearTimeout(timer);
                spaceHoverTimers.current.delete(marker._leaflet_id);
              }
              const coords = { lat, lng };
              setSelectedCoord(coords);
              mapInstance.current.panTo([lat, lng]);
              onMapTap(coords, {
                prefillBusinessType: item?.business_type || '',
              });
            });
          });
        })
        .catch(() => {
          // Keep map usable even if marker feed is temporarily unavailable.
        });

      fetch('/panabo_hazard_5yr.geojson')
        .then((response) => {
          if (!response.ok) {
            throw new Error('Unable to load hazard zone layer');
          }
          return response.json();
        })
        .then((geojson) => {
          if (!mapInstance.current || !hazardLayerGroup.current) return;

          const layer = L.geoJSON(geojson, {
            style: (feature) => {
              const hazardVar = Number(feature?.properties?.Var);
              return getHazardStyle(hazardVar);
            },
            onEachFeature: (feature, layerInstance) => {
              const hazardVar = Number(feature?.properties?.Var);
              const zoneName = hazardNameByVar[hazardVar] || 'Flood Hazard Zone';
              layerInstance.bindTooltip(zoneName, {
                className: 'hazard-zone-tooltip'
              });
            }
          });

          hazardGeoJsonLayerRef.current = layer;

          if (mapViewModeRef.current === 'flood') {
            layer.addTo(hazardLayerGroup.current);
          }
        })
        .catch((error) => {
          console.error(error);
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

      if (spaceMarkerLayerGroup.current) {
        spaceMarkerLayerGroup.current.clearLayers();
        spaceMarkerLayerGroup.current = null;
      }

      spaceHoverTimers.current.forEach((timer) => window.clearTimeout(timer));
      spaceHoverTimers.current.clear();

      hazardLayerGroup.current = null;
      hazardGeoJsonLayerRef.current = null;
      if (mapInstance.current) {
        mapInstance.current.remove();
        mapInstance.current = null;
      }
    };
  }, []);

  useEffect(() => {
    mapViewModeRef.current = mapViewMode;

    if (!mapInstance.current || !hazardLayerGroup.current || !hazardGeoJsonLayerRef.current) return;

    const layer = hazardGeoJsonLayerRef.current;
    const onMap = mapInstance.current.hasLayer(layer);

    if (mapViewMode === 'flood' && !onMap) {
      layer.addTo(hazardLayerGroup.current);
    } else if (mapViewMode !== 'flood' && onMap) {
      hazardLayerGroup.current.removeLayer(layer);
    }
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
        <div className="legend-item">
          <span className="legend-color space-user-guaranteed"></span>
          <span className="legend-text">User Guaranteed Space</span>
        </div>
        <div className="legend-item">
          <span className="legend-color space-admin-guaranteed"></span>
          <span className="legend-text">Admin Guaranteed Space</span>
        </div>
        <div className="legend-item">
          <span className="legend-color space-admin-potential"></span>
          <span className="legend-text">Admin Potential Space</span>
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
