import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { MapPinIcon } from '@heroicons/react/24/outline';
import AnchorsMap from '../../components/admin/AnchorsMap';
import { ANCHOR_SOURCE_COLORS } from '../../components/admin/anchorColors';
import CoordinateFields from '../../components/admin/ui/CoordinateFields';
import DataBackupButtons from '../../components/admin/ui/DataBackupButtons';
import { useConfirm } from '../../components/common/useConfirm';
import { Card, CardHeader, EmptyState, Field, PageHeader, SearchField, SkeletonRows } from '../../components/admin/ui/AdminUi';
import { buttonClass, inputClass } from '../../components/admin/ui/adminStyles';

const EMPTY_FORM = { name: '', category: '', power: '15', latitude: '', longitude: '', note: '' };

const SOURCE_LABELS = { admin: 'Added here', seed: 'Original list', osm: 'OpenStreetMap' };

const TIER_LABELS = { major: 'Major', medium: 'Medium', minor: 'Minor' };

const FILTERS = [
  { value: 'all', label: 'All anchors' },
  { value: 'admin', label: 'Added here' },
  { value: 'seed', label: 'Original list' },
  { value: 'osm', label: 'OpenStreetMap' },
  { value: 'edited', label: 'Corrected' },
  { value: 'off', label: 'Hidden or duplicate' }
];

const refOf = (anchor) => anchor.osm_ref || `row-${anchor.id}`;

const matchesFilter = (anchor, filter) => {
  if (filter === 'all') return true;
  if (filter === 'off') return anchor.status !== 'active';
  if (filter === 'edited') return Boolean(anchor.edited);
  return anchor.origin === filter;
};

const statusText = (anchor) => {
  if (anchor.status === 'hidden') return 'Hidden, not counted in scans';
  if (anchor.status === 'duplicate') return `Same place as "${anchor.duplicate_of}", so counted once`;
  return null;
};

// Anchors: places that bring people to an area, which raise the score of sites near
// them. The admin adds the ones OpenStreetMap is missing and corrects the ones it gets
// wrong. Every scan uses the merged list (backend: services/anchors.py).
export default function AnchorsPage({ api, notify, isDesktop, token }) {
  const [anchors, setAnchors] = useState([]);
  const [categories, setCategories] = useState({});
  const [tiers, setTiers] = useState({});
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState('');
  const [filter, setFilter] = useState('all');
  const [form, setForm] = useState(EMPTY_FORM);
  const [editing, setEditing] = useState(null);
  const [isFormOpen, setIsFormOpen] = useState(false);
  const [saving, setSaving] = useState(false);
  const [busyRef, setBusyRef] = useState(null);
  const [focus, setFocus] = useState(null);
  const formRef = useRef(null);
  const confirm = useConfirm();

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const data = await api('/admin/anchors');
      setAnchors(Array.isArray(data?.anchors) ? data.anchors : []);
      setCategories(data?.categories || {});
      setTiers(data?.power_tiers || {});
    } catch (error) {
      notify('error', error.message);
    } finally {
      setLoading(false);
    }
  }, [api, notify]);

  useEffect(() => {
    load();
  }, [load]);

  const rows = useMemo(() => {
    const query = search.trim().toLowerCase();
    return anchors
      .filter((anchor) => matchesFilter(anchor, filter))
      .filter((anchor) => !query || String(anchor.name).toLowerCase().includes(query) || String(categories[anchor.category]?.label || '').toLowerCase().includes(query))
      .sort((a, b) => b.power - a.power || String(a.name).localeCompare(String(b.name)));
  }, [anchors, categories, filter, search]);

  const counted = useMemo(() => anchors.filter((anchor) => anchor.status === 'active').length, [anchors]);

  const draft = useMemo(() => {
    const lat = Number(form.latitude);
    const lng = Number(form.longitude);
    if (!isFormOpen || !form.latitude || !form.longitude || Number.isNaN(lat) || Number.isNaN(lng)) return null;
    return { lat, lng };
  }, [form.latitude, form.longitude, isFormOpen]);

  const scrollToForm = () => {
    if (!isDesktop) requestAnimationFrame(() => formRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' }));
  };

  const setCoords = (lat, lng) => {
    setIsFormOpen(true);
    setForm((current) => ({ ...current, latitude: lat.toFixed(6), longitude: lng.toFixed(6) }));
    scrollToForm();
  };

  const closeForm = () => {
    setForm(EMPTY_FORM);
    setEditing(null);
    setIsFormOpen(false);
  };

  const startEdit = (anchor) => {
    setEditing(anchor);
    setIsFormOpen(true);
    setForm({
      name: anchor.name || '',
      category: anchor.category || '',
      power: String(anchor.power ?? 15),
      latitude: String(anchor.lat ?? ''),
      longitude: String(anchor.lon ?? ''),
      note: anchor.note || ''
    });
    setFocus({ lat: anchor.lat, lng: anchor.lon });
    scrollToForm();
  };

  // Saves a correction or a hide for an OSM anchor; both use the same endpoint.
  const saveOsmRow = (anchor, values) => api('/admin/anchors', {
    method: 'POST',
    body: {
      name: anchor.name,
      category: anchor.category,
      latitude: anchor.lat,
      longitude: anchor.lon,
      power: anchor.power,
      note: anchor.note,
      is_active: anchor.status !== 'hidden',
      ...values,
      osm_ref: anchor.osm_ref
    }
  });

  const submit = async (event) => {
    event.preventDefault();
    const payload = {
      name: form.name.trim(),
      category: form.category,
      power: Number(form.power),
      latitude: Number(form.latitude),
      longitude: Number(form.longitude),
      note: form.note.trim() || null
    };
    if (!payload.name || !payload.category || !form.latitude || !form.longitude || Number.isNaN(payload.latitude) || Number.isNaN(payload.longitude)) {
      notify('error', 'Fill in the name and category, and place the anchor on the map.');
      return;
    }

    setSaving(true);
    try {
      if (editing?.id) {
        await api(`/admin/anchors/${editing.id}`, { method: 'PUT', body: { ...payload, is_active: editing.status !== 'hidden' } });
        notify('success', `"${payload.name}" was updated. New scans will use it.`);
      } else if (editing?.osm_ref) {
        await saveOsmRow(editing, payload);
        notify('success', `"${payload.name}" was corrected. New scans will use it.`);
      } else {
        await api('/admin/anchors', { method: 'POST', body: payload });
        notify('success', `"${payload.name}" was added. New scans will count it.`);
      }
      closeForm();
      await load();
    } catch (error) {
      notify('error', error.message);
    } finally {
      setSaving(false);
    }
  };

  const toggleHidden = async (anchor) => {
    const hide = anchor.status !== 'hidden';
    setBusyRef(refOf(anchor));
    try {
      if (anchor.id) {
        await api(`/admin/anchors/${anchor.id}`, {
          method: 'PUT',
          body: { name: anchor.name, category: anchor.category, latitude: anchor.lat, longitude: anchor.lon, power: anchor.power, note: anchor.note, is_active: !hide }
        });
      } else {
        await saveOsmRow(anchor, { is_active: false });
      }
      notify('success', hide ? `"${anchor.name}" is hidden and won't count in new scans.` : `"${anchor.name}" counts in new scans again.`);
      if (editing && refOf(editing) === refOf(anchor)) closeForm();
      await load();
    } catch (error) {
      notify('error', error.message);
    } finally {
      setBusyRef(null);
    }
  };

  const remove = async (anchor) => {
    const isCorrection = anchor.origin === 'osm';
    const confirmed = await confirm({
      title: isCorrection ? `Undo your changes to "${anchor.name}"?` : `Delete "${anchor.name}"?`,
      message: isCorrection
        ? 'It goes back to what OpenStreetMap says, and counts in scans again.'
        : 'It will stop counting in scans. This cannot be undone.',
      confirmLabel: isCorrection ? 'Undo changes' : 'Delete anchor'
    });
    if (!confirmed) return;
    setBusyRef(refOf(anchor));
    try {
      await api(`/admin/anchors/${anchor.id}`, { method: 'DELETE' });
      notify('success', isCorrection ? `"${anchor.name}" is back to the OpenStreetMap version.` : `"${anchor.name}" was deleted.`);
      if (editing && refOf(editing) === refOf(anchor)) closeForm();
      await load();
    } catch (error) {
      notify('error', error.message);
    } finally {
      setBusyRef(null);
    }
  };

  const powerOptions = useMemo(() => {
    const options = Object.entries(tiers).map(([key, value]) => ({ value: String(value), label: `${TIER_LABELS[key] || key} (${value})` }));
    if (form.power && !options.some((option) => option.value === String(form.power))) {
      options.push({ value: String(form.power), label: `Current (${form.power})` });
    }
    return options.sort((a, b) => Number(b.value) - Number(a.value));
  }, [form.power, tiers]);

  const bands = categories[form.category]?.bands_m || null;
  const selectedRef = editing ? refOf(editing) : null;
  const isAddingOrEditing = isFormOpen;

  const formCard = (
    <div ref={formRef}>
      <Card>
        <CardHeader
          title={editing ? `Edit ${editing.name}` : 'Add an anchor'}
          description={editing?.origin === 'osm'
            ? 'Your changes replace what OpenStreetMap says about this place.'
            : 'Click the map or drag the pin to place it.'}
        />
        <form onSubmit={submit} className="space-y-4 p-5">
          <Field label="Name" required>
            <input className={inputClass} value={form.name} onChange={(e) => setForm((c) => ({ ...c, name: e.target.value }))} placeholder="e.g. NCCC Mall Panabo" maxLength={200} required />
          </Field>
          <div className="grid gap-3 sm:grid-cols-2">
            <Field label="Category" required>
              <select className={inputClass} value={form.category} onChange={(e) => setForm((c) => ({ ...c, category: e.target.value }))} required>
                <option value="">Choose...</option>
                {Object.entries(categories).map(([key, category]) => (
                  <option key={key} value={key}>{category.label}</option>
                ))}
              </select>
            </Field>
            <Field label="Importance" required hint="How many people it draws">
              <select className={inputClass} value={form.power} onChange={(e) => setForm((c) => ({ ...c, power: e.target.value }))} required>
                {powerOptions.map((option) => (
                  <option key={option.value} value={option.value}>{option.label}</option>
                ))}
              </select>
            </Field>
          </div>
          {bands && (
            <p className="text-xs leading-5 text-[var(--text-muted)]">
              Counts fully within {bands[0]} m (solid ring), half at {bands[1]} m (dashed ring), then fades out.
            </p>
          )}
          <CoordinateFields
            latitude={form.latitude}
            longitude={form.longitude}
            onChange={(coords) => setForm((c) => ({ ...c, ...coords }))}
            onError={(message) => notify('error', message)}
          />
          <Field label="Note" hint="Optional, such as where this information came from">
            <input className={inputClass} value={form.note} onChange={(e) => setForm((c) => ({ ...c, note: e.target.value }))} />
          </Field>
          <div className="flex flex-wrap gap-2 border-t border-[var(--border-color)] pt-4">
            <button type="submit" className={buttonClass.primary} disabled={saving}>
              {saving ? 'Saving...' : editing ? 'Save changes' : 'Add anchor'}
            </button>
            <button type="button" className={buttonClass.secondary} onClick={closeForm} disabled={saving}>Cancel</button>
          </div>
        </form>
      </Card>
    </div>
  );

  const rowActions = (anchor) => {
    const busy = busyRef === refOf(anchor);
    if (anchor.status === 'duplicate') return null;
    return (
      <div className="-ml-3 flex flex-wrap gap-1">
        <button type="button" className={buttonClass.rowAction} onClick={() => startEdit(anchor)} disabled={busy}>Edit</button>
        <button type="button" className={buttonClass.rowAction} onClick={() => toggleHidden(anchor)} disabled={busy}>
          {anchor.status === 'hidden' ? 'Show' : 'Hide'}
        </button>
        {anchor.origin !== 'osm' && (
          <button type="button" className={buttonClass.rowDanger} onClick={() => remove(anchor)} disabled={busy}>Delete</button>
        )}
        {anchor.origin === 'osm' && anchor.id && (
          <button type="button" className={buttonClass.rowDanger} onClick={() => remove(anchor)} disabled={busy}>Undo changes</button>
        )}
      </div>
    );
  };

  const listCard = (
    <Card className={isDesktop ? 'flex min-h-0 min-w-0 flex-1 flex-col overflow-hidden' : 'min-w-0'}>
      <div className="flex flex-none flex-wrap items-center gap-3 border-b border-[var(--border-color)] px-4 py-3">
        <SearchField value={search} onChange={setSearch} placeholder="Search by name or category" label="Search anchors" />
        <select className={`${inputClass} w-auto`} value={filter} onChange={(e) => setFilter(e.target.value)} aria-label="Filter anchors">
          {FILTERS.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}
        </select>
        <p className="text-sm tabular-nums text-[var(--text-muted)]">{rows.length} of {anchors.length}</p>
      </div>

      {loading ? (
        <SkeletonRows />
      ) : rows.length === 0 ? (
        <EmptyState
          icon={MapPinIcon}
          title="No anchors match"
          description="Try a different name, category or filter."
          action={<button type="button" className={buttonClass.secondary} onClick={() => { setSearch(''); setFilter('all'); }}>Clear filters</button>}
        />
      ) : (
        <ul className={`divide-y divide-[var(--border-color)] ${isDesktop ? 'min-h-0 flex-1 overflow-y-auto' : ''}`}>
          {rows.map((anchor) => {
            const note = statusText(anchor);
            return (
              <li key={refOf(anchor)} className={`px-4 py-3 ${selectedRef === refOf(anchor) ? 'bg-[var(--accent-hover)]' : ''}`}>
                <button
                  type="button"
                  className="flex w-full cursor-pointer items-start gap-2.5 bg-transparent p-0 text-left"
                  onClick={() => setFocus({ lat: anchor.lat, lng: anchor.lon, at: Date.now() })}
                  title="Show on the map"
                >
                  <span
                    className="mt-1.5 h-2.5 w-2.5 flex-none rounded-full"
                    style={{ background: anchor.status === 'active' ? ANCHOR_SOURCE_COLORS[anchor.origin] : 'var(--border-strong)' }}
                    aria-hidden="true"
                  />
                  <span className="min-w-0">
                    <span className={`block font-medium ${anchor.status === 'active' ? 'text-[var(--text-main)]' : 'text-[var(--text-muted)]'}`}>{anchor.name}</span>
                    <span className="block text-sm text-[var(--text-muted)]">
                      {categories[anchor.category]?.label || anchor.category} · importance {anchor.power}
                    </span>
                    <span className="block text-xs text-[var(--text-muted)]">
                      {SOURCE_LABELS[anchor.origin]}{anchor.edited ? ', corrected' : ''}
                    </span>
                    {note && <span className="block text-xs text-[var(--text-muted)]">{note}</span>}
                  </span>
                </button>
                <div className="mt-1 pl-5">{rowActions(anchor)}</div>
              </li>
            );
          })}
        </ul>
      )}
    </Card>
  );

  const mapCard = (
    <Card className={isDesktop ? 'relative isolate h-full min-w-0 overflow-hidden' : 'relative isolate h-[340px] overflow-hidden'}>
      <AnchorsMap
        anchors={anchors}
        selectedRef={selectedRef}
        draft={draft}
        bands={bands}
        focus={focus}
        refOf={refOf}
        onMapClick={setCoords}
        onDraftMove={setCoords}
        onSelect={startEdit}
      />
      <div className="pointer-events-none absolute bottom-3 left-3 z-[500] flex flex-wrap gap-x-3 gap-y-1 rounded-lg border border-[var(--border-color)] bg-[var(--bg-sheet)] px-3 py-2 text-xs text-[var(--text-main)]">
        {Object.entries(SOURCE_LABELS).map(([key, label]) => (
          <span key={key} className="inline-flex items-center gap-1.5">
            <span className="h-2.5 w-2.5 rounded-full" style={{ background: ANCHOR_SOURCE_COLORS[key] }} aria-hidden="true" />
            {label}
          </span>
        ))}
      </div>
    </Card>
  );

  const header = (
    <PageHeader
      title="Anchors"
      description={`Places that bring people to an area, which raise the score of sites near them. ${counted} count in scans. Click the map to add one OpenStreetMap is missing.`}
      actions={(
        <>
          <DataBackupButtons token={token} dataset="anchors" label="Anchors" notify={notify} onImported={load} />
          {!isAddingOrEditing && (
            <button type="button" className={buttonClass.primary} onClick={() => setIsFormOpen(true)}>
              <MapPinIcon className="h-4 w-4" aria-hidden="true" /> Add anchor
            </button>
          )}
        </>
      )}
    />
  );

  if (isDesktop) {
    // Fill the admin main area exactly, as the MSMEs page does: the page never scrolls.
    return (
      <div className="flex h-[calc(100svh-4rem)] flex-col">
        {header}
        <div className="grid min-h-0 flex-1 grid-cols-[minmax(360px,420px)_minmax(0,1fr)] grid-rows-[minmax(0,1fr)] gap-6">
          <div className="flex min-h-0 min-w-0 flex-col gap-4 overflow-y-auto">
            {isAddingOrEditing && formCard}
            {listCard}
          </div>
          {mapCard}
        </div>
      </div>
    );
  }

  return (
    <>
      {header}
      <div className="space-y-4">
        {mapCard}
        {isAddingOrEditing && formCard}
        {listCard}
      </div>
    </>
  );
}
