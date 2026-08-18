// Standard OSM raster tiles for both themes - full color roads, buildings,
// water, and parks, matching the admin maps (ZoningManager, FloodZoneManager).
// There is no free colorful "dark mode" tile set, so both themes share this
// source; only the vector overlay ink (see getMapInk) adapts to dark mode.
export const TILE_URLS = {
  light: 'https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png',
  dark: 'https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png'
};

export const TILE_ATTRIBUTION = '&copy; OpenStreetMap contributors';

export const isDarkTheme = () =>
  typeof document !== 'undefined' && document.documentElement.getAttribute('data-theme') === 'dark';

export const getTileUrl = () => (isDarkTheme() ? TILE_URLS.dark : TILE_URLS.light);

// Ink for map vector overlays (boundary, radius circles) — violet accent, readable on both tile sets.
export const getMapInk = () => (isDarkTheme() ? '#a78bfa' : '#7c3aed');
