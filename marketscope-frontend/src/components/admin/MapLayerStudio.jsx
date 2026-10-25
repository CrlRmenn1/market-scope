import React, { useCallback, useEffect, useLayoutEffect, useRef, useState } from 'react';
import L from 'leaflet';
import 'leaflet/dist/leaflet.css';
import '@geoman-io/leaflet-geoman-free';
import '@geoman-io/leaflet-geoman-free/dist/leaflet-geoman.css';
import {
  ArrowDownTrayIcon,
  ArrowUpTrayIcon,
  ExclamationTriangleIcon,
  MapIcon,
  PhotoIcon,
  PlusIcon
} from '@heroicons/react/24/outline';
import { apiUrl } from '../../lib/api';
import { getMapInk, getTileUrl, TILE_ATTRIBUTION } from '../../utils/mapTheme';
import { getHazardStyle, getHazardVar, HAZARD_CLASSES } from '../../utils/hazardStyle';
import { getZoneStyle, ZONING_CLASSES } from '../../utils/zoneStyle';
import { PANABO_BOUNDS } from '../../utils/mapLayers';
import { Card, CardHeader, EmptyState, Field, SegmentedTabs, SkeletonRows, StatusBadge } from './ui/AdminUi';
import { buttonClass, inputClass } from './ui/adminStyles';
import { createTraceOverlay, openPdfFile, readImageFile, renderPdfPage } from './imageTraceOverlay';

// Map Layer Studio: the admin draws, traces (over a PDF/PNG) or imports the
// flood hazard and zoning polygons that scans score against. Layers are saved
// in the database; one layer per category is active at a time.

const CATEGORY_TABS = [
  { id: 'hazard', label: 'Flood hazard' },
  { id: 'zoning', label: 'Zoning' }
];

const CATEGORY_TEXT = {
  hazard: {
    noun: 'flood hazard layer',
    noActive: 'No flood hazard layer is active, so scans treat every spot as Low Risk / Safe.'
  },
  zoning: {
    noun: 'zoning layer',
    noActive: 'No zoning layer is active, so every spot scores 0 for zoning.'
  }
};

const ORIGIN_LABELS = { builtin: 'Built-in', drawn: 'Drawn', imported: 'Imported' };

const ZONE_CLASSES = {
  hazard: HAZARD_CLASSES.map((item) => {
    const style = getHazardStyle(item.var);
    return { id: item.id, label: item.label, color: style.color, fill: style.fillColor, hint: 'flood level' };
  }),
  zoning: ZONING_CLASSES.map((item) => ({ ...item, hint: `scores ${item.score}` }))
};

const IMPORT_ACCEPT = '.geojson,.json,.kml,.zip';
const TRACE_ACCEPT = 'image/png,image/jpeg,application/pdf,.pdf';

const panaboLatLngBounds = () => L.latLngBounds(
  [PANABO_BOUNDS.south, PANABO_BOUNDS.west],
  [PANABO_BOUNDS.north, PANABO_BOUNDS.east]
);

const featureStyle = (category, zoneClass) => (
  category === 'hazard'
    ? getHazardStyle(getHazardVar({ properties: { zone_class: zoneClass } }))
    : getZoneStyle(zoneClass)
);

const classLabel = (category, zoneClass) => (
  ZONE_CLASSES[category].find((item) => item.id === zoneClass)?.label || zoneClass
);

const formatDate = (value) => {
  if (!value) return '';
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? '' : date.toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: 'numeric' });
};

const formatBytes = (bytes) => (bytes >= 1024 * 1024 ? `${(bytes / (1024 * 1024)).toFixed(1)} MB` : `${Math.max(1, Math.round(bytes / 1024))} KB`);

function ClassSwatch({ color, fill }) {
  return <span className="h-3.5 w-3.5 flex-none rounded" style={{ background: fill, boxShadow: `inset 0 0 0 2px ${color}` }} aria-hidden="true" />;
}

function ClassPicker({ category, value, onChange, label }) {
  return (
    <fieldset>
      <legend className="mb-1.5 text-sm font-medium text-[var(--text-main)]">{label}</legend>
      <div className="grid grid-cols-2 gap-1.5">
        {ZONE_CLASSES[category].map((item) => (
          <button
            key={item.id}
            type="button"
            aria-pressed={value === item.id}
            onClick={() => onChange(item.id)}
            className={`flex min-h-[40px] cursor-pointer items-center gap-2 rounded-lg border px-2.5 py-1.5 text-left text-sm transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--focus-ring)] ${value === item.id ? 'border-[var(--accent)] bg-[var(--accent-hover)] text-[var(--text-main)]' : 'border-[var(--border-color)] text-[var(--text-muted)] hover:border-[var(--border-strong)] hover:text-[var(--text-main)]'}`}
          >
            <ClassSwatch color={item.color} fill={item.fill} />
            <span className="min-w-0">
              <span className="block font-medium leading-tight">{item.label}</span>
              <span className="block text-[0.7rem] leading-tight text-[var(--text-muted)]">{item.hint}</span>
            </span>
          </button>
        ))}
      </div>
    </fieldset>
  );
}

export default function MapLayerStudio({ api, notify, token }) {
  const [category, setCategory] = useState('hazard');
  const [layers, setLayers] = useState([]);
  const [loadingLayers, setLoadingLayers] = useState(true);
  const [previewId, setPreviewId] = useState(null);
  const [draft, setDraft] = useState(null); // { id, name, source_note, origin, is_active } while editing
  const [dirty, setDirty] = useState(false);
  const [shapeCount, setShapeCount] = useState(0);
  const [outsideArea, setOutsideArea] = useState(false);
  const [tool, setTool] = useState(null); // 'Polygon' | 'Rectangle' | 'Cut'
  const [newClass, setNewClass] = useState({ hazard: 'very_high', zoning: 'commercial' });
  const [selected, setSelected] = useState(null); // { zoneClass, label, editing, moving }
  const [trace, setTrace] = useState(null); // { name, pageCount, page, opacity, visible, adjustable, lockAspect }
  const [busy, setBusy] = useState('');

  const containerRef = useRef(null);
  const mapRef = useRef(null);
  const previewLayerRef = useRef(null);
  const drawGroupRef = useRef(null);
  const selectedLayerRef = useRef(null);
  const traceRef = useRef(null);
  const pdfRef = useRef(null);
  const importInputRef = useRef(null);
  const traceInputRef = useRef(null);
  const handlersRef = useRef({});
  const categoryRef = useRef(category);
  const toolRef = useRef(tool);

  useLayoutEffect(() => {
    categoryRef.current = category;
    toolRef.current = tool;
  });

  // ---- map setup -------------------------------------------------------------

  useEffect(() => {
    const panabo = panaboLatLngBounds();
    const map = L.map(containerRef.current, {
      minZoom: 12,
      maxBounds: panabo.pad(0.35),
      maxBoundsViscosity: 0.8
    });
    map.fitBounds(panabo);
    L.tileLayer(getTileUrl(), { attribution: TILE_ATTRIBUTION, maxZoom: 19 }).addTo(map);
    L.rectangle(panabo, {
      color: getMapInk(),
      weight: 2.5,
      opacity: 0.85,
      fill: false,
      dashArray: '6 6',
      interactive: false,
      pmIgnore: true
    }).addTo(map);

    const drawGroup = L.featureGroup().addTo(map);
    map.pm.setGlobalOptions({ layerGroup: drawGroup, allowSelfIntersection: false, snapDistance: 14 });

    map.on('pm:create', (event) => handlersRef.current.onCreate?.(event));
    map.on('pm:cut', (event) => handlersRef.current.onCut?.(event));
    map.on('pm:drawend', () => setTool(null));
    map.on('pm:globalcutmodetoggled', (event) => {
      if (!event.enabled) setTool(null);
    });
    map.on('click', () => {
      if (!toolRef.current) handlersRef.current.select?.(null);
    });

    mapRef.current = map;
    drawGroupRef.current = drawGroup;

    const resizeObserver = new ResizeObserver(() => map.invalidateSize());
    resizeObserver.observe(containerRef.current);

    return () => {
      resizeObserver.disconnect();
      traceRef.current?.remove();
      traceRef.current = null;
      map.remove();
      mapRef.current = null;
    };
  }, []);

  // ---- editing helpers (map event handlers call these via handlersRef) ----------

  const refreshShapeStats = () => {
    const shapes = drawGroupRef.current?.getLayers() || [];
    const panabo = panaboLatLngBounds();
    setShapeCount(shapes.length);
    setOutsideArea(shapes.some((layer) => layer.getBounds && !panabo.contains(layer.getBounds())));
  };

  const markChanged = () => {
    setDirty(true);
    refreshShapeStats();
  };

  const applyStyle = (layer) => {
    const zoneClass = layer.feature?.properties?.zone_class;
    const style = featureStyle(categoryRef.current, zoneClass);
    layer.setStyle(layer === selectedLayerRef.current ? { ...style, weight: 4, opacity: 1, dashArray: null } : style);
  };

  const selectLayer = (layer) => {
    const previous = selectedLayerRef.current;
    if (previous && previous !== layer) {
      previous.pm?.disable();
      previous.pm?.disableLayerDrag();
      selectedLayerRef.current = null;
      if (drawGroupRef.current?.hasLayer(previous)) applyStyle(previous);
    }
    selectedLayerRef.current = layer;
    if (!layer) {
      setSelected(null);
      return;
    }
    applyStyle(layer);
    layer.bringToFront();
    const properties = layer.feature?.properties || {};
    setSelected({ zoneClass: properties.zone_class, label: properties.label || '', editing: false, moving: false });
  };

  const decorateLayer = (layer, properties) => {
    layer.feature = { type: 'Feature', properties: { ...properties } };
    applyStyle(layer);
    if (layer._studioBound) return;
    layer._studioBound = true;
    layer.on('click', (event) => {
      if (toolRef.current) return;
      L.DomEvent.stopPropagation(event);
      handlersRef.current.select?.(layer);
    });
    layer.on('pm:edit', () => handlersRef.current.changed?.());
    layer.on('pm:dragend', () => handlersRef.current.changed?.());
  };

  useLayoutEffect(() => {
    handlersRef.current = {
      select: selectLayer,
      changed: markChanged,
      onCreate: ({ layer }) => {
        decorateLayer(layer, { zone_class: newClass[categoryRef.current] });
        markChanged();
        selectLayer(layer);
      },
      onCut: ({ layer, originalLayer }) => {
        const properties = originalLayer?.feature?.properties || layer?.feature?.properties || {};
        const pieces = layer instanceof L.LayerGroup && !(layer instanceof L.Polygon) ? layer.getLayers() : [layer];
        pieces.forEach((piece) => decorateLayer(piece, properties));
        if (selectedLayerRef.current === originalLayer) selectLayer(null);
        markChanged();
      }
    };
  });

  const stopTools = () => {
    const map = mapRef.current;
    if (!map) return;
    map.pm.disableDraw();
    if (map.pm.globalCutModeEnabled()) map.pm.disableGlobalCutMode();
    setTool(null);
  };

  const clearEditor = () => {
    stopTools();
    selectLayer(null);
    drawGroupRef.current?.clearLayers();
    setShapeCount(0);
    setOutsideArea(false);
    setDirty(false);
  };

  const fitTo = (layer) => {
    const bounds = layer?.getBounds?.();
    if (bounds?.isValid()) mapRef.current?.fitBounds(bounds, { padding: [24, 24], maxZoom: 16 });
  };

  const loadIntoEditor = (geojson) => {
    clearEditor();
    L.geoJSON(geojson).eachLayer((layer) => {
      drawGroupRef.current.addLayer(layer);
      decorateLayer(layer, layer.feature?.properties || {});
    });
    refreshShapeStats();
    fitTo(drawGroupRef.current);
  };

  const collectGeoJSON = () => {
    const features = [];
    const add = (layer) => {
      if (layer instanceof L.Polygon) {
        const feature = layer.toGeoJSON(7);
        feature.properties = { ...(layer.feature?.properties || {}) };
        features.push(feature);
      } else if (layer instanceof L.LayerGroup) {
        layer.eachLayer(add);
      }
    };
    drawGroupRef.current?.eachLayer(add);
    return { type: 'FeatureCollection', features };
  };

  // ---- read-only preview of a saved layer ------------------------------------------

  const showPreview = useCallback((geojson, previewCategory) => {
    previewLayerRef.current?.remove();
    previewLayerRef.current = null;
    if (!geojson || !mapRef.current) return;
    previewLayerRef.current = L.geoJSON(geojson, {
      pmIgnore: true,
      style: (feature) => featureStyle(previewCategory, feature?.properties?.zone_class),
      onEachFeature: (feature, layer) => {
        const properties = feature?.properties || {};
        const name = classLabel(previewCategory, properties.zone_class);
        layer.bindTooltip(properties.label ? `${name}: ${properties.label}` : name, { sticky: true });
      }
    }).addTo(mapRef.current);
    const bounds = previewLayerRef.current.getBounds();
    if (bounds.isValid()) mapRef.current.fitBounds(bounds, { padding: [24, 24], maxZoom: 16 });
  }, []);

  const previewLayer = useCallback(async (layerId, previewCategory) => {
    setPreviewId(layerId);
    if (!layerId) {
      showPreview(null, previewCategory);
      return;
    }
    try {
      const data = await api(`/admin/map-layers/${layerId}`);
      if (categoryRef.current === previewCategory) showPreview(data?.layer?.geojson, previewCategory);
    } catch (error) {
      notify('error', error.message);
    }
  }, [api, notify, showPreview]);

  const loadLayers = useCallback(async (listCategory, previewTarget = 'active') => {
    setLoadingLayers(true);
    try {
      const data = await api(`/admin/map-layers?category=${listCategory}`);
      const rows = Array.isArray(data?.layers) ? data.layers : [];
      if (categoryRef.current !== listCategory) return;
      setLayers(rows);
      const targetId = previewTarget === 'active' ? rows.find((layer) => layer.is_active)?.id : previewTarget;
      await previewLayer(targetId || null, listCategory);
    } catch (error) {
      notify('error', error.message);
    } finally {
      setLoadingLayers(false);
    }
  }, [api, notify, previewLayer]);

  useEffect(() => {
    loadLayers(category);
  }, [category, loadLayers]);

  const confirmDiscard = () => !dirty || window.confirm('Discard the unsaved changes to this layer?');

  const changeCategory = (next) => {
    if (next === category || !confirmDiscard()) return;
    closeEditor();
    setLayers([]);
    setCategory(next);
  };

  // ---- starting and finishing an edit ----------------------------------------------

  const openEditor = (nextDraft, geojson) => {
    showPreview(null, category);
    setPreviewId(null);
    setDraft(nextDraft);
    if (geojson) loadIntoEditor(geojson);
    else {
      clearEditor();
      mapRef.current?.fitBounds(panaboLatLngBounds());
    }
  };

  const closeEditor = () => {
    clearEditor();
    traceRef.current?.remove();
    traceRef.current = null;
    pdfRef.current = null;
    setTrace(null);
    setDraft(null);
  };

  const startNewLayer = () => {
    openEditor({ id: null, name: '', source_note: '', origin: 'drawn', is_active: false }, null);
  };

  const editLayer = async (layer, { copy = false } = {}) => {
    setBusy(`load-${layer.id}`);
    try {
      const data = await api(`/admin/map-layers/${layer.id}`);
      const full = data?.layer;
      if (!full) throw new Error('Layer not found.');
      openEditor(
        copy
          ? { id: null, name: `Copy of ${full.name}`.slice(0, 255), source_note: full.source_note || '', origin: 'drawn', is_active: false }
          : { id: full.id, name: full.name, source_note: full.source_note || '', origin: full.origin, is_active: full.is_active },
        full.geojson
      );
    } catch (error) {
      notify('error', error.message);
    } finally {
      setBusy('');
    }
  };

  const cancelEdit = () => {
    if (!confirmDiscard()) return;
    closeEditor();
    loadLayers(category);
  };

  const saveDraft = async (activate) => {
    const name = draft.name.trim();
    if (!name) {
      notify('error', 'Give the layer a name before saving.');
      return;
    }
    const geojson = collectGeoJSON();
    if (!geojson.features.length) {
      notify('error', 'Draw at least one shape before saving.');
      return;
    }
    stopTools();
    setBusy('save');
    try {
      const body = { name, source_note: draft.source_note.trim() || null, geojson };
      let saved;
      if (draft.id) {
        saved = (await api(`/admin/map-layers/${draft.id}`, { method: 'PUT', body }))?.layer;
        if (activate && !draft.is_active) {
          saved = (await api(`/admin/map-layers/${draft.id}/activate`, { method: 'POST' }))?.layer;
        }
      } else {
        saved = (await api('/admin/map-layers', { method: 'POST', body: { ...body, category, activate } }))?.layer;
      }
      const live = activate || saved?.is_active;
      notify('success', live ? `"${name}" is saved and active. New scans use it now.` : `"${name}" is saved. Activate it when it is ready.`);
      closeEditor();
      await loadLayers(category, saved?.id ?? 'active');
    } catch (error) {
      notify('error', error.message);
    } finally {
      setBusy('');
    }
  };

  // ---- layer list actions ------------------------------------------------------------

  const setActive = async (layer, active) => {
    setBusy(`active-${layer.id}`);
    try {
      await api(`/admin/map-layers/${layer.id}/${active ? 'activate' : 'deactivate'}`, { method: 'POST' });
      notify('success', active ? `"${layer.name}" is now the active ${CATEGORY_TEXT[category].noun}.` : `"${layer.name}" is no longer active.`);
      await loadLayers(category, active ? layer.id : 'active');
    } catch (error) {
      notify('error', error.message);
    } finally {
      setBusy('');
    }
  };

  const deleteLayer = async (layer) => {
    const warning = layer.is_active ? ' It is the active layer, so scans will stop using it.' : '';
    if (!window.confirm(`Delete "${layer.name}"?${warning} This cannot be undone.`)) return;
    setBusy(`delete-${layer.id}`);
    try {
      await api(`/admin/map-layers/${layer.id}`, { method: 'DELETE' });
      notify('success', `"${layer.name}" was deleted.`);
      await loadLayers(category);
    } catch (error) {
      notify('error', error.message);
    } finally {
      setBusy('');
    }
  };

  const downloadFile = async (layer, file) => {
    try {
      const response = await fetch(apiUrl(`/admin/map-layers/${layer.id}/files/${file.id}`), { headers: { 'x-admin-token': token || '' } });
      if (!response.ok) throw new Error(`Download failed (${response.status})`);
      const url = URL.createObjectURL(await response.blob());
      const link = document.createElement('a');
      link.href = url;
      link.download = file.filename;
      link.click();
      URL.revokeObjectURL(url);
    } catch (error) {
      notify('error', error.message);
    }
  };

  const importFile = async (event) => {
    const file = event.target.files?.[0];
    event.target.value = '';
    if (!file) return;
    const form = new FormData();
    form.append('file', file);
    form.append('category', category);
    form.append('name', file.name.replace(/\.[^.]+$/, ''));
    setBusy('import');
    try {
      const response = await fetch(apiUrl('/admin/map-layers/import'), {
        method: 'POST',
        headers: { 'x-admin-token': token || '' },
        body: form
      });
      const data = await response.json().catch(() => null);
      if (!response.ok) throw new Error(typeof data?.detail === 'string' ? data.detail : `Import failed (${response.status})`);
      const layer = data.layer;
      notify('success', `Imported ${layer.feature_count} shape${layer.feature_count === 1 ? '' : 's'} from ${file.name}. Check each zone class, then save and activate.`);
      await loadLayers(category, layer.id);
      openEditor({ id: layer.id, name: layer.name, source_note: layer.source_note || '', origin: layer.origin, is_active: false }, layer.geojson);
    } catch (error) {
      notify('error', error.message);
    } finally {
      setBusy('');
    }
  };

  // ---- drawing tools -------------------------------------------------------------------

  const startTool = (nextTool) => {
    const map = mapRef.current;
    if (!map) return;
    stopTools();
    selectLayer(null);
    if (nextTool === 'Cut') {
      map.pm.enableGlobalCutMode({ allowSelfIntersection: false });
    } else {
      const style = featureStyle(category, newClass[category]);
      map.pm.enableDraw(nextTool, {
        pathOptions: style,
        templineStyle: { color: style.color },
        hintlineStyle: { color: style.color, dashArray: '4 6' },
        continueDrawing: false
      });
    }
    setTool(nextTool);
  };

  const undoPoint = () => {
    mapRef.current?.pm.Draw.Polygon?._removeLastVertex?.();
  };

  // ---- the selected shape ----------------------------------------------------------------

  const updateSelected = (changes) => {
    const layer = selectedLayerRef.current;
    if (!layer) return;
    const properties = { ...(layer.feature?.properties || {}) };
    if (changes.zoneClass) properties.zone_class = changes.zoneClass;
    if (changes.label !== undefined) {
      if (changes.label) properties.label = changes.label;
      else delete properties.label;
    }
    layer.feature = { type: 'Feature', properties };
    applyStyle(layer);
    setSelected((current) => ({ ...current, ...changes }));
    markChanged();
  };

  const toggleEditPoints = () => {
    const layer = selectedLayerRef.current;
    if (!layer) return;
    if (layer.pm.enabled()) layer.pm.disable();
    else {
      layer.pm.disableLayerDrag();
      layer.pm.enable({ allowSelfIntersection: false });
    }
    setSelected((current) => ({ ...current, editing: layer.pm.enabled(), moving: false }));
  };

  const toggleMove = () => {
    const layer = selectedLayerRef.current;
    if (!layer) return;
    if (layer.pm.layerDragEnabled()) layer.pm.disableLayerDrag();
    else {
      layer.pm.disable();
      layer.pm.enableLayerDrag();
    }
    setSelected((current) => ({ ...current, moving: layer.pm.layerDragEnabled(), editing: false }));
  };

  const deleteSelected = () => {
    const layer = selectedLayerRef.current;
    if (!layer) return;
    layer.pm.disable();
    layer.pm.disableLayerDrag();
    selectLayer(null);
    drawGroupRef.current.removeLayer(layer);
    markChanged();
  };

  // ---- reference image for tracing ----------------------------------------------------------

  const showTraceImage = (image, settings) => {
    traceRef.current?.remove();
    traceRef.current = createTraceOverlay(mapRef.current, image, { opacity: settings.opacity });
    traceRef.current.setLockAspect(settings.lockAspect);
  };

  const openTraceFile = async (event) => {
    const file = event.target.files?.[0];
    event.target.value = '';
    if (!file) return;
    setBusy('trace');
    try {
      const settings = { opacity: 0.6, visible: true, adjustable: true, lockAspect: true };
      if (file.type === 'application/pdf' || /\.pdf$/i.test(file.name)) {
        const pdf = await openPdfFile(file);
        pdfRef.current = pdf;
        showTraceImage(await renderPdfPage(pdf, 1), settings);
        setTrace({ ...settings, name: file.name, pageCount: pdf.numPages, page: 1 });
      } else {
        pdfRef.current = null;
        showTraceImage(await readImageFile(file), settings);
        setTrace({ ...settings, name: file.name, pageCount: 0, page: 1 });
      }
    } catch (error) {
      notify('error', error.message || 'That file could not be opened.');
    } finally {
      setBusy('');
    }
  };

  const changeTracePage = async (page) => {
    if (!pdfRef.current) return;
    setBusy('trace');
    try {
      showTraceImage(await renderPdfPage(pdfRef.current, page), { ...trace, visible: true, adjustable: true });
      setTrace((current) => ({ ...current, page, visible: true, adjustable: true }));
    } catch (error) {
      notify('error', error.message);
    } finally {
      setBusy('');
    }
  };

  const updateTrace = (changes) => {
    const overlay = traceRef.current;
    if (!overlay) return;
    if (changes.opacity !== undefined) overlay.setOpacity(changes.opacity);
    if (changes.visible !== undefined) overlay.setVisible(changes.visible);
    if (changes.adjustable !== undefined) overlay.setAdjustable(changes.adjustable);
    if (changes.lockAspect !== undefined) overlay.setLockAspect(changes.lockAspect);
    setTrace((current) => ({ ...current, ...changes }));
  };

  const removeTrace = () => {
    traceRef.current?.remove();
    traceRef.current = null;
    pdfRef.current = null;
    setTrace(null);
  };

  // ---- render --------------------------------------------------------------------------------

  const activeLayer = layers.find((layer) => layer.is_active);
  const editing = Boolean(draft);
  const toolHint = {
    Polygon: 'Click to place corners. Click the first corner to finish the shape.',
    Rectangle: 'Click one corner, then the opposite corner.',
    Cut: 'Draw a shape over an existing one to cut that area out of it.'
  }[tool];

  const layerList = (
    <>
      <CardHeader
        title="Saved layers"
        description="Scans use the active layer."
        actions={(
          <button type="button" className={buttonClass.secondary} onClick={() => importInputRef.current?.click()} disabled={busy === 'import'}>
            <ArrowUpTrayIcon className="h-4 w-4" aria-hidden="true" />
            {busy === 'import' ? 'Importing…' : 'Import file'}
          </button>
        )}
      />
      <input ref={importInputRef} type="file" accept={IMPORT_ACCEPT} className="hidden" onChange={importFile} />
      <div className="p-4">
        <button type="button" className={`${buttonClass.primary} w-full`} onClick={startNewLayer}>
          <PlusIcon className="h-4 w-4" aria-hidden="true" />
          New {CATEGORY_TEXT[category].noun}
        </button>
        <p className="mt-2 text-xs text-[var(--text-muted)]">Import accepts GeoJSON, KML, or a zipped shapefile. The original file is kept.</p>
      </div>
      {loadingLayers && <SkeletonRows count={3} />}
      {!loadingLayers && layers.length === 0 && (
        <EmptyState icon={MapIcon} title={`No ${CATEGORY_TEXT[category].noun}s yet`} description="Draw one on the map, trace it from a PDF or image, or import a GIS file." />
      )}
      {!loadingLayers && layers.length > 0 && (
        <ul className="divide-y divide-[var(--border-color)] border-t border-[var(--border-color)]">
          {layers.map((layer) => (
            <li key={layer.id} className={`px-4 py-3 ${previewId === layer.id ? 'bg-[var(--accent-hover)]' : ''}`}>
              <div className="flex items-start justify-between gap-2">
                <button type="button" className="min-w-0 cursor-pointer text-left" onClick={() => previewLayer(layer.id, category)}>
                  <span className="block truncate text-sm font-semibold text-[var(--text-main)]">{layer.name}</span>
                  <span className="mt-0.5 block text-xs text-[var(--text-muted)]">
                    {ORIGIN_LABELS[layer.origin] || layer.origin} · {layer.feature_count} shape{layer.feature_count === 1 ? '' : 's'} · {formatDate(layer.updated_at)}
                  </span>
                  {layer.source_note && <span className="mt-0.5 block text-xs text-[var(--text-muted)] line-clamp-2">{layer.source_note}</span>}
                </button>
                <StatusBadge status={layer.is_active ? 'active' : 'inactive'} />
              </div>
              <div className="-mx-2 mt-1.5 flex flex-wrap items-center">
                <button type="button" className={buttonClass.rowAction} onClick={() => editLayer(layer)} disabled={Boolean(busy)}>Edit</button>
                <button type="button" className={buttonClass.rowAction} onClick={() => setActive(layer, !layer.is_active)} disabled={Boolean(busy)}>
                  {layer.is_active ? 'Deactivate' : 'Activate'}
                </button>
                <button type="button" className={buttonClass.rowAction} onClick={() => editLayer(layer, { copy: true })} disabled={Boolean(busy)}>Duplicate</button>
                {(layer.files || []).map((file) => (
                  <button key={file.id} type="button" className={buttonClass.rowAction} onClick={() => downloadFile(layer, file)} title={`${file.filename} (${formatBytes(file.size_bytes)})`}>
                    <ArrowDownTrayIcon className="mr-1 h-4 w-4" aria-hidden="true" />
                    Original
                  </button>
                ))}
                <button type="button" className={buttonClass.rowDanger} onClick={() => deleteLayer(layer)} disabled={Boolean(busy)}>Delete</button>
              </div>
            </li>
          ))}
        </ul>
      )}
    </>
  );

  const editorPanel = draft && (
    <>
      <CardHeader
        title={draft.id ? 'Edit layer' : `New ${CATEGORY_TEXT[category].noun}`}
        description={draft.is_active ? 'This is the active layer. Saving updates scans right away.' : `${shapeCount} shape${shapeCount === 1 ? '' : 's'}${dirty ? ' · unsaved changes' : ''}`}
      />
      <div className="space-y-5 p-4">
        <ClassPicker
          category={category}
          label="New shapes are"
          value={newClass[category]}
          onChange={(zoneClass) => setNewClass((current) => ({ ...current, [category]: zoneClass }))}
        />

        {selected && (
          <div className="rounded-xl border border-[var(--accent)] p-3">
            <p className="mb-2 text-sm font-semibold text-[var(--text-main)]">Selected shape</p>
            <ClassPicker category={category} label="Zone class" value={selected.zoneClass} onChange={(zoneClass) => updateSelected({ zoneClass })} />
            <Field label="Label (optional)" className="mt-3">
              <input
                className={inputClass}
                value={selected.label}
                maxLength={120}
                placeholder={category === 'hazard' ? 'e.g. Brgy. Gredu riverside' : 'e.g. Poblacion business district'}
                onChange={(event) => updateSelected({ label: event.target.value })}
              />
            </Field>
            <div className="mt-3 grid grid-cols-3 gap-1.5">
              <button type="button" className={`${buttonClass.secondary} px-2 ${selected.editing ? 'border-[var(--accent)] text-[var(--accent)]' : ''}`} onClick={toggleEditPoints} aria-pressed={selected.editing}>
                Points
              </button>
              <button type="button" className={`${buttonClass.secondary} px-2 ${selected.moving ? 'border-[var(--accent)] text-[var(--accent)]' : ''}`} onClick={toggleMove} aria-pressed={selected.moving}>
                Move
              </button>
              <button type="button" className={`${buttonClass.danger} px-2`} onClick={deleteSelected}>Delete</button>
            </div>
            {selected.editing && <p className="mt-2 text-xs text-[var(--text-muted)]">Drag a corner to move it, drag a midpoint to add one, right-click a corner to remove it.</p>}
          </div>
        )}

        <div className="rounded-xl border border-[var(--border-color)] p-3">
          <div className="flex items-center justify-between gap-2">
            <p className="text-sm font-semibold text-[var(--text-main)]">Trace from a map image</p>
            {trace && <button type="button" className={buttonClass.rowDanger} onClick={removeTrace}>Remove</button>}
          </div>
          <input ref={traceInputRef} type="file" accept={TRACE_ACCEPT} className="hidden" onChange={openTraceFile} />
          {!trace ? (
            <>
              <p className="mt-1 text-xs text-[var(--text-muted)]">Put a PDF, PNG or JPG of the printed map over the map, line it up with the roads, then draw on top. The image is not saved.</p>
              <button type="button" className={`${buttonClass.secondary} mt-3 w-full`} onClick={() => traceInputRef.current?.click()} disabled={busy === 'trace'}>
                <PhotoIcon className="h-4 w-4" aria-hidden="true" />
                {busy === 'trace' ? 'Opening…' : 'Choose PDF or image'}
              </button>
            </>
          ) : (
            <div className="mt-2 space-y-3">
              <p className="truncate text-xs text-[var(--text-muted)]" title={trace.name}>{trace.name}</p>
              {trace.pageCount > 1 && (
                <Field label="PDF page">
                  <select className={inputClass} value={trace.page} onChange={(event) => changeTracePage(Number(event.target.value))} disabled={busy === 'trace'}>
                    {Array.from({ length: trace.pageCount }, (_, index) => (
                      <option key={index + 1} value={index + 1}>Page {index + 1}</option>
                    ))}
                  </select>
                </Field>
              )}
              <Field label={`See-through: ${Math.round((1 - trace.opacity) * 100)}%`}>
                <input
                  type="range"
                  min="0.1"
                  max="1"
                  step="0.05"
                  value={trace.opacity}
                  onChange={(event) => updateTrace({ opacity: Number(event.target.value) })}
                  className="w-full accent-[var(--accent)]"
                />
              </Field>
              <div className="space-y-2 text-sm text-[var(--text-main)]">
                <label className="flex cursor-pointer items-center gap-2">
                  <input type="checkbox" checked={trace.visible} onChange={(event) => updateTrace({ visible: event.target.checked })} className="h-4 w-4 accent-[var(--accent)]" />
                  Show image
                </label>
                <label className="flex cursor-pointer items-center gap-2">
                  <input type="checkbox" checked={trace.adjustable} disabled={!trace.visible} onChange={(event) => updateTrace({ adjustable: event.target.checked })} className="h-4 w-4 accent-[var(--accent)]" />
                  Show handles to move and resize
                </label>
                <label className="flex cursor-pointer items-center gap-2">
                  <input type="checkbox" checked={trace.lockAspect} onChange={(event) => updateTrace({ lockAspect: event.target.checked })} className="h-4 w-4 accent-[var(--accent)]" />
                  Keep proportions
                </label>
              </div>
              <button type="button" className={`${buttonClass.ghost} w-full`} onClick={() => traceRef.current?.fitView()}>Zoom to image</button>
            </div>
          )}
        </div>

        <Field label="Layer name" required>
          <input
            className={inputClass}
            value={draft.name}
            maxLength={255}
            placeholder={category === 'hazard' ? 'e.g. CDRRMO flood map 2026' : 'e.g. CLUP 2026 land use'}
            onChange={(event) => {
              setDraft((current) => ({ ...current, name: event.target.value }));
              setDirty(true);
            }}
          />
        </Field>
        <Field label="Source note" hint="Where the shapes came from, for other admins.">
          <textarea
            className={`${inputClass} min-h-[72px]`}
            value={draft.source_note}
            placeholder="e.g. Traced from the printed CDRRMO hazard map"
            onChange={(event) => {
              setDraft((current) => ({ ...current, source_note: event.target.value }));
              setDirty(true);
            }}
          />
        </Field>

        <div className="grid gap-2">
          {!draft.is_active && (
            <button type="button" className={buttonClass.primary} onClick={() => saveDraft(true)} disabled={busy === 'save'}>
              {busy === 'save' ? 'Saving…' : 'Save and activate'}
            </button>
          )}
          <button type="button" className={draft.is_active ? buttonClass.primary : buttonClass.secondary} onClick={() => saveDraft(false)} disabled={busy === 'save'}>
            {draft.is_active ? (busy === 'save' ? 'Saving…' : 'Save changes') : 'Save without activating'}
          </button>
          <button type="button" className={buttonClass.ghost} onClick={cancelEdit} disabled={busy === 'save'}>
            {dirty ? 'Discard changes' : 'Close editor'}
          </button>
        </div>
      </div>
    </>
  );

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <SegmentedTabs tabs={CATEGORY_TABS} value={category} onChange={changeCategory} ariaLabel="Layer type" />
        {!editing && activeLayer && (
          <p className="text-sm text-[var(--text-muted)]">
            Active: <span className="font-semibold text-[var(--text-main)]">{activeLayer.name}</span>
          </p>
        )}
      </div>

      {!loadingLayers && !activeLayer && !editing && (
        <div role="status" className="flex items-start gap-3 rounded-xl border border-[var(--trend-down)] bg-[var(--trend-down-bg)] px-4 py-3 text-sm text-[var(--trend-down)]">
          <ExclamationTriangleIcon className="mt-0.5 h-5 w-5 flex-none" aria-hidden="true" />
          <p className="font-medium">{CATEGORY_TEXT[category].noActive}</p>
        </div>
      )}

      <div className="grid gap-5 lg:grid-cols-[minmax(0,1fr)_minmax(300px,360px)]">
        <Card className="min-w-0 overflow-hidden">
          {editing && (
            <div className="flex flex-wrap items-center gap-2 border-b border-[var(--border-color)] px-4 py-3">
              {['Polygon', 'Rectangle', 'Cut'].map((item) => (
                <button
                  key={item}
                  type="button"
                  aria-pressed={tool === item}
                  className={`${buttonClass.secondary} ${tool === item ? 'border-[var(--accent)] text-[var(--accent)]' : ''}`}
                  onClick={() => (tool === item ? stopTools() : startTool(item))}
                >
                  {item === 'Polygon' ? 'Draw shape' : item === 'Rectangle' ? 'Draw box' : 'Cut out'}
                </button>
              ))}
              {tool === 'Polygon' && <button type="button" className={buttonClass.ghost} onClick={undoPoint}>Undo point</button>}
              {tool && <button type="button" className={buttonClass.ghost} onClick={stopTools}>Cancel</button>}
            </div>
          )}
          {(toolHint || (editing && outsideArea)) && (
            <div className="space-y-1 border-b border-[var(--border-color)] px-4 py-2 text-xs">
              {toolHint && <p className="text-[var(--text-muted)]">{toolHint}</p>}
              {editing && outsideArea && <p className="font-medium text-[var(--trend-down)]">Some shapes go past the dashed Panabo main area. Those parts are trimmed off when you save.</p>}
            </div>
          )}
          <div className="relative">
            <div ref={containerRef} className="map-layer-studio-map h-[60svh] min-h-[360px] w-full lg:h-[620px]" />
            {!editing && (
              <div className="pointer-events-none absolute bottom-3 left-3 z-[450] flex flex-wrap gap-x-3 gap-y-1 rounded-lg bg-[var(--bg-glass)] px-3 py-2 text-xs text-[var(--text-main)] shadow">
                {ZONE_CLASSES[category].map((item) => (
                  <span key={item.id} className="inline-flex items-center gap-1.5">
                    <ClassSwatch color={item.color} fill={item.fill} />
                    {item.label}
                  </span>
                ))}
              </div>
            )}
          </div>
        </Card>

        <Card className="min-w-0 self-start overflow-hidden">
          {editing ? editorPanel : layerList}
        </Card>
      </div>
    </div>
  );
}
