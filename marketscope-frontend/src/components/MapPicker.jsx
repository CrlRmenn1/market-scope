import React, { useEffect, useRef, useState } from 'react';
import L from 'leaflet';
// Fix for Vite + Leaflet image bug (same approach as Home.jsx)
delete L.Icon.Default.prototype._getIconUrl;
L.Icon.Default.mergeOptions({
  iconRetinaUrl: '',
  iconUrl: '',
  shadowUrl: ''
});

export default function MapPicker({ initialLat = 7.3109675, initialLng = 125.6853653, onSelect, onClose }) {
  const mapRef = useRef(null);
  const markerRef = useRef(null);
  const containerRef = useRef(null);
  const [selected, setSelected] = useState({ lat: initialLat, lng: initialLng });
  const [loading, setLoading] = useState(true);
  const [initError, setInitError] = useState(null);

  useEffect(() => {
    if (!containerRef.current) return;
    let map;
    try {
      map = L.map(containerRef.current, { center: [initialLat, initialLng], zoom: 15 });
      L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
        attribution: '&copy; OpenStreetMap contributors'
      }).addTo(map).on('load', () => setLoading(false)).on('tileerror', () => setLoading(false));

      // create a visible div icon for the picker pin (SVG ensures display without external images)
      const pinHtml = `
        <div style="display:flex;align-items:flex-end;justify-content:center;width:28px;height:28px;">
          <svg width="28" height="28" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
            <path d="M12 2C8.686 2 6 4.686 6 8c0 4.418 5.25 10.5 5.5 10.75.166.166.384.25.6.25s.434-.084.6-.25C12.75 18.5 18 12.418 18 8c0-3.314-2.686-6-6-6z" fill="#e11d48"/>
            <circle cx="12" cy="8" r="2.2" fill="#fff"/>
          </svg>
        </div>
      `;

      const pickerIcon = L.divIcon({ html: pinHtml, className: 'map-picker-pin', iconSize: [28, 28], iconAnchor: [14, 28] });

      // create initial marker so user sees a pin by default
      const marker = L.marker([initialLat, initialLng], { icon: pickerIcon, draggable: true }).addTo(map);
      marker.on('dragend', () => {
        const latlng = marker.getLatLng();
        setSelected({ lat: latlng.lat, lng: latlng.lng });
      });

      map.on('click', (e) => {
        const { lat, lng } = e.latlng;
        if (!markerRef.current) {
          markerRef.current = L.marker([lat, lng], { icon: pickerIcon, draggable: true }).addTo(map);
          markerRef.current.on('dragend', () => {
            const latlng2 = markerRef.current.getLatLng();
            setSelected({ lat: latlng2.lat, lng: latlng2.lng });
          });
        } else {
          markerRef.current.setLatLng([lat, lng]);
        }
        setSelected({ lat, lng });
      });

      mapRef.current = map;
      markerRef.current = marker;
    } catch (err) {
      setInitError(err?.message || 'Map init failed');
      setLoading(false);
    }

    return () => {
      try { map && map.remove(); } catch (e) {}
    };
  }, [initialLat, initialLng]);

  return (
    <div style={{ position: 'fixed', inset: 0, zIndex: 1200, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
      <div style={{ position: 'absolute', inset: 0, background: 'rgba(0,0,0,0.45)' }} onClick={onClose} />
      <div style={{ width: '92%', maxWidth: 900, height: 520, background: 'var(--bg)', borderRadius: 12, overflow: 'hidden', boxShadow: '0 16px 40px rgba(2,6,23,0.6)', position: 'relative' }}>
        {loading && <div style={{ position: 'absolute', inset: 0, display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 1250 }}><div className="spinner" /> Loading map…</div>}
        {initError && <div style={{ padding: 16, color: 'var(--muted)', zIndex: 1250 }}>Map failed to load: {initError}</div>}
        <div ref={containerRef} style={{ width: '100%', height: '100%' }} />
        <div style={{ position: 'absolute', left: 16, top: 16, zIndex: 1300 }}>
          <button className="map-picker-use-btn" onClick={() => { onSelect && onSelect({ latitude: Number(selected.lat), longitude: Number(selected.lng) }); onClose && onClose(); }}>
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg"><path d="M12 2v6l4 4" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round"/></svg>
            <span style={{ marginLeft: 8 }}>Use this location</span>
          </button>
          <button className="map-picker-pin-btn" onClick={() => { if (mapRef.current && markerRef.current) { mapRef.current.setView([selected.lat, selected.lng], 16); markerRef.current.openPopup && markerRef.current.openPopup(); } else if (mapRef.current) { mapRef.current.setView([selected.lat, selected.lng], 16); } }} title="Center pin">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg"><path d="M12 2C8.686 2 6 4.686 6 8c0 4.418 5.25 10.5 5.5 10.75.166.166.384.25.6.25s.434-.084.6-.25C12.75 18.5 18 12.418 18 8c0-3.314-2.686-6-6-6z" stroke="currentColor" strokeWidth="1.2" strokeLinecap="round" strokeLinejoin="round"/><circle cx="12" cy="8" r="2.2" fill="currentColor"/></svg>
          </button>
        </div>
        <div style={{ position: 'absolute', right: 12, top: 12, zIndex: 1300 }}>
          <button className="map-picker-close-btn" onClick={onClose} aria-label="Close map picker">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
              <path d="M18 6L6 18" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
              <path d="M6 6L18 18" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
            </svg>
          </button>
        </div>

        {/* Floating confirm check button when a marker/selection exists */}
        {selected && (
          <div style={{ position: 'absolute', right: 18, bottom: 18, zIndex: 1400 }}>
            <button className="map-picker-confirm-btn" onClick={() => { onSelect && onSelect({ latitude: Number(selected.lat), longitude: Number(selected.lng) }); onClose && onClose(); }} aria-label="Confirm location">
              <svg className="confirm-check" width="22" height="22" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
                <path d="M20 6L9 17l-5-5" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" />
              </svg>
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
