import L from 'leaflet';

// Reference image for tracing a paper/PDF map in the Map Layer Studio.
// The image only lives in the browser (an object URL); it is never uploaded.

const MIN_SIZE_PX = 24;

// ---- reading the file --------------------------------------------------------

export const readImageFile = (file) => new Promise((resolve, reject) => {
  const url = URL.createObjectURL(file);
  const image = new Image();
  image.onload = () => resolve({ url, width: image.naturalWidth, height: image.naturalHeight });
  image.onerror = () => {
    URL.revokeObjectURL(url);
    reject(new Error('That image could not be opened.'));
  };
  image.src = url;
});

// pdf.js is large, so it only loads when an admin opens a PDF.
const loadPdfJs = async () => {
  const [pdfjs, worker] = await Promise.all([
    import('pdfjs-dist'),
    import('pdfjs-dist/build/pdf.worker.min.mjs?url')
  ]);
  pdfjs.GlobalWorkerOptions.workerSrc = worker.default;
  return pdfjs;
};

export const openPdfFile = async (file) => {
  const pdfjs = await loadPdfJs();
  const data = new Uint8Array(await file.arrayBuffer());
  return pdfjs.getDocument({ data }).promise;
};

// Render one PDF page to a PNG object URL, at most maxSide pixels on its long side.
export const renderPdfPage = async (pdf, pageNumber, maxSide = 2400) => {
  const page = await pdf.getPage(pageNumber);
  const base = page.getViewport({ scale: 1 });
  const scale = Math.min(4, maxSide / Math.max(base.width, base.height));
  const viewport = page.getViewport({ scale });
  const canvas = document.createElement('canvas');
  canvas.width = Math.round(viewport.width);
  canvas.height = Math.round(viewport.height);
  await page.render({ canvas, viewport, background: '#ffffff' }).promise;
  const blob = await new Promise((resolve) => canvas.toBlob(resolve, 'image/png'));
  if (!blob) throw new Error('That PDF page could not be rendered.');
  return { url: URL.createObjectURL(blob), width: canvas.width, height: canvas.height };
};

// ---- the overlay on the map ----------------------------------------------------

const handleIcon = (modifier, size) => L.divIcon({
  className: `trace-handle trace-handle--${modifier}`,
  iconSize: [size, size]
});

// Puts the image over the current view and returns controls for it. Two corner
// handles resize it (keeping its proportions unless lockAspect is off) and the
// center handle moves it.
export function createTraceOverlay(map, { url, width, height }, { opacity = 0.6 } = {}) {
  if (!map.getPane('tracePane')) {
    map.createPane('tracePane');
    // Below the overlay pane (400) so traced polygons stay on top of the image.
    map.getPane('tracePane').style.zIndex = 350;
  }

  const aspect = width / height;
  const view = map.getSize();
  const scale = Math.min((view.x * 0.8) / width, (view.y * 0.8) / height);
  const center = view.divideBy(2);
  let northWest = map.containerPointToLatLng([center.x - (width * scale) / 2, center.y - (height * scale) / 2]);
  let southEast = map.containerPointToLatLng([center.x + (width * scale) / 2, center.y + (height * scale) / 2]);
  let lockAspect = true;
  let adjustable = true;

  const overlay = L.imageOverlay(url, [northWest, southEast], {
    pane: 'tracePane',
    opacity,
    interactive: false,
    pmIgnore: true
  }).addTo(map);

  const markerOptions = (icon) => ({ draggable: true, icon, keyboard: false, pmIgnore: true, zIndexOffset: 1000 });
  const nwHandle = L.marker(northWest, markerOptions(handleIcon('corner', 18)));
  const seHandle = L.marker(southEast, markerOptions(handleIcon('corner', 18)));
  const moveHandle = L.marker(L.latLngBounds(northWest, southEast).getCenter(), markerOptions(handleIcon('move', 30)));
  const handles = [nwHandle, seHandle, moveHandle];

  const redraw = () => {
    overlay.setBounds(L.latLngBounds(northWest, southEast));
    nwHandle.setLatLng(northWest);
    seHandle.setLatLng(southEast);
    moveHandle.setLatLng(L.latLngBounds(northWest, southEast).getCenter());
  };

  // Work in layer pixels so "keep proportions" matches what the admin sees.
  const resizeFrom = (corner, latlng) => {
    const fixed = map.latLngToLayerPoint(corner === 'nw' ? southEast : northWest);
    const dragged = map.latLngToLayerPoint(latlng);
    const direction = corner === 'nw' ? -1 : 1;
    const widthPx = Math.max(MIN_SIZE_PX, (dragged.x - fixed.x) * direction);
    let heightPx = Math.max(MIN_SIZE_PX, (dragged.y - fixed.y) * direction);
    if (lockAspect) heightPx = widthPx / aspect;
    const moved = map.layerPointToLatLng(L.point(fixed.x + widthPx * direction, fixed.y + heightPx * direction));
    if (corner === 'nw') northWest = moved;
    else southEast = moved;
    redraw();
  };

  nwHandle.on('drag', (event) => resizeFrom('nw', event.target.getLatLng()));
  seHandle.on('drag', (event) => resizeFrom('se', event.target.getLatLng()));

  let moveStart = null;
  moveHandle.on('dragstart', (event) => {
    moveStart = { latlng: event.target.getLatLng(), northWest, southEast };
  });
  moveHandle.on('drag', (event) => {
    if (!moveStart) return;
    const now = event.target.getLatLng();
    const dLat = now.lat - moveStart.latlng.lat;
    const dLng = now.lng - moveStart.latlng.lng;
    northWest = L.latLng(moveStart.northWest.lat + dLat, moveStart.northWest.lng + dLng);
    southEast = L.latLng(moveStart.southEast.lat + dLat, moveStart.southEast.lng + dLng);
    overlay.setBounds(L.latLngBounds(northWest, southEast));
    nwHandle.setLatLng(northWest);
    seHandle.setLatLng(southEast);
  });
  moveHandle.on('dragend', () => {
    moveStart = null;
  });

  const showHandles = (show) => {
    handles.forEach((handle) => {
      if (show && !map.hasLayer(handle)) handle.addTo(map);
      if (!show && map.hasLayer(handle)) handle.remove();
    });
  };
  showHandles(true);

  return {
    setOpacity: (value) => overlay.setOpacity(value),
    setVisible: (visible) => {
      if (visible && !map.hasLayer(overlay)) overlay.addTo(map);
      if (!visible && map.hasLayer(overlay)) overlay.remove();
      showHandles(visible && adjustable);
    },
    setAdjustable: (value) => {
      adjustable = value;
      showHandles(value && map.hasLayer(overlay));
    },
    setLockAspect: (value) => {
      lockAspect = value;
    },
    fitView: () => map.fitBounds(L.latLngBounds(northWest, southEast), { padding: [24, 24] }),
    remove: () => {
      showHandles(false);
      overlay.remove();
      URL.revokeObjectURL(url);
    }
  };
}
