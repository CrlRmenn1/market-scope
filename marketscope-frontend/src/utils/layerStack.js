import difference from '@turf/difference';
import { featureCollection } from '@turf/helpers';

// Stacking rule for map layers (mirror of the backend's services/layer_stack.py):
// features are a stack, first = bottom, last = top, and where shapes overlap the
// one on top wins. resolveStack() returns each feature cut down to the part no
// higher feature covers, so overlapping shapes can be shown the way scans read them.

const ringBounds = (coordinates, bounds) => {
  coordinates.forEach((item) => {
    if (typeof item[0] === 'number') {
      bounds[0] = Math.min(bounds[0], item[0]);
      bounds[1] = Math.min(bounds[1], item[1]);
      bounds[2] = Math.max(bounds[2], item[0]);
      bounds[3] = Math.max(bounds[3], item[1]);
    } else {
      ringBounds(item, bounds);
    }
  });
  return bounds;
};

const featureBounds = (feature) => ringBounds(feature.geometry?.coordinates || [], [Infinity, Infinity, -Infinity, -Infinity]);

const boundsOverlap = (a, b) => a[0] <= b[2] && b[0] <= a[2] && a[1] <= b[3] && b[1] <= a[3];

// Visible part of every feature, bottom to top; fully covered features are dropped.
export const resolveStack = (features) => {
  const stack = (features || []).filter((feature) => feature?.geometry?.coordinates?.length);
  const bounds = stack.map(featureBounds);
  const resolved = [];

  stack.forEach((feature, index) => {
    let visible = feature;
    for (let above = index + 1; above < stack.length && visible; above += 1) {
      if (!boundsOverlap(bounds[index], bounds[above])) continue;
      try {
        visible = difference(featureCollection([visible, stack[above]]));
      } catch {
        // Leave the shape uncut if the geometry library can't handle it.
      }
    }
    if (visible) resolved.push({ ...visible, properties: { ...feature.properties } });
  });

  return resolved;
};
