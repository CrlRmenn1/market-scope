import React, { useEffect, useMemo, useRef, useState } from 'react';
import L from 'leaflet';
import './ZoningManager.css';

export default function ZoningEditor({ initialCenter = [7.3109675, 125.6853653], onClose, onCreate }) {
  const mapRef = useRef(null);
  const containerRef = useRef(null);
  const [points, setPoints] = useState([]);
  const polygonRef = useRef(null);
  const outlineRef = useRef(null);
  const markersRef = useRef([]);
  const [drawMode, setDrawMode] = useState(true);
  const drawModeRef = useRef(true);

  const pointCountLabel = useMemo(() => {
    if (points.length === 0) return 'No points yet';
    if (points.length === 1) return '1 point placed';
    if (points.length === 2) return '2 points placed';
    return `${points.length} points placed`;
  }, [points.length]);

  useEffect(() => {
    if (!containerRef.current) return;
    let map;
    try {
      map = L.map(containerRef.current, { center: initialCenter, zoom: 14 });
      L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {}).addTo(map);

      const clickHandler = (e) => {
        if (!drawModeRef.current) return;
        const latlng = e.latlng;
        setPoints((p) => {
          const next = [...p, [latlng.lat, latlng.lng]];
          const marker = L.circleMarker([latlng.lat, latlng.lng], {
            radius: 6,
            color: '#ffffff',
            weight: 2,
            fillColor: '#e11d48',
            fillOpacity: 1
          }).addTo(map);
          markersRef.current.push(marker);

          if (polygonRef.current) {
            polygonRef.current.setLatLngs(next);
            polygonRef.current.bringToFront();
          } else {
            polygonRef.current = L.polygon(next, {
              color: '#f43f5e',
              weight: 5,
              opacity: 1,
              fillColor: '#e11d48',
              fillOpacity: 0.36,
              lineCap: 'round',
              lineJoin: 'round'
            }).addTo(map);
          }

          if (outlineRef.current) {
            outlineRef.current.setLatLngs(next);
            outlineRef.current.bringToFront();
          } else {
            outlineRef.current = L.polyline(next, {
              color: '#fde047',
              weight: 4,
              opacity: 0.95,
              dashArray: '6 8'
            }).addTo(map);
          }

          if (next.length < 3 && polygonRef.current) {
            polygonRef.current.setStyle({ fillOpacity: 0.12 });
          } else if (polygonRef.current) {
            polygonRef.current.setStyle({ fillOpacity: 0.36 });
            try {
              map.fitBounds(polygonRef.current.getBounds(), { padding: [60, 60], maxZoom: 18 });
            } catch (fitErr) {
              console.warn('Unable to fit draft bounds', fitErr);
            }
          }

          return next;
        });
      };

      map.on('click', clickHandler);
      mapRef.current = map;
      setTimeout(() => {
        try { map.invalidateSize(); } catch (e) {}
      }, 0);
    } catch (err) {
      console.error('ZoningEditor map init failed', err);
    }

    return () => {
      try { map && map.remove(); } catch (e) {}
    };
  }, [initialCenter]);

  const handleFinish = () => {
    if (!points || points.length < 3) {
      alert('Draw a polygon with at least 3 points.');
      return;
    }

    const feature = {
      type: 'Feature',
      properties: {},
      geometry: {
        type: 'Polygon',
        coordinates: [[...points.map((p) => [p[1], p[0]]), [points[0][1], points[0][0]]]]
      }
    };

    onCreate && onCreate(feature);
    onClose && onClose();
  };

  const handleClear = () => {
    setPoints([]);
    if (polygonRef.current) {
      polygonRef.current.remove();
      polygonRef.current = null;
    }
    if (outlineRef.current) {
      outlineRef.current.remove();
      outlineRef.current = null;
    }
    markersRef.current.forEach((marker) => marker.remove());
    markersRef.current = [];
  };

  useEffect(() => {
    drawModeRef.current = drawMode;
  }, [drawMode]);

  const handleUndo = () => {
    setPoints((current) => {
      const next = current.slice(0, -1);

      const marker = markersRef.current.pop();
      if (marker) marker.remove();

      if (polygonRef.current) {
        if (next.length >= 3) {
          polygonRef.current.setLatLngs(next);
          polygonRef.current.setStyle({ fillOpacity: 0.36 });
          polygonRef.current.bringToFront();
        } else {
          polygonRef.current.remove();
          polygonRef.current = null;
        }
      }

      if (outlineRef.current) {
        if (next.length >= 2) {
          outlineRef.current.setLatLngs(next);
        } else {
          outlineRef.current.remove();
          outlineRef.current = null;
        }
      }

      return next;
    });
  };

  return (
    <div className="zoning-editor-modal">
      <div className="zoning-editor-backdrop" onClick={onClose} />
      <div className="zoning-editor-panel">
        <div ref={containerRef} style={{ width: '100%', height: '100%' }} />

        <div className="zoning-editor-card">
          <div style={{ fontWeight: 700, marginBottom: 4 }}>Draw a zoning area</div>
          <div style={{ fontSize: 13, lineHeight: 1.4, opacity: 0.92 }}>
            Click the map to place vertices. You need at least 3 points. Use Undo if you place one in the wrong spot.
          </div>
          <div style={{ marginTop: 8, fontSize: 12, opacity: 0.8 }}>{pointCountLabel}</div>
          <div style={{ marginTop: 4, fontSize: 12, color: 'var(--text-muted)' }}>A dashed outline will appear as soon as you place points.</div>
        </div>

        <div className="zoning-editor-actions zoning-editor-actions-left">
          <button className="zoning-editor-btn zoning-editor-btn-sm" onClick={() => setDrawMode((current) => !current)} type="button">
            {drawMode ? 'Drawing: On' : 'Drawing: Off'}
          </button>
          <button className="zoning-editor-btn zoning-editor-btn-sm" onClick={handleUndo} disabled={points.length === 0} type="button">Undo</button>
          <button className="zoning-editor-btn zoning-editor-btn-sm" onClick={handleClear} disabled={points.length === 0} type="button">Clear</button>
        </div>

        <div className="zoning-editor-top-right">
          <button className="zoning-editor-btn zoning-editor-btn-icon zoning-editor-btn-close" onClick={onClose} type="button" aria-label="Close editor" title="Close editor">
            <svg viewBox="0 0 24 24" fill="none" aria-hidden="true">
              <path d="M18 6L6 18" stroke="currentColor" strokeWidth="2.6" strokeLinecap="round" strokeLinejoin="round" />
              <path d="M6 6L18 18" stroke="currentColor" strokeWidth="2.6" strokeLinecap="round" strokeLinejoin="round" />
            </svg>
          </button>
        </div>

        <div className="zoning-editor-bottom-right">
          <button className="zoning-editor-btn zoning-editor-btn-icon" onClick={handleFinish} type="button" aria-label="Finish zone" title="Finish zone">
            <svg viewBox="0 0 24 24" fill="none" aria-hidden="true">
              <path d="M20 6L9 17l-5-5" stroke="currentColor" strokeWidth="2.6" strokeLinecap="round" strokeLinejoin="round" />
            </svg>
          </button>
        </div>
      </div>
    </div>
  );
}
