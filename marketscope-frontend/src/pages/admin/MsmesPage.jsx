import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { BuildingStorefrontIcon, PlusIcon } from '@heroicons/react/24/outline';
import { BUSINESS_TYPE_OPTIONS, getBusinessTypeLabel } from '../../utils/businessTypes';
import CoordinateFields from '../../components/admin/ui/CoordinateFields';
import {
  Card,
  CardHeader,
  DataTable,
  EmptyState,
  Field,
  PageHeader,
  SearchField,
  SkeletonRows
} from '../../components/admin/ui/AdminUi';
import { buttonClass, inputClass } from '../../components/admin/ui/adminStyles';

const EMPTY_FORM = { name: '', business_type: '', latitude: '', longitude: '' };

const SORTERS = {
  'type-asc': (a, b) => a.typeLabel.localeCompare(b.typeLabel) || a.name.localeCompare(b.name),
  'type-desc': (a, b) => b.typeLabel.localeCompare(a.typeLabel) || a.name.localeCompare(b.name),
  'name-asc': (a, b) => a.name.localeCompare(b.name),
  'name-desc': (a, b) => b.name.localeCompare(a.name)
};

const formatCoords = (item) => `${Number(item.latitude).toFixed(5)}, ${Number(item.longitude).toFixed(5)}`;

// Custom MSMEs: businesses the admin adds by hand. Every scan counts them as
// competitors for their business type, next to the OpenStreetMap data.
export default function MsmesPage({ api, notify, isDesktop }) {
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState('');
  const [sortBy, setSortBy] = useState('type-asc');
  const [form, setForm] = useState(EMPTY_FORM);
  const [editingId, setEditingId] = useState(null);
  const [saving, setSaving] = useState(false);
  const [busyId, setBusyId] = useState(null);
  const [showMobileForm, setShowMobileForm] = useState(false);
  const formRef = useRef(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const data = await api('/admin/custom-msmes');
      setItems(Array.isArray(data?.custom_msmes) ? data.custom_msmes : []);
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
    return items
      .map((item) => ({ ...item, name: String(item.name || ''), typeLabel: getBusinessTypeLabel(item.business_type) }))
      .filter((item) => !query || item.name.toLowerCase().includes(query) || item.typeLabel.toLowerCase().includes(query))
      .sort(SORTERS[sortBy]);
  }, [items, search, sortBy]);

  const resetForm = () => {
    setForm(EMPTY_FORM);
    setEditingId(null);
    setShowMobileForm(false);
  };

  const submit = async (event) => {
    event.preventDefault();
    const payload = {
      name: form.name.trim(),
      business_type: form.business_type,
      latitude: Number(form.latitude),
      longitude: Number(form.longitude)
    };
    if (!payload.name || !payload.business_type || !form.latitude || !form.longitude || Number.isNaN(payload.latitude) || Number.isNaN(payload.longitude)) {
      notify('error', 'Fill in the name, business type and a valid latitude and longitude.');
      return;
    }

    setSaving(true);
    try {
      if (editingId) {
        await api(`/admin/custom-msmes/${editingId}`, { method: 'PUT', body: payload });
        notify('success', `"${payload.name}" was updated.`);
      } else {
        await api('/admin/custom-msmes', { method: 'POST', body: payload });
        notify('success', `"${payload.name}" was added.`);
      }
      resetForm();
      await load();
    } catch (error) {
      notify('error', error.message);
    } finally {
      setSaving(false);
    }
  };

  const startEdit = (item) => {
    setEditingId(item.id);
    setForm({
      name: item.name || '',
      business_type: item.business_type || '',
      latitude: String(item.latitude ?? ''),
      longitude: String(item.longitude ?? '')
    });
    setShowMobileForm(true);
    requestAnimationFrame(() => formRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' }));
  };

  const remove = async (item) => {
    if (!window.confirm(`Delete "${item.name}"? It will stop counting as a competitor in scans.`)) return;
    setBusyId(item.id);
    try {
      await api(`/admin/custom-msmes/${item.id}`, { method: 'DELETE' });
      notify('success', `"${item.name}" was deleted.`);
      if (editingId === item.id) resetForm();
      await load();
    } catch (error) {
      notify('error', error.message);
    } finally {
      setBusyId(null);
    }
  };

  const formCard = (
    <div ref={formRef} className={isDesktop ? 'sticky top-0' : ''}>
      <Card>
        <CardHeader
          title={editingId ? 'Edit MSME' : 'Add an MSME'}
          description={editingId ? 'Changes apply to the next scans.' : 'It will count as a competitor for its business type.'}
        />
        <form onSubmit={submit} className="space-y-4 p-5">
          <Field label="Business name" required>
            <input className={inputClass} value={form.name} onChange={(e) => setForm((c) => ({ ...c, name: e.target.value }))} placeholder="e.g. Kape Panabo" required />
          </Field>
          <Field label="Business type" required>
            <select className={inputClass} value={form.business_type} onChange={(e) => setForm((c) => ({ ...c, business_type: e.target.value }))} required>
              <option value="">Choose a business type...</option>
              {BUSINESS_TYPE_OPTIONS.map((option) => (
                <option key={option.value} value={option.value}>{option.label}</option>
              ))}
            </select>
          </Field>
          <CoordinateFields
            latitude={form.latitude}
            longitude={form.longitude}
            onChange={(coords) => setForm((c) => ({ ...c, ...coords }))}
            onError={(message) => notify('error', message)}
          />
          <div className="flex flex-wrap gap-2 border-t border-[var(--border-color)] pt-4">
            <button type="submit" className={buttonClass.primary} disabled={saving}>
              {saving ? 'Saving...' : editingId ? 'Save changes' : 'Add MSME'}
            </button>
            {(editingId || !isDesktop) && (
              <button type="button" className={buttonClass.secondary} onClick={resetForm} disabled={saving}>Cancel</button>
            )}
          </div>
        </form>
      </Card>
    </div>
  );

  const rowActions = (item, align = 'end') => (
    <div className={`flex gap-1 ${align === 'end' ? 'justify-end' : '-ml-3'}`}>
      <button type="button" className={buttonClass.rowAction} onClick={() => startEdit(item)} disabled={busyId === item.id}>Edit</button>
      <button type="button" className={buttonClass.rowDanger} onClick={() => remove(item)} disabled={busyId === item.id}>
        {busyId === item.id ? 'Deleting...' : 'Delete'}
      </button>
    </div>
  );

  const listCard = (
    <Card className="min-w-0">
      <div className="flex flex-wrap items-center gap-3 border-b border-[var(--border-color)] px-5 py-4">
        <SearchField value={search} onChange={setSearch} placeholder="Search by name or business type" label="Search MSMEs" />
        <select className={`${inputClass} w-auto`} value={sortBy} onChange={(e) => setSortBy(e.target.value)} aria-label="Sort MSMEs">
          <option value="type-asc">Business type (A-Z)</option>
          <option value="type-desc">Business type (Z-A)</option>
          <option value="name-asc">Name (A-Z)</option>
          <option value="name-desc">Name (Z-A)</option>
        </select>
        <p className="text-sm tabular-nums text-[var(--text-muted)]">{rows.length} of {items.length}</p>
      </div>

      {loading ? (
        <SkeletonRows />
      ) : rows.length === 0 ? (
        <EmptyState
          icon={BuildingStorefrontIcon}
          title={items.length === 0 ? 'No MSMEs added yet' : 'No MSMEs match your search'}
          description={items.length === 0 ? 'Add a business that is missing from OpenStreetMap so scans count it as a competitor.' : 'Try a different name or business type.'}
          action={items.length > 0 && <button type="button" className={buttonClass.secondary} onClick={() => setSearch('')}>Clear search</button>}
        />
      ) : isDesktop ? (
        <DataTable
          caption="Custom MSMEs"
          rows={rows}
          rowKey={(item) => item.id}
          isRowHighlighted={(item) => item.id === editingId}
          columns={[
            { key: 'name', header: 'Name', render: (item) => <span className="font-medium text-[var(--text-main)]">{item.name}</span> },
            { key: 'type', header: 'Business type', render: (item) => item.typeLabel },
            { key: 'coords', header: 'Coordinates', className: 'tabular-nums', render: formatCoords },
            { key: 'actions', header: <span className="sr-only">Actions</span>, className: 'text-right', render: rowActions }
          ]}
        />
      ) : (
        <ul className="divide-y divide-[var(--border-color)]">
          {rows.map((item) => (
            <li key={item.id} className={`px-4 py-4 ${item.id === editingId ? 'bg-[var(--accent-hover)]' : ''}`}>
              <p className="font-medium text-[var(--text-main)]">{item.name}</p>
              <p className="mt-0.5 text-sm text-[var(--text-muted)]">{item.typeLabel}</p>
              <p className="mt-0.5 text-sm tabular-nums text-[var(--text-muted)]">{formatCoords(item)}</p>
              <div className="mt-2">{rowActions(item, 'start')}</div>
            </li>
          ))}
        </ul>
      )}
    </Card>
  );

  return (
    <>
      <PageHeader
        title="MSMEs"
        description="Businesses added here count as competitors in every scan, alongside OpenStreetMap data."
        actions={!isDesktop && !showMobileForm && (
          <button type="button" className={buttonClass.primary} onClick={() => setShowMobileForm(true)}>
            <PlusIcon className="h-4 w-4" aria-hidden="true" /> Add MSME
          </button>
        )}
      />
      {isDesktop ? (
        <div className="grid grid-cols-[minmax(320px,380px)_minmax(0,1fr)] items-start gap-6">
          {formCard}
          {listCard}
        </div>
      ) : (
        <div className="space-y-4">
          {showMobileForm && formCard}
          {listCard}
        </div>
      )}
    </>
  );
}
