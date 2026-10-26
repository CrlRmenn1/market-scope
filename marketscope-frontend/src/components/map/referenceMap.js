import L from 'leaflet';
import { apiUrl } from '../../lib/api';
import { TILE_ATTRIBUTION } from '../../utils/mapTheme';

// Reference map drawn from the backend's OpenStreetMap file
// (GET /map-layers/reference): road and waterway lines plus street, barangay
// and subdivision names. Used by the admin Map Layer Studio ("Roads only" view,
// which matches the LGU's printed road maps) and by the satellite views, whose
// photos carry no names of their own.

let referencePromise = null;

// Bump when the backend's reference data changes shape (e.g. new feature kinds),
// so browsers don't keep using a cached older copy.
const REFERENCE_DATA_VERSION = 2;

// Fetched once per page load; the backend also lets the browser cache it for a day.
export const loadReferenceMap = () => {
  if (!referencePromise) {
    referencePromise = fetch(apiUrl(`/map-layers/reference?v=${REFERENCE_DATA_VERSION}`))
      .then((response) => {
        if (!response.ok) throw new Error('The road map could not be loaded.');
        return response.json();
      })
      .catch((error) => {
        referencePromise = null;
        throw error;
      });
  }
  return referencePromise;
};

// ---- lines --------------------------------------------------------------------

// Line style by feature and background: dark "ink" on the plain/street map,
// bright lines on satellite photos. Widths grow as the map zooms in.
export const referenceStyle = (basemap, zoom) => (feature) => {
  const { kind, cls } = feature?.properties || {};
  const scale = zoom >= 17 ? 1.6 : zoom >= 15 ? 1.15 : zoom >= 14 ? 0.85 : 0.6;
  const onPhoto = basemap === 'satellite';

  // On photos the lines are thinner and see-through so houses and fields stay visible.
  if (kind === 'water') {
    return onPhoto
      ? { color: '#7dd3fc', weight: (cls === 'river' ? 2.5 : 1.5) * scale, opacity: 0.7 }
      : { color: '#2563eb', weight: (cls === 'river' ? 3.5 : 2) * scale, opacity: 0.9 };
  }
  if (cls === 'major') {
    return onPhoto
      ? { color: '#fde047', weight: 3 * scale, opacity: 0.8 }
      : { color: '#111827', weight: 4.5 * scale, opacity: 1 };
  }
  if (cls === 'path') {
    return onPhoto
      ? { color: '#e5e7eb', weight: 1 * scale, opacity: 0.4, dashArray: '4 4' }
      : { color: '#6b7280', weight: 1.2 * scale, opacity: 0.8, dashArray: '4 4' };
  }
  return onPhoto
    ? { color: '#ffffff', weight: 1.4 * scale, opacity: 0.5 }
    : { color: '#374151', weight: 2.2 * scale, opacity: 1 };
};

const isLineFeature = (feature) => feature?.properties?.kind === 'road' || feature?.properties?.kind === 'water';

// Road and waterway lines on a canvas in `pane`. They never take clicks.
export const createReferenceLines = (map, data, { pane, basemap }) => L.geoJSON(data, {
  filter: isLineFeature,
  pane,
  renderer: L.canvas({ pane, padding: 0.5 }),
  interactive: false,
  pmIgnore: true,
  attribution: `Roads ${TILE_ATTRIBUTION}`,
  style: referenceStyle(basemap, map.getZoom())
});

const flattenLatLngs = (latlngs) => (
  Array.isArray(latlngs[0]) ? latlngs.flatMap(flattenLatLngs) : [latlngs]
);

// Returns a function that names the road or waterway under the cursor
// (within maxPixels).
export const createLineNameFinder = (map, linesLayer, maxPixels = 12) => {
  const named = [];
  linesLayer.eachLayer((layer) => {
    const name = layer.feature?.properties?.name;
    if (!name) return;
    named.push({
      name,
      kind: layer.feature.properties.kind,
      bounds: layer.getBounds().pad(0.05),
      lines: flattenLatLngs(layer.getLatLngs())
    });
  });

  return (latlng) => {
    // Cheap prefilter: ~40 m around the cursor in degrees.
    const near = L.latLngBounds(
      [latlng.lat - 0.0004, latlng.lng - 0.0004],
      [latlng.lat + 0.0004, latlng.lng + 0.0004]
    );
    const cursor = map.latLngToContainerPoint(latlng);
    let best = null;
    named.forEach((item) => {
      if (!item.bounds.intersects(near)) return;
      item.lines.forEach((line) => {
        for (let index = 1; index < line.length; index += 1) {
          const distance = L.LineUtil.pointToSegmentDistance(
            cursor,
            map.latLngToContainerPoint(line[index - 1]),
            map.latLngToContainerPoint(line[index])
          );
          if (distance <= maxPixels && (!best || distance < best.distance)) {
            best = { name: item.name, kind: item.kind, distance };
          }
        }
      });
    });
    return best;
  };
};

// ---- names --------------------------------------------------------------------

const MAX_LABELS = 140;
const SAME_NAME_SPACING_PX = 320;

// Smallest zoom at which each kind of name appears, so the map isn't crowded
// when zoomed out.
const LABEL_MIN_ZOOM = { barangay: 12, area: 16, major: 14, water: 15, minor: 15 };

const escapeHtml = (text) => String(text).replace(/[&<>"']/g, (char) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[char]));

// Rough text size in pixels for collision checks (labels use an 11–12px font).
const labelSize = (name, cls) => {
  if (cls === 'barangay') return [name.length * 8.6 + 10, 18];
  if (cls === 'area') return [name.length * 6 + 8, 14];
  return [name.length * 6.4 + 8, 14];
};

const toLatLngs = (coordinates) => coordinates.map(([lng, lat]) => L.latLng(lat, lng));

// Street, waterway, barangay and subdivision names as rotated text labels in
// `pane`. Labels are re-placed after every pan/zoom: barangays first, then
// major roads, waterways and minor streets, skipping any that would overlap.
export function createReferenceLabels(map, data, { pane }) {
  const places = [];
  const linesByName = new Map();
  (data?.features || []).forEach((feature) => {
    const { kind, cls, name } = feature.properties || {};
    if (!name) return;
    if (kind === 'place') {
      const [lng, lat] = feature.geometry.coordinates;
      places.push({ name, cls, latlng: L.latLng(lat, lng) });
      return;
    }
    const labelClass = kind === 'water' ? 'water' : cls;
    if (!LABEL_MIN_ZOOM[labelClass]) return;
    const { type, coordinates } = feature.geometry;
    const lines = type === 'LineString' ? [toLatLngs(coordinates)] : coordinates.map(toLatLngs);
    const key = `${labelClass}:${name}`;
    if (!linesByName.has(key)) linesByName.set(key, { name, cls: labelClass, lines: [] });
    linesByName.get(key).lines.push(...lines);
  });
  places.sort((a, b) => (a.cls === b.cls ? 0 : a.cls === 'barangay' ? -1 : 1));
  const lineOrder = ['major', 'water', 'minor'];
  const namedLines = [...linesByName.values()].sort((a, b) => lineOrder.indexOf(a.cls) - lineOrder.indexOf(b.cls));

  const group = L.layerGroup();

  const render = () => {
    group.clearLayers();
    if (!map.hasLayer(group)) return;

    const zoom = map.getZoom();
    const size = map.getSize();
    const placed = [];
    const placedByName = new Map();
    const overlaps = (box) => placed.some((other) => !(box.x2 < other.x1 || box.x1 > other.x2 || box.y2 < other.y1 || box.y1 > other.y2));
    const insideView = (point) => point.x >= 0 && point.y >= 0 && point.x <= size.x && point.y <= size.y;

    const addLabel = (latlng, point, name, cls, angle = 0) => {
      const [width, height] = labelSize(name, cls);
      const radians = (angle * Math.PI) / 180;
      const boxWidth = Math.abs(width * Math.cos(radians)) + Math.abs(height * Math.sin(radians));
      const boxHeight = Math.abs(width * Math.sin(radians)) + Math.abs(height * Math.cos(radians));
      const box = { x1: point.x - boxWidth / 2, y1: point.y - boxHeight / 2, x2: point.x + boxWidth / 2, y2: point.y + boxHeight / 2 };
      if (placed.length >= MAX_LABELS || overlaps(box)) return false;
      const sameName = placedByName.get(name) || [];
      if (sameName.some((other) => other.distanceTo(point) < SAME_NAME_SPACING_PX)) return false;

      placed.push(box);
      placedByName.set(name, [...sameName, point]);
      group.addLayer(L.marker(latlng, {
        pane,
        interactive: false,
        keyboard: false,
        pmIgnore: true,
        icon: L.divIcon({
          className: `ref-label ref-label--${cls}`,
          html: `<span style="transform: translate(-50%, -50%) rotate(${angle.toFixed(1)}deg)">${escapeHtml(name)}</span>`,
          iconSize: [0, 0]
        })
      }));
      return true;
    };

    places.forEach((place) => {
      if (zoom < LABEL_MIN_ZOOM[place.cls]) return;
      const point = map.latLngToContainerPoint(place.latlng);
      if (insideView(point)) addLabel(place.latlng, point, place.name, place.cls);
    });

    namedLines.forEach((item) => {
      if (zoom < LABEL_MIN_ZOOM[item.cls]) return;
      const [textWidth] = labelSize(item.name, item.cls);
      item.lines.forEach((line) => {
        // Walk the line in screen pixels and drop a label on the middle of
        // every stretch that is long enough to hold the name.
        const points = line.map((latlng) => map.latLngToContainerPoint(latlng));
        let runStart = 0;
        let runLength = 0;
        const placeOnRun = (start, end, length) => {
          if (length < textWidth + 12) return;
          let target = length / 2;
          for (let index = start + 1; index <= end; index += 1) {
            const a = points[index - 1];
            const b = points[index];
            const segment = a.distanceTo(b);
            if (target <= segment) {
              const ratio = segment ? target / segment : 0;
              const point = L.point(a.x + (b.x - a.x) * ratio, a.y + (b.y - a.y) * ratio);
              let angle = (Math.atan2(b.y - a.y, b.x - a.x) * 180) / Math.PI;
              if (angle > 90) angle -= 180;
              if (angle < -90) angle += 180;
              addLabel(map.containerPointToLatLng(point), point, item.name, item.cls, angle);
              return;
            }
            target -= segment;
          }
        };
        for (let index = 1; index < points.length; index += 1) {
          const visible = insideView(points[index - 1]) && insideView(points[index]);
          if (visible) {
            runLength += points[index - 1].distanceTo(points[index]);
          } else {
            placeOnRun(runStart, index - 1, runLength);
            runStart = index;
            runLength = 0;
          }
        }
        placeOnRun(runStart, points.length - 1, runLength);
      });
    });
  };

  map.on('moveend', render);

  return {
    show: () => {
      if (!map.hasLayer(group)) group.addTo(map);
      render();
    },
    hide: () => group.remove(),
    // Light text with a dark halo on satellite photos, dark text otherwise.
    setOnPhoto: (onPhoto) => map.getPane(pane)?.classList.toggle('ref-labels--photo', Boolean(onPhoto)),
    destroy: () => {
      map.off('moveend', render);
      group.remove();
    }
  };
}
