// Zoning classes an admin can give a polygon, with the zoning score each one
// earns in a scan (backend: constants/map_layers.py ZONING_CLASSES).
export const ZONING_CLASSES = [
  { id: 'commercial', label: 'Commercial', score: '25', color: '#2563eb', fill: '#3b82f6' },
  { id: 'mixed_use', label: 'Mixed-use', score: '20', color: '#0e7490', fill: '#06b6d4' },
  { id: 'industrial', label: 'Industrial', score: '25 / 5', color: '#475569', fill: '#64748b' },
  { id: 'residential', label: 'Residential', score: '10', color: '#a16207', fill: '#eab308' },
  { id: 'institutional', label: 'Institutional', score: '5', color: '#be185d', fill: '#ec4899' },
  { id: 'agricultural', label: 'Agricultural', score: '5', color: '#15803d', fill: '#22c55e' }
];

const ZONING_CLASS_BY_ID = Object.fromEntries(ZONING_CLASSES.map((item) => [item.id, item]));

export const getZoningClass = (zoneClass) => ZONING_CLASS_BY_ID[zoneClass] || ZONING_CLASSES[0];

// Leaflet style for a zoning polygon, by its zone_class.
export const getZoneStyle = (zoneClass) => {
  const zone = getZoningClass(zoneClass);
  return {
    color: zone.color,
    weight: 2,
    fillColor: zone.fill,
    fillOpacity: 0.24,
    opacity: 0.9
  };
};
