// Theme-aware map tiles: CARTO light/dark basemaps matching the app theme.
export const TILE_URLS = {
  light: 'https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png',
  dark: 'https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png'
};

export const TILE_ATTRIBUTION = '&copy; OpenStreetMap contributors &copy; CARTO';

export const isDarkTheme = () =>
  typeof document !== 'undefined' && document.documentElement.getAttribute('data-theme') === 'dark';

export const getTileUrl = () => (isDarkTheme() ? TILE_URLS.dark : TILE_URLS.light);

// Ink for map vector overlays (boundary, radius circles) — violet accent, readable on both tile sets.
export const getMapInk = () => (isDarkTheme() ? '#a78bfa' : '#7c3aed');
