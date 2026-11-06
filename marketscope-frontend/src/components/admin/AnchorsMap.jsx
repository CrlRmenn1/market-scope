import React, { useEffect, useRef } from 'react';
import L from 'leaflet';
import { getMapInk, getTileUrl, TILE_ATTRIBUTION } from '../../utils/mapTheme';
import { panaboLatLngBounds } from '../../utils/mapLayers';
import { ANCHOR_SOURCE_COLORS } from './anchorColors';

const INACTIVE_COLOR = '#94a3b8';

const PIN_HTML = `
  <div style="display:flex;align-items:flex-end;justify-content:center;width:32px;height:32px;">
    <svg width="32" height="32" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg" aria-hidden="true">
      <path d="M12 2C8.686 2 6 4.686 6 8c0 4.418 5.25 10.5 5.5 10.75.166.166.384.25.6.25s.434-.084.6-.25C12.75 18.5 18 12.418 18 8c0-3.314-2.686-6-6-6z" fill="#e11d48" stroke="#ffffff" stroke-width="1"/>
      <circle cx="12" cy="8" r="2.2" fill="#fff"/>
    </svg>
  </div>
`;

const markerRadius = (power) => (power >= 20 ? 9 : power >= 10 ? 7 : 5);

// Every anchor on one map. Clicking empty map space places the draft pin, which can
// then be dragged, and the rings show how far an anchor of that category counts.
export default function AnchorsMap({ anchors, selectedRef, draft, bands, focus, refOf, onMapClick, onDraftMove, onSelect }) {
  const containerRef = useRef(null);
  const mapRef = useRef(null);
  const markersRef = useRef(null);
  const draftRef = useRef(null);
  const ringsRef = useRef(null);
  const handlersRef = useRef({});

  // The map is created once, so its events read the latest handlers from here.
  useEffect(() => {
    handlersRef.current = { onMapClick, onDraftMove, onSelect };
  });

  useEffect(() => {
    const panabo = panaboLatLngBounds();
    const map = L.map(containerRef.current, { minZoom: 12, maxBounds: panabo.pad(0.35), maxBoundsViscosity: 0.8 });
    map.fitBounds(panabo);
    L.tileLayer(getTileUrl(), { attribution: TILE_ATTRIBUTION, maxZoom: 19 }).addTo(map);
    L.rectangle(panabo, { color: getMapInk(), weight: 2, opacity: 0.6, fill: false, dashArray: '6 6', interactive: false }).addTo(map);
    ringsRef.current = L.layerGroup().addTo(map);
    markersRef.current = L.layerGroup().addTo(map);
    map.on('click', (event) => handlersRef.current.onMapClick?.(event.latlng.lat, event.latlng.lng));
    mapRef.current = map;

    const resizeObserver = new ResizeObserver(() => map.invalidateSize());
    resizeObserver.observe(containerRef.current);

    return () => {
      resizeObserver.disconnect();
      map.remove();
      mapRef.current = null;
      draftRef.current = null;
    };
  }, []);

  // The anchors.
  useEffect(() => {
    const group = markersRef.current;
    if (!group) return;
    group.clearLayers();
    anchors.forEach((anchor) => {
      const active = anchor.status === 'active';
      const selected = refOf(anchor) === selectedRef;
      const color = active ? ANCHOR_SOURCE_COLORS[anchor.origin] || INACTIVE_COLOR : INACTIVE_COLOR;
      const marker = L.circleMarker([anchor.lat, anchor.lon], {
        radius: markerRadius(anchor.power) + (selected ? 2 : 0),
        color: selected ? getMapInk() : '#ffffff',
        weight: selected ? 3 : 1.5,
        fillColor: color,
        fillOpacity: active ? 0.95 : 0.35,
        dashArray: active ? null : '3 3',
        bubblingMouseEvents: false
      }).addTo(group);
      marker.bindTooltip(anchor.name, { direction: 'top', offset: [0, -6], opacity: 0.92 });
      marker.on('click', () => handlersRef.current.onSelect?.(anchor));
    });
  }, [anchors, selectedRef, refOf]);

  // The pin being placed or edited.
  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;
    if (!draft) {
      draftRef.current?.remove();
      draftRef.current = null;
      return;
    }
    if (draftRef.current) {
      draftRef.current.setLatLng([draft.lat, draft.lng]);
      return;
    }
    const icon = L.divIcon({ html: PIN_HTML, className: 'map-picker-pin', iconSize: [32, 32], iconAnchor: [16, 32] });
    const marker = L.marker([draft.lat, draft.lng], { icon, draggable: true, zIndexOffset: 1000, autoPan: true }).addTo(map);
    marker.on('dragend', () => {
      const position = marker.getLatLng();
      handlersRef.current.onDraftMove?.(position.lat, position.lng);
    });
    draftRef.current = marker;
  }, [draft]);

  // How far an anchor of the chosen category counts: full value, then half value.
  useEffect(() => {
    const group = ringsRef.current;
    if (!group) return;
    group.clearLayers();
    if (!draft || !bands) return;
    const [fullMeters, halfMeters] = bands;
    const ink = getMapInk();
    L.circle([draft.lat, draft.lng], { radius: fullMeters, color: ink, weight: 1.5, fillColor: ink, fillOpacity: 0.08, interactive: false }).addTo(group);
    L.circle([draft.lat, draft.lng], { radius: halfMeters, color: ink, weight: 1, dashArray: '5 5', fill: false, interactive: false }).addTo(group);
  }, [draft, bands]);

  // Pan to a spot picked from the list.
  useEffect(() => {
    if (focus && mapRef.current) mapRef.current.setView([focus.lat, focus.lng], Math.max(mapRef.current.getZoom(), 16));
  }, [focus]);

  return (
    <div className="relative h-full min-h-[320px] overflow-hidden rounded-xl">
      <div className="osm-map-wrapper">
        <div ref={containerRef} className="h-full w-full" />
      </div>
    </div>
  );
}
