import React, { useEffect, useRef, useState } from 'react';

export default function MapPicker({ initialLat = 7.3109675, initialLng = 125.6853653, onSelect, onClose }) {
  const mapRef = useRef(null);
  const markerRef = useRef(null);
  const containerRef = useRef(null);
  const [selected, setSelected] = useState({ lat: initialLat, lng: initialLng });

  useEffect(() => {
    // initialize Leaflet map (global L) — app already uses Leaflet elsewhere
    const L = window.L;
    if (!L || !containerRef.current) return;

    const map = L.map(containerRef.current, { center: [initialLat, initialLng], zoom: 15 });
    L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
      attribution: '&copy; OpenStreetMap contributors'
    }).addTo(map);

    const marker = L.marker([initialLat, initialLng], { draggable: true }).addTo(map);
    marker.on('dragend', () => {
      const latlng = marker.getLatLng();
      setSelected({ lat: latlng.lat, lng: latlng.lng });
    });

    map.on('click', (e) => {
      const { lat, lng } = e.latlng;
      marker.setLatLng([lat, lng]);
      setSelected({ lat, lng });
    });

    mapRef.current = map;
    markerRef.current = marker;

    return () => {
      try { map.remove(); } catch (e) {}
    };
  }, [initialLat, initialLng]);

  return (
    <div style={{ position: 'fixed', inset: 0, zIndex: 1200, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
      <div style={{ position: 'absolute', inset: 0, background: 'rgba(0,0,0,0.5)' }} onClick={onClose} />
      <div style={{ width: '92%', maxWidth: 900, height: 520, background: '#0b0b0f', borderRadius: 12, overflow: 'hidden', boxShadow: '0 16px 40px rgba(2,6,23,0.6)', position: 'relative' }}>
        <div ref={containerRef} style={{ width: '100%', height: '100%' }} />
        <div style={{ position: 'absolute', left: 12, top: 12, zIndex: 1300 }}>
          <button className="secondary-btn" onClick={() => { onSelect && onSelect({ latitude: Number(selected.lat), longitude: Number(selected.lng) }); onClose && onClose(); }}>
            Use this location
          </button>
        </div>
        <div style={{ position: 'absolute', right: 12, top: 12, zIndex: 1300 }}>
          <button className="secondary-btn" onClick={onClose}>Close</button>
        </div>
      </div>
    </div>
  );
}
