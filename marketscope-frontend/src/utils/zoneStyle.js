// Zones of the Panabo City Integrated Zoning Map C.Y. 2020-2029 (backend:
// constants/map_layers.py ZONING_CLASSES). Colors follow the printed legend so
// the admin can match the paper map; zones that share a color there get a
// dashed outline (dash) to tell them apart. Zoning is pass/fail per business
// type, set in Admin -> Map layers -> Allowed businesses.
export const ZONING_CLASSES = [
  { id: 'general_commercial', label: 'General Commercial Zone', group: 'Commercial', color: '#b71c1c', fill: '#f44336' },
  { id: 'commercial_2', label: 'Commercial-2 (C-2) Zone', group: 'Commercial', color: '#5d1f18', fill: '#8d3b32' },
  { id: 'commercial_3', label: 'Commercial-3 (C-3) Zone', group: 'Commercial', color: '#a5281a', fill: '#d84a3a', dash: true },
  { id: 'tourism', label: 'Tourism Zone', group: 'Commercial', color: '#b45309', fill: '#f59e0b' },
  { id: 'general_residential', label: 'General Residential Zone', group: 'Residential', color: '#a18207', fill: '#e6c229' },
  { id: 'residential_1', label: 'Residential-1 (R-1) Zone', group: 'Residential', color: '#b59f00', fill: '#f5d90a', dash: true },
  { id: 'socialized_housing', label: 'Socialized Housing Zone', group: 'Residential', color: '#7a6500', fill: '#d9b300', dash: true },
  { id: 'agri_industrial', label: 'Agri-Industrial Zone', group: 'Industrial', color: '#7e57c2', fill: '#c4a3dc' },
  { id: 'industrial_1', label: 'Industrial-1 (I-1) Zone', group: 'Industrial', color: '#6c3483', fill: '#a569bd' },
  { id: 'industrial_2', label: 'Industrial-2 (I-2) Zone', group: 'Industrial', color: '#5b2c6f', fill: '#8e44ad', dash: true },
  { id: 'industrial_3', label: 'Industrial-3 (I-3) Zone', group: 'Industrial', color: '#4a235a', fill: '#6c3483' },
  { id: 'general_institutional', label: 'General Institutional Zone', group: 'Institutional & services', color: '#0d47a1', fill: '#1e63d6' },
  { id: 'special_institutional', label: 'Special Institutional Zone', group: 'Institutional & services', color: '#1a237e', fill: '#2a52be', dash: true },
  { id: 'utilities_transport', label: 'Utilities, Transportation and Services Zone', group: 'Institutional & services', color: '#616161', fill: '#b0b0b0' },
  { id: 'parks_recreation', label: 'Parks and Recreation Zone', group: 'Open space', color: '#388e3c', fill: '#7cc36b' },
  { id: 'cemetery', label: 'Cemetery/Memorial Park Zone', group: 'Open space', color: '#2e7d32', fill: '#8fd18a', dash: true },
  { id: 'buffer_greenbelt', label: 'Buffer/Greenbelt Zone', group: 'Open space', color: '#1b5e20', fill: '#66bb6a' },
  { id: 'production_agricultural', label: 'Production Agricultural Sub-Zone', group: 'Agriculture & environment', color: '#2e7d32', fill: '#4caf50' },
  { id: 'aquaculture', label: 'Aquaculture Sub-Zone', group: 'Agriculture & environment', color: '#5b8db8', fill: '#bcd6ee' },
  { id: 'mangrove', label: 'Mangrove Sub-Zone', group: 'Agriculture & environment', color: '#3f6f99', fill: '#a9cbe8', dash: true },
  { id: 'forest_reserve', label: 'Forest Reserve Sub-Zone', group: 'Agriculture & environment', color: '#1b3d1e', fill: '#2e6b34' },
  { id: 'quarry', label: 'Quarry Sub-Zone', group: 'Agriculture & environment', color: '#5d2e17', fill: '#a0522d' },
  { id: 'special_use', label: 'Special Used Zone', group: 'Agriculture & environment', color: '#1e4422', fill: '#3e7b44', dash: true }
];

const ZONING_CLASS_BY_ID = Object.fromEntries(ZONING_CLASSES.map((item) => [item.id, item]));

export const getZoningClass = (zoneClass) => ZONING_CLASS_BY_ID[zoneClass] || ZONING_CLASSES[0];

// [[group, zones], ...] in legend order, for grouped pickers.
export const ZONING_GROUPS = ZONING_CLASSES.reduce((groups, zone) => {
  const last = groups[groups.length - 1];
  if (last && last[0] === zone.group) last[1].push(zone);
  else groups.push([zone.group, [zone]]);
  return groups;
}, []);

// Zone classes used by a zoning FeatureCollection, in legend order (for map legends).
export const zoningClassesIn = (geojson) => {
  const present = new Set((geojson?.features || []).map((feature) => feature?.properties?.zone_class));
  return ZONING_CLASSES.filter((zone) => present.has(zone.id));
};

// Leaflet style for a zoning polygon, by its zone_class.
export const getZoneStyle = (zoneClass) => {
  const zone = getZoningClass(zoneClass);
  return {
    color: zone.color,
    weight: 2,
    fillColor: zone.fill,
    fillOpacity: 0.3,
    opacity: 0.9,
    dashArray: zone.dash ? '6 4' : null
  };
};
