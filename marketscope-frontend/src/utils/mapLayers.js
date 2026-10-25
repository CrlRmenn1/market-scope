import { apiUrl } from '../lib/api';

// Panabo main area. Scans only run inside it, and map layers are clipped to it.
export const PANABO_BOUNDS = {
  south: 7.269,
  north: 7.333,
  west: 125.636,
  east: 125.742
};

// The active hazard or zoning layer as a GeoJSON FeatureCollection, or null when none is active.
export const fetchActiveMapLayer = async (category) => {
  const response = await fetch(apiUrl(`/map-layers/active?category=${category}`));
  if (!response.ok) {
    throw new Error(`Unable to load the ${category} layer`);
  }
  const data = await response.json();
  return data?.geojson || null;
};
