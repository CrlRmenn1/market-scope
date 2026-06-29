import React, { useEffect, useRef, useState } from 'react';
import L from 'leaflet';
import ZoningEditor from './ZoningEditor';
import { apiUrl } from '../api';
import './ZoningManager.css';

const FLOOD_PREVIEW_URL = '/panabo_hazard_5yr.geojson';

const isFloodRelevantLayer = (layer) => {
  const haystack = `${layer?.name || ''} ${layer?.source_note || ''}`.toLowerCase();
  return haystack.includes('flood') || haystack.includes('hazard');
};

const isClupRelevantLayer = (layer) => {
  const haystack = `${layer?.name || ''} ${layer?.source_note || ''}`.toLowerCase();
  return haystack.includes('clup') || haystack.includes('zoning') || !isFloodRelevantLayer(layer);
};

export default function FloodZoneManager({ token }) {
  const mapRef = useRef(null);
  const containerRef = useRef(null);
  const layerRef = useRef(null);
  const [layers, setLayers] = useState([]);
  const [loading, setLoading] = useState(false);
  const [showEditor, setShowEditor] = useState(false);
  const [panelMode, setPanelMode] = useState('clup');
  const [clupGeoJSON, setClupGeoJSON] = useState(null);
  const [floodEditableGeoJSON, setFloodEditableGeoJSON] = useState(null);
  const [floodGeoJSON, setFloodGeoJSON] = useState(null);
  const [clupUploadName, setClupUploadName] = useState('CLUP Flood Zone');
  const [floodUploadName, setFloodUploadName] = useState('Flood Prone Area');

  const loadFloodOverlay = async () => {
    try {
      const response = await fetch(FLOOD_PREVIEW_URL);
      const data = await response.json();
      setFloodGeoJSON(data);
    } catch (error) {
      console.warn('Failed to load flood overlay', error);
    }
  };

  useEffect(() => {
    if (!containerRef.current) return;

    const map = L.map(containerRef.current, { center: [7.3109675, 125.6853653], zoom: 13 });
    L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {}).addTo(map);
    mapRef.current = map;

    return () => {
      try {
        map.remove();
      } catch (error) {}
    };
  }, []);

  useEffect(() => {
    loadFloodOverlay();
  }, []);

  useEffect(() => {
    if (!mapRef.current) return;

    if (layerRef.current) {
      layerRef.current.remove();
      layerRef.current = null;
    }

    const geojson = panelMode === 'flood'
      ? (floodEditableGeoJSON || floodGeoJSON)
      : clupGeoJSON;
    if (!geojson) return;

    layerRef.current = L.geoJSON(geojson, {
      style: {
        color: panelMode === 'flood' ? '#0284c7' : '#f43f5e',
        weight: panelMode === 'flood' ? 2 : 3,
        fillOpacity: panelMode === 'flood' ? 0.18 : 0.24
      }
    }).addTo(mapRef.current);

    try {
      mapRef.current.fitBounds(layerRef.current.getBounds(), { maxZoom: 16 });
    } catch (error) {
      console.warn('Unable to fit panel bounds', error);
    }
  }, [panelMode, clupGeoJSON, floodGeoJSON]);

  useEffect(() => {
    if (!token) return;

    const fetchLayers = async () => {
      setLoading(true);
      try {
        const response = await fetch(apiUrl('/admin/zoning-layers'), { headers: { 'x-admin-token': token || '' } });
        const data = await response.json();
        setLayers(Array.isArray(data.layers) ? data.layers : []);
      } catch (error) {
        console.warn('Failed to fetch flood and CLUP layers', error);
      } finally {
        setLoading(false);
      }
    };

    fetchLayers();
  }, [token]);

  const refreshLayers = async () => {
    try {
      const response = await fetch(apiUrl('/admin/zoning-layers'), { headers: { 'x-admin-token': token || '' } });
      const data = await response.json();
      setLayers(Array.isArray(data.layers) ? data.layers : []);
    } catch (error) {
      console.warn('Failed to refresh layers', error);
    }
  };

  const handleFileUpload = async (event) => {
    const file = event.target.files && event.target.files[0];
    if (!file) return;

    try {
      const text = await file.text();
      const json = JSON.parse(text);
      if (panelMode === 'flood') {
        setFloodEditableGeoJSON(json);
        setFloodUploadName(file.name.replace(/\.(geojson|json|geojson\.json)$/i, ''));
      } else {
        setClupGeoJSON(json);
        setClupUploadName(file.name.replace(/\.(geojson|json|geojson\.json)$/i, ''));
      }
    } catch (error) {
      alert('Invalid GeoJSON file');
    } finally {
      event.target.value = '';
    }
  };

  const handleSaveUpload = async () => {
    const activeGeoJSON = panelMode === 'flood' ? floodEditableGeoJSON : clupGeoJSON;
    const activeUploadName = panelMode === 'flood' ? floodUploadName : clupUploadName;

    if (!activeGeoJSON) return alert('No GeoJSON to upload');

    const form = new FormData();
    const blob = new Blob([JSON.stringify(activeGeoJSON)], { type: 'application/geo+json' });
    form.append('file', blob, `${activeUploadName || 'clup-flood-zone'}.geojson`);
    form.append('name', activeUploadName || (panelMode === 'flood' ? 'Flood Prone Area' : 'CLUP Flood Zone'));

    try {
      const response = await fetch(apiUrl('/admin/zoning-layers/upload'), {
        method: 'POST',
        headers: { 'x-admin-token': token || '' },
        body: form
      });
      const data = await response.json();
      if (!response.ok) throw new Error(data.detail || 'Upload failed');

      alert(panelMode === 'flood' ? 'Flood-prone area uploaded' : 'CLUP layer uploaded');
      await refreshLayers();
    } catch (error) {
      alert(String(error));
    }
  };

  const handleCreateZone = (feature) => {
    const next = { type: 'FeatureCollection', features: [feature] };
    if (panelMode === 'flood') {
      setFloodEditableGeoJSON(next);
    } else {
      setClupGeoJSON(next);
    }
    setShowEditor(false);
  };

  const handleClearActive = () => {
    if (panelMode === 'flood') {
      setFloodEditableGeoJSON(null);
    } else {
      setClupGeoJSON(null);
    }
  };

  const handlePanelToggle = () => {
    setPanelMode((current) => (current === 'clup' ? 'flood' : 'clup'));
  };

  const activeLayers = panelMode === 'flood'
    ? layers.filter(isFloodRelevantLayer)
    : layers.filter(isClupRelevantLayer);

  const previewLabel = panelMode === 'flood' ? 'Flood prone area' : 'CLUP';
  const activePreviewGeoJSON = panelMode === 'flood' ? (floodEditableGeoJSON || floodGeoJSON) : clupGeoJSON;
  const activeEditableGeoJSON = panelMode === 'flood' ? floodEditableGeoJSON : clupGeoJSON;
  const activeUploadName = panelMode === 'flood' ? floodUploadName : clupUploadName;
  const activeZoneLabel = panelMode === 'flood' ? 'Flood prone area' : 'CLUP zone';

  return (
    <div className="zoning-manager-shell flood-zone-manager">
      <div className="zoning-hero">
        <div>
          <div className="zoning-kicker">Flood and CLUP Studio</div>
          <h3 className="zoning-title">Review zoning and flood-prone overlays</h3>
          <p className="zoning-subtitle">
            Use the toggle in the top-right corner to switch between the CLUP panel and the flood-prone area panel.
          </p>
        </div>

        <div className="zoning-hero-actions">
          <button
            type="button"
            className="zoning-mode-toggle"
            onClick={handlePanelToggle}
          >
            <span>{panelMode === 'clup' ? 'Show flood-prone area' : 'Show CLUP panel'}</span>
            <small>{panelMode === 'clup' ? 'CLUP panel active' : 'Flood-prone panel active'}</small>
          </button>
        </div>
      </div>

      <div className="zoning-toolbar">
        <label className="zoning-upload-btn">
          <input type="file" accept="application/geo+json,application/json,.geojson" onChange={handleFileUpload} />
          <span>Import GeoJSON</span>
        </label>

        <div className="zoning-input-wrap">
          <label>Layer name</label>
          <input
            value={activeUploadName}
            onChange={(e) => {
              if (panelMode === 'flood') {
                setFloodUploadName(e.target.value);
              } else {
                setClupUploadName(e.target.value);
              }
            }}
            placeholder={panelMode === 'flood' ? 'e.g. Panabo Flood Prone Area' : 'e.g. Panabo CLUP Zone'}
          />
        </div>

        <button className="zoning-btn zoning-btn-secondary" onClick={() => setShowEditor(true)} type="button">
          Draw {activeZoneLabel}
        </button>
        <button className="zoning-btn zoning-btn-primary" onClick={handleSaveUpload} disabled={!activeEditableGeoJSON} type="button">
          Save {panelMode === 'flood' ? 'Flood Layer' : 'CLUP Layer'}
        </button>
        <button className="zoning-btn zoning-btn-ghost" onClick={handleClearActive} type="button">
          Clear {activeZoneLabel}
        </button>

        {panelMode === 'flood' && (
          <button className="zoning-btn zoning-btn-secondary zoning-btn-sm" type="button" onClick={loadFloodOverlay}>
            Refresh flood overlay
          </button>
        )}
      </div>

      <div className="zoning-layout">
        <div className="zoning-map-card">
          <div className="zoning-map-header">
            <div>
              <div className="zoning-map-label">Live map</div>
              <div className="zoning-map-helper">
                {panelMode === 'clup'
                  ? 'Edit the CLUP geometry here before saving it to the admin layer store.'
                  : 'Edit or upload a flood-prone area here using the same workflow as CLUP.'}
              </div>
            </div>
            <div className="zoning-map-mini-stat">
              <strong>{previewLabel}</strong>
              <span>{activePreviewGeoJSON ? 'Geometry loaded' : (panelMode === 'flood' ? 'Live overlay only' : 'No CLUP geometry')}</span>
            </div>
          </div>
          <div className="zoning-map-canvas" ref={containerRef} />
        </div>

        <aside className="zoning-side-panel">
          <div className="zoning-panel-head">
            <h4>{panelMode === 'clup' ? 'CLUP layers' : 'Flood layers'}</h4>
            <span>{activeLayers.length}</span>
          </div>

          {loading && <div className="zoning-empty-state">Loading layers...</div>}
          {!loading && activeLayers.length === 0 && <div className="zoning-empty-state">No matching layers uploaded yet.</div>}

          {!loading && activeLayers.map((layer) => (
            <div key={layer.id} className="zoning-layer-card">
              <div className="zoning-layer-top">
                <div>
                  <div className="zoning-layer-name">{layer.name || `Layer ${layer.id}`}</div>
                  <div className="zoning-layer-meta">{layer.source_note || 'No source note provided'}</div>
                </div>
                <span className="zoning-layer-pill">Saved</span>
              </div>

              <div className="zoning-layer-actions">
                <button
                  className="zoning-btn zoning-btn-secondary zoning-btn-sm"
                  type="button"
                  onClick={async () => {
                    try {
                      const response = await fetch(apiUrl(`/admin/zoning-layers/${layer.id}`));
                      const data = await response.json();
                      if (response.ok && data.geojson) {
                        if (isFloodRelevantLayer(layer)) {
                          setPanelMode('flood');
                          setFloodEditableGeoJSON(data.geojson);
                        } else {
                          setPanelMode('clup');
                          setClupGeoJSON(data.geojson);
                        }
                      } else {
                        alert('Failed to load layer preview');
                      }
                    } catch (error) {
                      alert('Failed to load layer preview');
                    }
                  }}
                >
                  Preview
                </button>
                <button className="zoning-btn zoning-btn-ghost zoning-btn-sm" type="button" onClick={() => {
                  if (panelMode === 'flood') {
                    setFloodUploadName(layer.name || activeUploadName);
                  } else {
                    setClupUploadName(layer.name || activeUploadName);
                  }
                }}>
                  Use name
                </button>
              </div>
            </div>
          ))}
        </aside>
      </div>

      {showEditor && (
        <ZoningEditor onClose={() => setShowEditor(false)} onCreate={handleCreateZone} />
      )}
    </div>
  );
}