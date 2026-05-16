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
  const spaceMarkerLayerGroup = useRef(null);
  const spaceHoverTimers = useRef(new Map());
  const selectedMarkerRef = useRef(null);
  const competitorLayerGroup = useRef(null);
  const competitorCircleRef = useRef(null);
  const previewRequestIdRef = useRef(0);
  const [selectedCoord, setSelectedCoord] = useState(null);
  const [selectedSpaceMarker, setSelectedSpaceMarker] = useState(null);
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
  const [selectedSpacePhotoIndex, setSelectedSpacePhotoIndex] = useState(0);

  const normalizePhotoUrls = (marker) => {
    const rawPhotos = Array.isArray(marker?.photo_urls) ? marker.photo_urls : [];
    return rawPhotos.filter(Boolean).slice(0, 4);
  };

  const selectedSpacePhotos = normalizePhotoUrls(selectedSpaceMarker);
  const selectedSpacePhotoUrl = selectedSpacePhotos[selectedSpacePhotoIndex] || selectedSpacePhotos[0] || '';

  const formatSpacePrice = (marker) => {
    const priceMin = Number(marker?.price_min || 0);
    const priceMax = Number(marker?.price_max || 0);

    if (priceMin > 0 && priceMax > 0) {
      return `PHP ${priceMin.toLocaleString()} - PHP ${priceMax.toLocaleString()}`;
    }

    if (priceMin > 0) {
      return `From PHP ${priceMin.toLocaleString()}`;
    }

    if (priceMax > 0) {
      return `Up to PHP ${priceMax.toLocaleString()}`;
    }

    return 'Price not set';
  };

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
      tooltipAnchor: [0, -26]
    });
  };

  const buildMarkerBrief = (marker) => {
    const listingMode = String(marker?.listing_mode || '').toLowerCase();
    const modeLabel = listingMode === 'buy' ? 'For Sale' : 'For Rent';
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
      spaceMarkerLayerGroup.current = L.layerGroup().addTo(mapInstance.current);
      competitorLayerGroup.current = L.layerGroup().addTo(mapInstance.current);

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
              opacity: 1
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
              setSelectedSpaceMarker({
                ...item,
                latitude: lat,
                longitude: lng,
                photo_urls: normalizePhotoUrls(item)
              });
              mapInstance.current.panTo([lat, lng]);
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
        setSelectedSpaceMarker(null);
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

      if (spaceMarkerLayerGroup.current) {
        spaceMarkerLayerGroup.current.clearLayers();
        spaceMarkerLayerGroup.current = null;
      }

      spaceHoverTimers.current.forEach((timer) => window.clearTimeout(timer));
      spaceHoverTimers.current.clear();

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
    setSelectedSpacePhotoIndex(0);
  }, [selectedSpaceMarker]);

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
    if (!selectedSpaceMarker) return;
    const timer = setTimeout(() => setLocationUpdated(false), 120);
    return () => clearTimeout(timer);
  }, [selectedSpaceMarker]);

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

      {selectedSpaceMarker && selectedCoord && (
        <div className="space-detail-overlay" onClick={() => setSelectedSpaceMarker(null)} role="presentation">
          <div className="space-detail-card" onClick={(event) => event.stopPropagation()} role="dialog" aria-modal="true" aria-label="Space details">
            <button type="button" className="space-detail-close" onClick={() => setSelectedSpaceMarker(null)} aria-label="Close space details">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M18 6L6 18"></path><path d="M6 6L18 18"></path></svg>
            </button>

            <div className="space-detail-scroll">
              <div className="space-detail-media">
                {selectedSpacePhotos.length > 0 ? (
                  <div className="space-detail-photo-shell">
                    <div className="space-detail-photo-stage">
                      <img src={selectedSpacePhotoUrl} alt={`${selectedSpaceMarker.title || 'Space'} photo ${selectedSpacePhotoIndex + 1}`} />
                    </div>
                    <div className="space-detail-photo-strip" role="list" aria-label="Space photos">
                      {selectedSpacePhotos.map((photoUrl, index) => (
                        <button
                          key={`${photoUrl}-${index}`}
                          type="button"
                          className={`space-detail-photo-thumb ${selectedSpacePhotoIndex === index ? 'is-active' : ''}`}
                          onClick={() => setSelectedSpacePhotoIndex(index)}
                          aria-label={`View photo ${index + 1}`}
                        >
                          <img src={photoUrl} alt={`${selectedSpaceMarker.title || 'Space'} thumbnail ${index + 1}`} />
                        </button>
                      ))}
                    </div>
                  </div>
                ) : (
                  <div className="space-detail-photo-empty">No photos uploaded</div>
                )}
              </div>

              <div className="space-detail-body">
                <div className="space-detail-header">
                  <div>
                    <p className="space-detail-kicker">{selectedSpaceMarker.listing_mode === 'buy' ? 'For Sale' : 'For Rent'}</p>
                    <h3>{selectedSpaceMarker.title || 'Space listing'}</h3>
                  </div>
                  <span className={`space-detail-chip space-detail-chip--${getSpaceMarkerTone(selectedSpaceMarker)}`}>
                    {selectedSpaceMarker.source_type === 'user' ? 'User' : 'Admin'}
                  </span>
                </div>

                <div className="space-detail-grid">
                  <div><span>Property</span><strong>{selectedSpaceMarker.property_type || 'Not specified'}</strong></div>
                  <div><span>Category</span><strong>{selectedSpaceMarker.business_type || 'Not specified'}</strong></div>
                  <div><span>Coordinates</span><strong>{Number(selectedSpaceMarker.latitude).toFixed(5)}, {Number(selectedSpaceMarker.longitude).toFixed(5)}</strong></div>
                  <div><span>Price</span><strong>{formatSpacePrice(selectedSpaceMarker)}</strong></div>
                </div>

                <div className="space-detail-list">
                  <p><span>Address:</span> {selectedSpaceMarker.address_text || 'Not provided'}</p>
                  <p><span>Contact:</span> {selectedSpaceMarker.contact_info || 'Not provided'}</p>
                  <p><span>Notes:</span> {selectedSpaceMarker.notes || 'No notes added.'}</p>
                </div>
              </div>
            </div>

            <div className="space-detail-actions">
              <button
                type="button"
                className="primary-btn"
                onClick={() => {
                  onMapTap({ lat: Number(selectedSpaceMarker.latitude), lng: Number(selectedSpaceMarker.longitude) }, {
                    prefillBusinessType: selectedSpaceMarker.business_type || '',
                    prefillRadius: previewRadius
                  });
                  setSelectedSpaceMarker(null);
                }}
              >
                Next
              </button>
            </div>
          </div>
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
