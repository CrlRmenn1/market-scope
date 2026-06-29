import React, { useEffect, useRef, useState } from 'react';
import L from 'leaflet';
import ZoningEditor from './ZoningEditor';
import { apiUrl } from '../api';
import './ZoningManager.css';

export default function ZoningManager({ token }) {
  const mapRef = useRef(null);
  const containerRef = useRef(null);
  const layerRef = useRef(null);
  const [layers, setLayers] = useState([]);
  const [loading, setLoading] = useState(false);
  const [showEditor, setShowEditor] = useState(false);
  const [stagedGeoJSON, setStagedGeoJSON] = useState(null);
  const [uploadName, setUploadName] = useState('New zoning layer');

  useEffect(() => {
    if (!containerRef.current) return;
    const map = L.map(containerRef.current, { center: [7.3109675, 125.6853653], zoom: 13 });
    L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {}).addTo(map);
    mapRef.current = map;

    return () => { try { map.remove(); } catch (e) {} };
  }, []);

  useEffect(() => {
    if (!mapRef.current) return;
    if (layerRef.current) {
      layerRef.current.remove();
      layerRef.current = null;
    }
    if (stagedGeoJSON) {
      layerRef.current = L.geoJSON(stagedGeoJSON, {
        style: { color: '#2563eb', weight: 2, fillOpacity: 0.2 }
      }).addTo(mapRef.current);
      mapRef.current.fitBounds(layerRef.current.getBounds(), { maxZoom: 16 });
    }
  }, [stagedGeoJSON]);

  const fetchLayers = async () => {
    setLoading(true);
    try {
      const res = await fetch(apiUrl('/admin/zoning-layers'), { headers: { 'x-admin-token': token || '' } });
      const data = await res.json();
      setLayers(Array.isArray(data.layers) ? data.layers : []);
    } catch (e) {
      console.warn('Failed to fetch zoning layers', e);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { fetchLayers(); }, []);

  const handleFileUpload = async (e) => {
    const file = e.target.files && e.target.files[0];
    if (!file) return;
    try {
      const text = await file.text();
      const json = JSON.parse(text);
      setStagedGeoJSON(json);
      setUploadName(file.name.replace(/\.(geojson|json|geojson.json)$/i, ''));
    } catch (err) {
      alert('Invalid GeoJSON file');
    } finally {
      e.target.value = '';
    }
  };

  const handleSaveUpload = async () => {
    if (!stagedGeoJSON) return alert('No GeoJSON to upload');
    const form = new FormData();
    const blob = new Blob([JSON.stringify(stagedGeoJSON)], { type: 'application/geo+json' });
    form.append('file', blob, `${uploadName || 'zoning'}.geojson`);
    form.append('name', uploadName || 'zoning');

    try {
      const res = await fetch(apiUrl('/admin/zoning-layers/upload'), {
        method: 'POST',
        headers: { 'x-admin-token': token || '' },
        body: form
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || 'Upload failed');
      alert('Layer uploaded');
      setStagedGeoJSON(null);
      fetchLayers();
    } catch (err) {
      alert(String(err));
    }
  };

  const handleCreateZone = (feature) => {
    // Convert single feature into a FeatureCollection for staging
    const next = { type: 'FeatureCollection', features: [feature] };
    setStagedGeoJSON(next);
    setShowEditor(false);
  };

  return (
    <div className="zoning-manager-shell">
      <div className="zoning-hero">
        <div>
          <div className="zoning-kicker">Zoning Studio</div>
          <h3 className="zoning-title">Build and preview zoning layers</h3>
          <p className="zoning-subtitle">
            Upload a GeoJSON layer, draw a draft zone, or preview existing geometry before it gets published.
          </p>
        </div>
        <div className="zoning-hero-badge">
          <span className="zoning-badge-dot" />
          Draft mode
        </div>
      </div>

      <div className="zoning-toolbar">
        <label className="zoning-upload-btn">
          <input type="file" accept="application/geo+json,application/json,.geojson" onChange={handleFileUpload} />
          <span>Import GeoJSON</span>
        </label>

        <div className="zoning-input-wrap">
          <label>Layer name</label>
          <input value={uploadName} onChange={(e) => setUploadName(e.target.value)} placeholder="e.g. Panabo Commercial Core" />
        </div>

        <button className="zoning-btn zoning-btn-secondary" onClick={() => setShowEditor(true)} type="button">
          Draw New Zone
        </button>
        <button className="zoning-btn zoning-btn-primary" onClick={handleSaveUpload} disabled={!stagedGeoJSON} type="button">
          Save Layer
        </button>
        <button className="zoning-btn zoning-btn-ghost" onClick={() => { setStagedGeoJSON(null); }} type="button">
          Clear Draft
        </button>
      </div>

      <div className="zoning-layout">
        <div className="zoning-map-card">
          <div className="zoning-map-header">
            <div>
              <div className="zoning-map-label">Live map</div>
              <div className="zoning-map-helper">Preview your draft zone here. The editor stays centered on Panabo.</div>
            </div>
            <div className="zoning-map-mini-stat">
              <strong>{stagedGeoJSON ? '1 draft' : '0 drafts'}</strong>
              <span>{stagedGeoJSON ? 'Ready to save' : 'No draft selected'}</span>
            </div>
          </div>
          <div className="zoning-map-canvas" ref={containerRef} />
        </div>

        <aside className="zoning-side-panel">
          <div className="zoning-panel-head">
            <h4>Layers</h4>
            <span>{layers.length}</span>
          </div>

          {loading && <div className="zoning-empty-state">Loading layers...</div>}
          {!loading && layers.length === 0 && <div className="zoning-empty-state">No layers uploaded yet.</div>}

          {!loading && layers.map((l) => (
            <div key={l.id} className="zoning-layer-card">
              <div className="zoning-layer-top">
                <div>
                  <div className="zoning-layer-name">{l.name || `Layer ${l.id}`}</div>
                  <div className="zoning-layer-meta">{l.source_note || 'No source note provided'}</div>
                </div>
                <span className="zoning-layer-pill">Saved</span>
              </div>

              <div className="zoning-layer-actions">
                <button className="zoning-btn zoning-btn-secondary zoning-btn-sm" type="button" onClick={async () => {
                  try {
                    const res = await fetch(apiUrl(`/admin/zoning-layers/${l.id}`));
                    const data = await res.json();
                    if (res.ok && data.geojson) setStagedGeoJSON(data.geojson);
                    else alert('Failed to load layer preview');
                  } catch (e) { alert('Failed to load layer preview'); }
                }}>
                  Preview
                </button>
                <button className="zoning-btn zoning-btn-ghost zoning-btn-sm" type="button" onClick={() => setUploadName(l.name || uploadName)}>
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
