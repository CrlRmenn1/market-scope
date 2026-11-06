import React, { useEffect, useRef } from 'react';
import L from 'leaflet';
import { getMapInk, getTileUrl, TILE_ATTRIBUTION } from '../../utils/mapTheme';
import { panaboLatLngBounds } from '../../utils/mapLayers';

const markerClass = (headline, selected) => {
  const kind = !headline?.is_suggestion ? 'none' : headline.competitor_data === 'thin' ? 'thin' : 'strong';
  return `trend-area-marker ${kind}${selected ? ' selected' : ''}`;
};

// Each area is a numbered marker: the score of its top business. The number carries
// the meaning, so the map still reads without telling the colors apart.
export default function AreaMap({ areas, selectedName, onSelect }) {
  const containerRef = useRef(null);
  const mapRef = useRef(null);
  const markersRef = useRef(null);
  const onSelectRef = useRef(onSelect);
  const fittedRef = useRef(false);

  // The map is created once, so its events read the latest handler from here.
  useEffect(() => {
    onSelectRef.current = onSelect;
  });

  useEffect(() => {
    const panabo = panaboLatLngBounds();
    const map = L.map(containerRef.current, { minZoom: 12, maxBounds: panabo.pad(0.35), maxBoundsViscosity: 0.8 });
    map.fitBounds(panabo);
    L.tileLayer(getTileUrl(), { attribution: TILE_ATTRIBUTION, maxZoom: 19 }).addTo(map);
    L.rectangle(panabo, { color: getMapInk(), weight: 2, opacity: 0.4, fill: false, dashArray: '6 6', interactive: false }).addTo(map);
    markersRef.current = L.layerGroup().addTo(map);
    mapRef.current = map;

    const resizeObserver = new ResizeObserver(() => map.invalidateSize());
    resizeObserver.observe(containerRef.current);

    return () => {
      resizeObserver.disconnect();
      map.remove();
      mapRef.current = null;
      fittedRef.current = false;
    };
  }, []);

  // Zoom to the areas once, not the whole city boundary, which is mostly farmland and
  // sea and leaves the downtown markers on top of each other.
  useEffect(() => {
    if (fittedRef.current || !mapRef.current || areas.length === 0) return;
    // Not animated: leaving the page mid-animation makes Leaflet throw as the map is removed.
    mapRef.current.fitBounds(L.latLngBounds(areas.map(({ lat, lng }) => [lat, lng])), { padding: [24, 24], animate: false });
    fittedRef.current = true;
  }, [areas]);

  useEffect(() => {
    const group = markersRef.current;
    if (!group) return;
    group.clearLayers();
    areas.forEach(({ name, lat, lng, headline }) => {
      const selected = name === selectedName;
      const icon = L.divIcon({
        html: `<span>${headline ? headline.score : '-'}</span>`,
        className: markerClass(headline, selected),
        iconSize: [32, 32],
        iconAnchor: [16, 16]
      });
      const summary = headline ? `${name}: ${headline.business_name}, ${headline.score}` : `${name}: no match`;
      const marker = L.marker([lat, lng], { icon, title: summary, alt: summary, zIndexOffset: selected ? 1000 : 0 }).addTo(group);
      marker.on('click', () => onSelectRef.current?.(name));
    });
  }, [areas, selectedName]);

  return (
    <div className="relative h-[320px] overflow-hidden rounded-xl lg:h-[420px]">
      <div className="osm-map-wrapper">
        <div ref={containerRef} className="h-full w-full" />
      </div>
    </div>
  );
}
