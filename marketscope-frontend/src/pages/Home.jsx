import React, { useEffect, useRef, useState } from 'react';
import L from 'leaflet';
import 'leaflet/dist/leaflet.css';
import { apiUrl } from '../api';
import { BUSINESS_TYPE_OPTIONS } from '../utils/businessTypes';

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

export default function Home({ onMapTap, userId }) {
  const mapRef = useRef(null);
  const mapInstance = useRef(null);
  const hazardLayerGroup = useRef(null);
  const hazardGeoJsonLayerRef = useRef(null);
  const selectedMarkerRef = useRef(null);
  const competitorLayerGroup = useRef(null);
  const competitorCircleRef = useRef(null);
  const previewRequestIdRef = useRef(0);
  const [selectedCoord, setSelectedCoord] = useState(null);
  const [mapViewMode, setMapViewMode] = useState('normal');
  const mapViewModeRef = useRef('normal');
  const [outOfBounds, setOutOfBounds] = useState(false);
  const [previewBusinessType, setPreviewBusinessType] = useState('');
  const [previewRadius, setPreviewRadius] = useState(500);
  const [competitorLocations, setCompetitorLocations] = useState([]);
  const [previewLoading, setPreviewLoading] = useState(false);
  const [previewMessage, setPreviewMessage] = useState('Drop a pin, then choose an MSME and radius to preview competitors.');
  const [previewError, setPreviewError] = useState('');
  const [previewCollapsed, setPreviewCollapsed] = useState(false);
  const [locationUpdated, setLocationUpdated] = useState(false);

  const createCompetitorIcon = (name) => {
    const initials = String(name || 'C').trim().slice(0, 1).toUpperCase();

    return L.divIcon({
      className: 'competitor-marker-icon-wrapper',
      html: `
        <div class="competitor-marker">
          <span class="competitor-marker__pulse"></span>
          <span class="competitor-marker__core">${initials}</span>
        </div>
      `,
      iconSize: [32, 32],
      iconAnchor: [16, 30],
      tooltipAnchor: [0, -22]
    });
  };

  const isWithinBounds = (lat, lng) => {
    return lat >= PANABO_BOUNDS.south && lat <= PANABO_BOUNDS.north &&
           lng >= PANABO_BOUNDS.west && lng <= PANABO_BOUNDS.east;
  };

  const getDistanceMeters = (lat1, lon1, lat2, lon2) => {
    const earthRadius = 6371000;
    const toRadians = (value) => (value * Math.PI) / 180;
    const deltaLat = toRadians(lat2 - lat1);
    const deltaLon = toRadians(lon2 - lon1);
    const a = Math.sin(deltaLat / 2) ** 2 + Math.cos(toRadians(lat1)) * Math.cos(toRadians(lat2)) * Math.sin(deltaLon / 2) ** 2;
    return 2 * earthRadius * Math.asin(Math.sqrt(a));
  };

  useEffect(() => {
    if (!mapInstance.current) {
      mapInstance.current = L.map(mapRef.current, {
        center: [7.3075, 125.6811],
        zoom: 15,
        zoomControl: false
      });

      mapInstance.current.createPane('previewPane');
      mapInstance.current.getPane('previewPane').style.zIndex = 450;

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
      competitorLayerGroup.current = L.layerGroup().addTo(mapInstance.current);

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
          setCompetitorLocations([]);
          setPreviewError('');
          setPreviewMessage(previewBusinessType ? 'Adjust the radius or choose another MSME to preview competitors.' : 'Choose an MSME and radius to preview competitors.');
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
        setLocationUpdated(true);
        if (competitorLayerGroup.current) {
          competitorLayerGroup.current.clearLayers();
        }
        if (competitorCircleRef.current) {
          competitorCircleRef.current.remove();
          competitorCircleRef.current = null;
        }
        mapInstance.current.panTo(e.latlng);
      });
    }

    return () => {
      if (selectedMarkerRef.current) {
        selectedMarkerRef.current.remove();
        selectedMarkerRef.current = null;
      }

      if (competitorLayerGroup.current) {
        competitorLayerGroup.current.clearLayers();
        competitorLayerGroup.current = null;
      }

      if (competitorCircleRef.current) {
        competitorCircleRef.current.remove();
        competitorCircleRef.current = null;
      }

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

  useEffect(() => {
    if (!mapInstance.current || !selectedCoord) return;

    if (competitorCircleRef.current) {
      competitorCircleRef.current.remove();
      competitorCircleRef.current = null;
    }

    competitorCircleRef.current = L.circle([selectedCoord.lat, selectedCoord.lng], {
      radius: previewRadius,
      pane: 'previewPane',
      color: '#ffffff',
      weight: 4,
      opacity: 1,
      fillColor: '#a855f7',
      fillOpacity: 0.14,
      dashArray: '10 8'
    }).addTo(mapInstance.current);

    return () => {
      if (competitorCircleRef.current) {
        competitorCircleRef.current.remove();
        competitorCircleRef.current = null;
      }
    };
  }, [selectedCoord, previewRadius]);

  useEffect(() => {
    if (!mapInstance.current || !competitorLayerGroup.current || !selectedCoord) return;

    competitorLayerGroup.current.clearLayers();

    if (!previewBusinessType) {
      setPreviewLoading(false);
      setPreviewMessage('Choose an MSME and radius to preview competitors.');
      setCompetitorLocations([]);
      return;
    }

    let isActive = true;
    const requestId = ++previewRequestIdRef.current;

    const runPreview = async () => {
      setPreviewLoading(true);
      setPreviewError('');
      setPreviewMessage('Scanning nearby competitors...');

      try {
        const response = await fetch(apiUrl('/analyze'), {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            lat: selectedCoord.lat,
            lon: selectedCoord.lng,
            business_type: previewBusinessType,
            radius: previewRadius,
            user_id: userId || null
          })
        });

        const data = await response.json();
        if (!response.ok) {
          throw new Error(data?.detail || 'Unable to preview competitors');
        }
        if (!isActive || requestId !== previewRequestIdRef.current) return;

        const competitors = Array.isArray(data?.competitor_locations)
          ? data.competitor_locations.filter((item) => {
              const lat = Number(item?.lat);
              const lon = Number(item?.lon);
              if (!Number.isFinite(lat) || !Number.isFinite(lon)) return false;
              return getDistanceMeters(selectedCoord.lat, selectedCoord.lng, lat, lon) <= previewRadius;
            })
          : [];
        setCompetitorLocations(competitors);
        setPreviewMessage(competitors.length > 0 ? `Found ${competitors.length} nearby competitors.` : 'No competitors found in this radius.');
      } catch (error) {
        if (!isActive || requestId !== previewRequestIdRef.current) return;
        setCompetitorLocations([]);
        setPreviewError(error.message || 'Unable to preview competitors.');
        setPreviewMessage('Unable to preview competitors.');
      } finally {
        if (isActive && requestId === previewRequestIdRef.current) {
          setPreviewLoading(false);
        }
      }
    };

    runPreview();

    return () => {
      isActive = false;
    };
  }, [selectedCoord, previewBusinessType, previewRadius, userId]);

  useEffect(() => {
    if (!mapInstance.current || !competitorLayerGroup.current) return;

    competitorLayerGroup.current.clearLayers();

    competitorLocations.forEach((item) => {
      const lat = Number(item?.lat);
      const lng = Number(item?.lon);
      if (!Number.isFinite(lat) || !Number.isFinite(lng)) return;

      const marker = L.marker([lat, lng], { icon: createCompetitorIcon(item?.name), pane: 'previewPane' }).addTo(competitorLayerGroup.current);
      marker.bindTooltip(item?.name || 'Competitor', {
        className: 'competitor-name-tooltip',
        direction: 'top',
        sticky: false,
        opacity: 1
      });
    });
  }, [competitorLocations]);

  useEffect(() => {
    if (!locationUpdated) return;
    const timer = setTimeout(() => setLocationUpdated(false), 400);
    return () => clearTimeout(timer);
  }, [locationUpdated]);

  return (
    <div className={`home-container relative page-enter ${mapViewMode}-mode`} data-map-mode={mapViewMode}>
      <div className="osm-map-wrapper" ref={mapRef} style={{ height: '100%', width: '100%', zIndex: 0 }} />

      {outOfBounds && (
        <div className="out-of-bounds-warning">
          Click within Panabo City boundary only
        </div>
      )}

      {selectedCoord && (
        <div
          className={`map-quick-panel data-card ${previewCollapsed ? 'is-collapsed' : ''} ${locationUpdated ? 'location-updated' : ''}`}
          onClick={() => previewCollapsed && setPreviewCollapsed(false)}
          style={{ cursor: previewCollapsed ? 'pointer' : 'default' }}
        >
          <div className="map-quick-panel__top">
            {previewCollapsed ? (
              <div className="map-quick-panel__compact-view">
                <p className="map-quick-panel__coords">{selectedCoord.lat.toFixed(5)}, {selectedCoord.lng.toFixed(5)}</p>
                {previewBusinessType && (
                  <p className="map-quick-panel__msme-label">
                    {BUSINESS_TYPE_OPTIONS.find((opt) => opt.value === previewBusinessType)?.label || previewBusinessType}
                  </p>
                )}
              </div>
            ) : (
              <div>
                <h3 className="section-heading" style={{ marginBottom: 4 }}>Competitor Preview</h3>
                <p className="map-quick-panel__coords">{selectedCoord.lat.toFixed(5)}, {selectedCoord.lng.toFixed(5)}</p>
              </div>
            )}
            <button
              type="button"
              className="map-quick-panel__toggle"
              onClick={(e) => {
                e.stopPropagation();
                setPreviewCollapsed((current) => !current);
              }}
              aria-label={previewCollapsed ? 'Expand preview panel' : 'Collapse preview panel'}
            >
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
                <path d={previewCollapsed ? 'M6 9l6 6 6-6' : 'M6 15l6-6 6 6'} stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
              </svg>
            </button>
          </div>

          {!previewCollapsed && (
            <>
              <div className="input-group">
                <label className="input-label">Select MSME</label>
                <select className="styled-select" value={previewBusinessType} onChange={(event) => setPreviewBusinessType(event.target.value)}>
                  <option value="">Choose an MSME...</option>
                  {BUSINESS_TYPE_OPTIONS.map((option) => (
                    <option key={option.value} value={option.value}>{option.label}</option>
                  ))}
                </select>
              </div>

              <div className="input-group">
                <label className="input-label">Radius</label>
                <input
                  type="range"
                  min="100"
                  max="1500"
                  step="50"
                  value={previewRadius}
                  onChange={(event) => setPreviewRadius(Number(event.target.value))}
                  className="radius-slider"
                />
                <div className="radius-slider-meta">
                  <span>100m</span>
                  <b>{previewRadius}m</b>
                  <span>1500m</span>
                </div>
              </div>

              <div className="map-quick-panel__summary">
                {previewLoading ? 'Scanning nearby competitors...' : previewMessage}
              </div>

              {previewError && <div className="error-alert" style={{ marginTop: 0 }}>{previewError}</div>}

              <div className="map-quick-panel__actions">
                <button
                  type="button"
                  className="primary-btn"
                  disabled={!previewBusinessType || previewLoading}
                  onClick={() => onMapTap(selectedCoord, { prefillBusinessType: previewBusinessType, prefillRadius: previewRadius })}
                >
                  Open Full Report
                </button>
              </div>
            </>
          )}
        </div>
      )}

      {/* Map legend: show flood-related indicators only when in flood mode, otherwise show space/boundary indicators */}
      {mapViewMode === 'flood' ? (
        <div className="map-legend" aria-hidden={mapViewMode !== 'flood'}>
          <h4 className="legend-title">Flood Zones</h4>
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
      ) : (
        <div className="map-legend" aria-hidden={mapViewMode !== 'normal'}>
          <h4 className="legend-title">Panabo City Boundary</h4>
          <div className="legend-item">
            <span className="legend-color boundary-line"></span>
            <span className="legend-text">Scanning Area</span>
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
          {selectedCoord && competitorLocations.length > 0 && (
            <div className="legend-item">
              <span className="legend-color competitor-preview"></span>
              <span className="legend-text">Preview Competitors</span>
            </div>
          )}
        </div>
      )}

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

    </div>
  );
}
