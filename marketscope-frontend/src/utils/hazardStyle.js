// Flood hazard classes an admin can give a polygon (backend: constants/map_layers.py).
export const HAZARD_CLASSES = [
  { id: 'very_high', var: 1, label: 'Very High' },
  { id: 'high', var: 2, label: 'High' },
  { id: 'moderate', var: 3, label: 'Moderate' }
];

const HAZARD_VAR_BY_CLASS = Object.fromEntries(HAZARD_CLASSES.map((item) => [item.id, item.var]));

// Var level (1 = highest) of a hazard feature: from properties.zone_class, or a legacy Var field.
export const getHazardVar = (feature) => {
  const properties = feature?.properties || {};
  return HAZARD_VAR_BY_CLASS[properties.zone_class] || Number(properties.Var);
};

// Leaflet style for a flood hazard polygon, by its Var level (1 = highest).
export const getHazardStyle = (hazardVar) => {
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
