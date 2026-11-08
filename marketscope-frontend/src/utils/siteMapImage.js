import { TILE_URLS } from './mapTheme';
import { fetchActiveMapLayer } from './mapLayers';
import { getHazardStyle, getHazardVar } from './hazardStyle';

// A still image of the site map for the PDF report: OSM tiles around the site with
// the scan radius, site pin, competitors, counted anchors and flood hazard zones drawn
// on top (the same things the report screen's map shows). Leaflet's live map can't be
// captured reliably, so this draws its own on a canvas.

const TILE_SIZE = 256;
const INK = '#7c3aed';
const ANCHOR_INK = '#171717';
const EARTH = 156543.03392; // metres per pixel at zoom 0 on the equator
const TILE_TIMEOUT_MS = 8000;

export const HAZARD_LEGEND = [
  { var: 1, label: 'Very high flood hazard' },
  { var: 2, label: 'High flood hazard' },
  { var: 3, label: 'Moderate flood hazard' }
].map((item) => ({ ...item, ...getHazardStyle(item.var) }));

const metresPerPixel = (lat, zoom) => (EARTH * Math.cos((lat * Math.PI) / 180)) / 2 ** zoom;

// World pixel position of a point at a (possibly fractional) zoom.
const project = (lat, lng, zoom) => {
  const scale = TILE_SIZE * 2 ** zoom;
  const sin = Math.sin((lat * Math.PI) / 180);
  return {
    x: ((lng + 180) / 360) * scale,
    y: (0.5 - Math.log((1 + sin) / (1 - sin)) / (4 * Math.PI)) * scale
  };
};

const tileUrl = (z, x, y) => {
  const subdomain = 'abc'[(x + y) % 3];
  // Own URL so the tile cache (public/sw.js) can't answer with a copy a canvas may not read.
  return `${TILE_URLS.light.replace('{s}', subdomain).replace('{z}', z).replace('{x}', x).replace('{y}', y)}?print=1`;
};

const loadImage = (url) => new Promise((resolve) => {
  const image = new Image();
  const timer = setTimeout(() => resolve(null), TILE_TIMEOUT_MS);
  image.crossOrigin = 'anonymous';
  image.onload = () => { clearTimeout(timer); resolve(image); };
  image.onerror = () => { clearTimeout(timer); resolve(null); };
  image.src = url;
});

const polygonsOf = (geometry) => {
  if (!geometry) return [];
  if (geometry.type === 'Polygon') return [geometry.coordinates];
  if (geometry.type === 'MultiPolygon') return geometry.coordinates;
  return [];
};

// A round number of metres for the scale bar, about a fifth of the map width.
const niceDistance = (metres) => {
  const steps = [25, 50, 100, 200, 250, 500, 1000, 2000, 5000];
  return steps.reduce((best, step) => (step <= metres ? step : best), steps[0]);
};

/**
 * Renders the site map. Returns { dataUrl, hazardLegend, tilesShown } or null when no
 * image could be made. center: { lat, lng }. Points are { lat, lng } objects.
 */
export const renderSiteMapImage = async ({
  center,
  radiusMeters = 340,
  competitors = [],
  anchors = [],
  competitorColor = '#ef4444',
  widthPx = 1000,
  heightPx = 560
}) => {
  if (!center || !Number.isFinite(center.lat) || !Number.isFinite(center.lng)) return null;

  const width = Math.round(widthPx);
  const height = Math.round(heightPx);

  // Fit the scan circle with some room around it, then draw whole-zoom tiles scaled to fit.
  const wantedMpp = (radiusMeters * 2 * 1.35) / Math.min(width, height);
  const idealZoom = Math.min(18, Math.max(12, Math.log2((EARTH * Math.cos((center.lat * Math.PI) / 180)) / wantedMpp)));
  const tileZoom = Math.round(idealZoom);
  const scale = 2 ** (idealZoom - tileZoom);
  const mpp = metresPerPixel(center.lat, idealZoom);

  const middle = project(center.lat, center.lng, idealZoom);
  const originX = middle.x - width / 2;
  const originY = middle.y - height / 2;
  const toCanvas = (lat, lng) => {
    const point = project(lat, lng, idealZoom);
    return { x: point.x - originX, y: point.y - originY };
  };

  const hazardRequest = fetchActiveMapLayer('hazard').catch(() => null);

  const drawnTile = TILE_SIZE * scale;
  const tileCount = 2 ** tileZoom;
  const firstX = Math.floor(originX / drawnTile);
  const lastX = Math.floor((originX + width) / drawnTile);
  const firstY = Math.floor(originY / drawnTile);
  const lastY = Math.floor((originY + height) / drawnTile);
  const tiles = [];
  for (let tx = firstX; tx <= lastX; tx += 1) {
    for (let ty = firstY; ty <= lastY; ty += 1) {
      if (ty < 0 || ty >= tileCount) continue;
      const wrappedX = ((tx % tileCount) + tileCount) % tileCount;
      tiles.push(loadImage(tileUrl(tileZoom, wrappedX, ty)).then((image) => ({ image, tx, ty })));
    }
  }

  const canvas = document.createElement('canvas');
  canvas.width = width;
  canvas.height = height;
  const ctx = canvas.getContext('2d');
  ctx.fillStyle = '#eef0f3';
  ctx.fillRect(0, 0, width, height);

  let tilesShown = 0;
  (await Promise.all(tiles)).forEach(({ image, tx, ty }) => {
    if (!image) return;
    ctx.drawImage(image, tx * drawnTile - originX, ty * drawnTile - originY, drawnTile + 0.5, drawnTile + 0.5);
    tilesShown += 1;
  });
  // Soften the base map a little so the overlays stand out on paper.
  ctx.fillStyle = 'rgba(255, 255, 255, 0.18)';
  ctx.fillRect(0, 0, width, height);

  // Flood hazard zones. Only the classes that show up in view go in the legend.
  const hazardClasses = new Set();
  const hazard = await hazardRequest;
  (hazard?.features || []).forEach((feature) => {
    const hazardVar = getHazardVar(feature);
    const style = getHazardStyle(hazardVar);
    polygonsOf(feature.geometry).forEach((rings) => {
      const points = rings.map((ring) => ring.map(([lng, lat]) => toCanvas(lat, lng)));
      const outer = points[0] || [];
      const xs = outer.map((point) => point.x);
      const ys = outer.map((point) => point.y);
      const inView = outer.length > 0
        && Math.max(...xs) >= 0 && Math.min(...xs) <= width
        && Math.max(...ys) >= 0 && Math.min(...ys) <= height;
      if (!inView) return;

      ctx.beginPath();
      points.forEach((ring) => {
        ring.forEach((point, index) => {
          if (index === 0) ctx.moveTo(point.x, point.y);
          else ctx.lineTo(point.x, point.y);
        });
        ctx.closePath();
      });
      ctx.globalAlpha = style.fillOpacity ?? 0.2;
      ctx.fillStyle = style.fillColor;
      ctx.fill('evenodd');
      ctx.globalAlpha = style.opacity ?? 0.9;
      ctx.strokeStyle = style.color;
      ctx.lineWidth = (style.weight || 1.5) * 1.2;
      ctx.setLineDash(style.dashArray ? style.dashArray.split(' ').map(Number) : []);
      ctx.stroke();
      ctx.globalAlpha = 1;
      ctx.setLineDash([]);
      hazardClasses.add(hazardVar);
    });
  });

  // Scan radius.
  const centre = toCanvas(center.lat, center.lng);
  ctx.beginPath();
  ctx.arc(centre.x, centre.y, radiusMeters / mpp, 0, Math.PI * 2);
  ctx.fillStyle = 'rgba(124, 58, 237, 0.07)';
  ctx.fill();
  ctx.lineWidth = 3;
  ctx.strokeStyle = INK;
  ctx.stroke();

  const inside = (point, pad = 10) => point.x > -pad && point.y > -pad && point.x < width + pad && point.y < height + pad;

  // Counted anchors (diamonds).
  anchors.forEach((anchor) => {
    const point = toCanvas(anchor.lat, anchor.lng);
    if (!inside(point)) return;
    ctx.save();
    ctx.translate(point.x, point.y);
    ctx.rotate(Math.PI / 4);
    ctx.fillStyle = ANCHOR_INK;
    ctx.strokeStyle = '#ffffff';
    ctx.lineWidth = 2;
    ctx.fillRect(-6, -6, 12, 12);
    ctx.strokeRect(-6, -6, 12, 12);
    ctx.restore();
  });

  // Competitors.
  competitors.forEach((competitor) => {
    const point = toCanvas(competitor.lat, competitor.lng);
    if (!inside(point)) return;
    ctx.beginPath();
    ctx.arc(point.x, point.y, 7, 0, Math.PI * 2);
    ctx.fillStyle = competitorColor;
    ctx.fill();
    ctx.lineWidth = 2.5;
    ctx.strokeStyle = '#ffffff';
    ctx.stroke();
  });

  // Proposed site.
  ctx.beginPath();
  ctx.arc(centre.x, centre.y, 16, 0, Math.PI * 2);
  ctx.fillStyle = 'rgba(124, 58, 237, 0.22)';
  ctx.fill();
  ctx.lineWidth = 2;
  ctx.strokeStyle = 'rgba(124, 58, 237, 0.7)';
  ctx.stroke();
  ctx.beginPath();
  ctx.arc(centre.x, centre.y, 7, 0, Math.PI * 2);
  ctx.fillStyle = INK;
  ctx.fill();
  ctx.lineWidth = 2.5;
  ctx.strokeStyle = '#ffffff';
  ctx.stroke();

  // Scale bar (bottom left).
  const barMetres = niceDistance((width / 5) * mpp);
  const barPx = barMetres / mpp;
  const barLabel = barMetres >= 1000 ? `${barMetres / 1000} km` : `${barMetres} m`;
  ctx.fillStyle = 'rgba(255, 255, 255, 0.85)';
  ctx.fillRect(12, height - 40, barPx + 20, 28);
  ctx.strokeStyle = '#111827';
  ctx.lineWidth = 2;
  ctx.beginPath();
  ctx.moveTo(22, height - 22);
  ctx.lineTo(22, height - 16);
  ctx.lineTo(22 + barPx, height - 16);
  ctx.lineTo(22 + barPx, height - 22);
  ctx.stroke();
  ctx.font = '600 13px Helvetica, Arial, sans-serif';
  ctx.fillStyle = '#111827';
  ctx.fillText(barLabel, 24, height - 25);

  // Attribution (bottom right), required by the OSM tile licence.
  if (tilesShown > 0) {
    const credit = '\u00A9 OpenStreetMap contributors';
    ctx.font = '12px Helvetica, Arial, sans-serif';
    const creditWidth = ctx.measureText(credit).width;
    ctx.fillStyle = 'rgba(255, 255, 255, 0.85)';
    ctx.fillRect(width - creditWidth - 16, height - 22, creditWidth + 16, 22);
    ctx.fillStyle = '#374151';
    ctx.fillText(credit, width - creditWidth - 8, height - 7);
  }

  try {
    return {
      dataUrl: canvas.toDataURL('image/jpeg', 0.9),
      hazardLegend: HAZARD_LEGEND.filter((item) => hazardClasses.has(item.var)),
      tilesShown
    };
  } catch (error) {
    // A tile the browser won't let us read back ("tainted" canvas): leave the map out.
    console.warn('Site map image could not be exported:', error);
    return null;
  }
};
