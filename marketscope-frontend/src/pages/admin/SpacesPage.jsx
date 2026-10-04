import React, { useCallback, useEffect, useState } from 'react';
import { ArrowPathIcon, HomeModernIcon, InboxIcon, PhotoIcon, XMarkIcon } from '@heroicons/react/24/outline';
import { BUSINESS_TYPE_OPTIONS, getBusinessTypeLabel } from '../../utils/businessTypes';
import CoordinateFields from '../../components/admin/ui/CoordinateFields';
import {
  Card,
  CardHeader,
  DataTable,
  Detail,
  EmptyState,
  Field,
  PageHeader,
  SegmentedTabs,
  SkeletonRows,
  StatusBadge
} from '../../components/admin/ui/AdminUi';
import { buttonClass, inputClass } from '../../components/admin/ui/adminStyles';

const STATUS_FILTERS = [
  { id: 'pending', label: 'Pending' },
  { id: 'approved', label: 'Approved' },
  { id: 'rejected', label: 'Rejected' },
  { id: 'archived', label: 'Archived' },
  { id: 'all', label: 'All' }
];

const EMPTY_FORM = {
  title: '',
  listing_mode: 'rent',
  property_type: '',
  business_type: '',
  latitude: '',
  longitude: '',
  address_text: '',
  price_min: '',
  price_max: '',
  contact_info: '',
  notes: '',
  photo_urls: []
};

const MAX_PHOTOS = 4;

const listingModeLabel = (value) => (String(value || '').toLowerCase() === 'buy' ? 'For sale' : 'For rent');

const formatPrice = (min, max) => {
  const low = Number(min || 0);
  const high = Number(max || 0);
  if (low > 0 && high > 0) return `PHP ${low.toLocaleString()} - ${high.toLocaleString()}`;
  if (low > 0) return `From PHP ${low.toLocaleString()}`;
  if (high > 0) return `Up to PHP ${high.toLocaleString()}`;
  return 'Not set';
};

const formatCoords = (item) => `${Number(item.latitude).toFixed(5)}, ${Number(item.longitude).toFixed(5)}`;

const formatDate = (value) => {
  if (!value) return null;
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? null : date.toLocaleDateString(undefined, { year: 'numeric', month: 'short', day: 'numeric' });
};

const readFileAsDataUrl = (file) => new Promise((resolve, reject) => {
  const reader = new FileReader();
  reader.onload = () => resolve(String(reader.result || ''));
  reader.onerror = () => reject(new Error(`Could not read ${file.name}.`));
  reader.readAsDataURL(file);
});

// Which review actions make sense for a submission in each status.
const REVIEW_ACTIONS = {
  pending: [
    { status: 'approved', label: 'Approve', style: 'primary' },
    { status: 'rejected', label: 'Reject', style: 'secondary' },
    { status: 'archived', label: 'Archive', style: 'danger' }
  ],
  approved: [
    { status: 'rejected', label: 'Move to rejected', style: 'secondary' },
    { status: 'archived', label: 'Archive', style: 'danger' }
  ],
  rejected: [
    { status: 'approved', label: 'Approve', style: 'secondary' },
    { status: 'archived', label: 'Archive', style: 'danger' }
  ],
  archived: [{ status: 'approved', label: 'Restore as approved', style: 'secondary' }]
};

function SubmissionCard({ item, busy, onReview }) {
  const status = String(item.status || 'pending').toLowerCase();
  const photos = Array.isArray(item.photo_urls) ? item.photo_urls : [];
  const submittedOn = formatDate(item.created_at);

  return (
    <Card className="flex min-w-0 flex-col">
      <div className="flex-1 p-5">
        <div className="flex items-start justify-between gap-3">
          <div className="min-w-0">
            <h3 className="font-semibold text-[var(--text-main)]">{item.title}</h3>
            {submittedOn && <p className="mt-0.5 text-xs text-[var(--text-muted)]">Submitted {submittedOn}</p>}
          </div>
          <StatusBadge status={status} />
        </div>

        {photos.length > 0 && (
          <div className="mt-4 flex gap-2 overflow-x-auto pb-1">
            {photos.map((photoUrl, index) => (
              <img
                key={index}
                src={photoUrl}
                alt={`${item.title}, photo ${index + 1}`}
                loading="lazy"
                className="h-20 w-28 flex-none rounded-lg border border-[var(--border-color)] object-cover"
              />
            ))}
          </div>
        )}

        <dl className="mt-4 grid grid-cols-2 gap-3">
          <Detail label="Listing">{listingModeLabel(item.listing_mode)}</Detail>
          <Detail label="Business type">{item.business_type ? getBusinessTypeLabel(item.business_type) : 'Any'}</Detail>
          <Detail label="Price">{formatPrice(item.price_min, item.price_max)}</Detail>
          <Detail label="Coordinates"><span className="tabular-nums">{formatCoords(item)}</span></Detail>
          {item.address_text && <div className="col-span-2"><Detail label="Address">{item.address_text}</Detail></div>}
          {item.contact_info && <div className="col-span-2"><Detail label="Contact">{item.contact_info}</Detail></div>}
          {item.notes && <div className="col-span-2"><Detail label="Notes">{item.notes}</Detail></div>}
        </dl>
      </div>

      <div className="flex flex-wrap gap-2 border-t border-[var(--border-color)] px-5 py-3">
        {(REVIEW_ACTIONS[status] || []).map((action) => (
          <button
            key={action.status}
            type="button"
            className={buttonClass[action.style]}
            disabled={busy}
            onClick={() => onReview(item, action.status)}
          >
            {action.label}
          </button>
        ))}
      </div>
    </Card>
  );
}

// Commercial spaces: review what users submit, add verified listings, and
// switch admin listings on or off. What appears on the map / in trend scans comes
// from services/spaces.py (pending + approved user spaces, active admin listings).
export default function SpacesPage({ api, notify, isDesktop, pendingCount, onPendingChanged }) {
  const [view, setView] = useState('review');
  const [statusFilter, setStatusFilter] = useState('pending');
  const [submissions, setSubmissions] = useState([]);
  const [submissionsLoading, setSubmissionsLoading] = useState(true);
  const [listings, setListings] = useState([]);
  const [listingsLoading, setListingsLoading] = useState(true);
  const [busyId, setBusyId] = useState(null);
  const [form, setForm] = useState(EMPTY_FORM);
  const [saving, setSaving] = useState(false);

  const loadSubmissions = useCallback(async () => {
    setSubmissionsLoading(true);
    try {
      const query = statusFilter === 'all' ? '' : `?status=${statusFilter}`;
      const data = await api(`/admin/spaces/user-submissions${query}`);
      setSubmissions(Array.isArray(data?.submissions) ? data.submissions : []);
    } catch (error) {
      notify('error', error.message);
    } finally {
      setSubmissionsLoading(false);
    }
  }, [api, notify, statusFilter]);

  const loadListings = useCallback(async () => {
    setListingsLoading(true);
    try {
      const data = await api('/admin/spaces/admin-submissions');
      setListings(Array.isArray(data?.submissions) ? data.submissions : []);
    } catch (error) {
      notify('error', error.message);
    } finally {
      setListingsLoading(false);
    }
  }, [api, notify]);

  useEffect(() => {
    loadSubmissions();
  }, [loadSubmissions]);

  useEffect(() => {
    loadListings();
  }, [loadListings]);

  const review = async (item, status) => {
    setBusyId(`user-${item.id}`);
    try {
      await api(`/admin/spaces/user-submissions/${item.id}/status`, { method: 'PUT', body: { status } });
      notify('success', `"${item.title}" is now ${status}.`);
      await loadSubmissions();
      onPendingChanged?.();
    } catch (error) {
      notify('error', error.message);
    } finally {
      setBusyId(null);
    }
  };

  const toggleListing = async (item) => {
    const nextActive = !item.is_active;
    setBusyId(`admin-${item.id}`);
    try {
      await api(`/admin/spaces/admin-submissions/${item.id}/active`, { method: 'PUT', body: { is_active: nextActive } });
      notify('success', `"${item.title}" is now ${nextActive ? 'active' : 'inactive'}.`);
      await loadListings();
    } catch (error) {
      notify('error', error.message);
    } finally {
      setBusyId(null);
    }
  };

  const addPhotos = async (event) => {
    const files = Array.from(event.target.files || []);
    event.target.value = '';
    const room = MAX_PHOTOS - form.photo_urls.length;
    if (!files.length || room <= 0) return;
    try {
      const encoded = await Promise.all(files.slice(0, room).map(readFileAsDataUrl));
      setForm((current) => ({ ...current, photo_urls: [...current.photo_urls, ...encoded].slice(0, MAX_PHOTOS) }));
    } catch (error) {
      notify('error', error.message);
    }
  };

  const submitListing = async (event) => {
    event.preventDefault();
    const latitude = Number(form.latitude);
    const longitude = Number(form.longitude);
    if (!form.title.trim() || !form.latitude || !form.longitude || Number.isNaN(latitude) || Number.isNaN(longitude)) {
      notify('error', 'A title and a valid latitude and longitude are required.');
      return;
    }

    setSaving(true);
    try {
      await api('/admin/spaces/admin-submissions', {
        method: 'POST',
        body: {
          title: form.title.trim(),
          listing_mode: form.listing_mode,
          property_type: form.property_type.trim() || null,
          business_type: form.business_type || null,
          latitude,
          longitude,
          address_text: form.address_text.trim() || null,
          price_min: form.price_min === '' ? null : Number(form.price_min),
          price_max: form.price_max === '' ? null : Number(form.price_max),
          contact_info: form.contact_info.trim() || null,
          notes: form.notes.trim() || null,
          photo_urls: form.photo_urls
        }
      });
      notify('success', `"${form.title.trim()}" was added to the admin listings.`);
      setForm(EMPTY_FORM);
      await loadListings();
      setView('listings');
    } catch (error) {
      notify('error', error.message);
    } finally {
      setSaving(false);
    }
  };

  const setField = (field) => (event) => setForm((current) => ({ ...current, [field]: event.target.value }));

  const reviewView = (
    <>
      <div className="mb-4 flex flex-wrap items-center gap-2">
        <div className="flex flex-wrap gap-2" role="group" aria-label="Filter by status">
          {STATUS_FILTERS.map((filter) => (
            <button
              key={filter.id}
              type="button"
              aria-pressed={statusFilter === filter.id}
              onClick={() => setStatusFilter(filter.id)}
              className={`inline-flex min-h-[36px] cursor-pointer items-center rounded-full border px-3.5 text-sm font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--focus-ring)] ${statusFilter === filter.id ? 'border-[var(--accent)] bg-[var(--accent-hover)] text-[var(--accent)]' : 'border-[var(--border-color)] text-[var(--text-muted)] hover:text-[var(--text-main)]'}`}
            >
              {filter.label}
            </button>
          ))}
        </div>
        <button type="button" className={`${buttonClass.ghost} ml-auto`} onClick={loadSubmissions} disabled={submissionsLoading}>
          <ArrowPathIcon className={`h-4 w-4 ${submissionsLoading ? 'animate-spin' : ''}`} aria-hidden="true" /> Reload
        </button>
      </div>

      {submissionsLoading ? (
        <Card><SkeletonRows count={3} /></Card>
      ) : submissions.length === 0 ? (
        <Card>
          <EmptyState
            icon={InboxIcon}
            title={statusFilter === 'pending' ? 'Nothing to review' : `No ${statusFilter === 'all' ? '' : statusFilter} submissions`}
            description={statusFilter === 'pending' ? 'New spaces submitted by users will show up here.' : 'Try another status filter.'}
          />
        </Card>
      ) : (
        <div className="grid gap-4 lg:grid-cols-2">
          {submissions.map((item) => (
            <SubmissionCard key={item.id} item={item} busy={busyId === `user-${item.id}`} onReview={review} />
          ))}
        </div>
      )}
    </>
  );

  const addView = (
    <Card className="max-w-4xl">
      <CardHeader title="Add a verified space" description="Admin listings go straight onto the map and into Business Trends scans." />
      <form onSubmit={submitListing} className="grid gap-4 p-5 md:grid-cols-2">
        <Field label="Title" required className="md:col-span-2">
          <input className={inputClass} value={form.title} onChange={setField('title')} placeholder="e.g. Corner lot near Panabo Public Market" required />
        </Field>
        <Field label="Listing type">
          <select className={inputClass} value={form.listing_mode} onChange={setField('listing_mode')}>
            <option value="rent">For rent</option>
            <option value="buy">For sale</option>
          </select>
        </Field>
        <Field label="Best for business type">
          <select className={inputClass} value={form.business_type} onChange={setField('business_type')}>
            <option value="">Any business</option>
            {BUSINESS_TYPE_OPTIONS.map((option) => (
              <option key={option.value} value={option.value}>{option.label}</option>
            ))}
          </select>
        </Field>
        <div className="md:col-span-2">
          <CoordinateFields
            latitude={form.latitude}
            longitude={form.longitude}
            onChange={(coords) => setForm((current) => ({ ...current, ...coords }))}
            onError={(message) => notify('error', message)}
          />
        </div>
        <Field label="Property type">
          <input className={inputClass} value={form.property_type} onChange={setField('property_type')} placeholder="Storefront, lot, stall..." />
        </Field>
        <Field label="Address">
          <input className={inputClass} value={form.address_text} onChange={setField('address_text')} placeholder="Street, barangay or landmark" />
        </Field>
        <Field label="Minimum price (PHP)">
          <input className={`${inputClass} tabular-nums`} type="number" min="0" inputMode="numeric" value={form.price_min} onChange={setField('price_min')} />
        </Field>
        <Field label="Maximum price (PHP)">
          <input className={`${inputClass} tabular-nums`} type="number" min="0" inputMode="numeric" value={form.price_max} onChange={setField('price_max')} />
        </Field>
        <Field label="Contact info" className="md:col-span-2">
          <input className={inputClass} value={form.contact_info} onChange={setField('contact_info')} placeholder="Name and phone number of the owner or agent" />
        </Field>
        <Field label="Notes" className="md:col-span-2">
          <textarea className={`${inputClass} min-h-[96px] py-2.5`} rows={3} value={form.notes} onChange={setField('notes')} />
        </Field>

        <div className="md:col-span-2">
          <p className="mb-1.5 text-sm font-medium text-[var(--text-main)]">Photos</p>
          <div className="flex flex-wrap gap-3">
            {form.photo_urls.map((photoUrl, index) => (
              <div key={index} className="relative">
                <img src={photoUrl} alt={`New listing photo ${index + 1}`} className="h-24 w-32 rounded-xl border border-[var(--border-color)] object-cover" />
                <button
                  type="button"
                  onClick={() => setForm((current) => ({ ...current, photo_urls: current.photo_urls.filter((_, i) => i !== index) }))}
                  className="absolute -right-2 -top-2 inline-flex h-7 w-7 cursor-pointer items-center justify-center rounded-full border border-[var(--border-color)] bg-[var(--bg-sheet)] text-[var(--text-main)] shadow-sm hover:bg-[var(--trend-down-bg)] hover:text-[var(--trend-down)]"
                  aria-label={`Remove photo ${index + 1}`}
                >
                  <XMarkIcon className="h-4 w-4" aria-hidden="true" />
                </button>
              </div>
            ))}
            {form.photo_urls.length < MAX_PHOTOS && (
              <label className="flex h-24 w-32 cursor-pointer flex-col items-center justify-center gap-1 rounded-xl border border-dashed border-[var(--border-strong)] text-xs font-medium text-[var(--text-muted)] transition-colors hover:border-[var(--accent)] hover:text-[var(--accent)] focus-within:ring-2 focus-within:ring-[var(--focus-ring)]">
                <PhotoIcon className="h-6 w-6" aria-hidden="true" />
                Add photos
                <input type="file" accept="image/*" multiple onChange={addPhotos} className="sr-only" />
              </label>
            )}
          </div>
          <p className="mt-1.5 text-xs text-[var(--text-muted)]">Up to {MAX_PHOTOS} photos.</p>
        </div>

        <div className="flex flex-wrap justify-end gap-2 border-t border-[var(--border-color)] pt-4 md:col-span-2">
          <button type="button" className={buttonClass.secondary} onClick={() => setForm(EMPTY_FORM)} disabled={saving}>Clear form</button>
          <button type="submit" className={buttonClass.primary} disabled={saving}>{saving ? 'Saving...' : 'Add listing'}</button>
        </div>
      </form>
    </Card>
  );

  const listingStatus = (item) => (
    <div>
      <StatusBadge status={item.is_active ? 'active' : 'inactive'} />
      {formatDate(item.expires_at) && <p className="mt-1 text-xs text-[var(--text-muted)]">Expires {formatDate(item.expires_at)}</p>}
    </div>
  );

  const listingToggle = (item) => (
    <button
      type="button"
      className={item.is_active ? buttonClass.rowDanger : buttonClass.rowAction}
      onClick={() => toggleListing(item)}
      disabled={busyId === `admin-${item.id}`}
    >
      {busyId === `admin-${item.id}` ? 'Saving...' : item.is_active ? 'Deactivate' : 'Activate'}
    </button>
  );

  const listingsView = (
    <Card className="min-w-0">
      {listingsLoading ? (
        <SkeletonRows />
      ) : listings.length === 0 ? (
        <EmptyState
          icon={HomeModernIcon}
          title="No admin listings yet"
          description="Spaces you add yourself are listed here."
          action={<button type="button" className={buttonClass.primary} onClick={() => setView('add')}>Add a space</button>}
        />
      ) : isDesktop ? (
        <DataTable
          caption="Admin space listings"
          rows={listings}
          rowKey={(item) => item.id}
          columns={[
            {
              key: 'title',
              header: 'Title',
              render: (item) => (
                <div className="min-w-0">
                  <p className="font-medium text-[var(--text-main)]">{item.title}</p>
                  {item.property_type && <p className="text-xs text-[var(--text-muted)]">{item.property_type}</p>}
                </div>
              )
            },
            { key: 'mode', header: 'Listing', className: 'whitespace-nowrap', render: (item) => listingModeLabel(item.listing_mode) },
            { key: 'business', header: 'Business type', render: (item) => (item.business_type ? getBusinessTypeLabel(item.business_type) : 'Any') },
            { key: 'price', header: 'Price', className: 'tabular-nums', render: (item) => formatPrice(item.price_min, item.price_max) },
            { key: 'coords', header: 'Coordinates', className: 'tabular-nums whitespace-nowrap', render: formatCoords },
            { key: 'status', header: 'Status', render: listingStatus },
            { key: 'actions', header: <span className="sr-only">Actions</span>, className: 'text-right', render: listingToggle }
          ]}
        />
      ) : (
        <ul className="divide-y divide-[var(--border-color)]">
          {listings.map((item) => (
            <li key={item.id} className="px-4 py-4">
              <div className="flex items-start justify-between gap-3">
                <p className="min-w-0 font-medium text-[var(--text-main)]">{item.title}</p>
                <StatusBadge status={item.is_active ? 'active' : 'inactive'} />
              </div>
              <dl className="mt-3 grid grid-cols-2 gap-3">
                <Detail label="Listing">{listingModeLabel(item.listing_mode)}</Detail>
                <Detail label="Price">{formatPrice(item.price_min, item.price_max)}</Detail>
                <Detail label="Business type">{item.business_type ? getBusinessTypeLabel(item.business_type) : 'Any'}</Detail>
                <Detail label="Coordinates"><span className="tabular-nums">{formatCoords(item)}</span></Detail>
              </dl>
              <div className="mt-2 -ml-3">{listingToggle(item)}</div>
            </li>
          ))}
        </ul>
      )}
    </Card>
  );

  return (
    <>
      <PageHeader title="Spaces" description="Commercial spaces for rent or sale. Pending and approved user spaces, plus active admin listings, appear on the map and in Business Trends scans. Reject or archive a space to take it off." />
      <div className="mb-5">
        <SegmentedTabs
          ariaLabel="Spaces views"
          value={view}
          onChange={setView}
          tabs={[
            { id: 'review', label: 'Review queue', count: pendingCount },
            { id: 'add', label: 'Add space' },
            { id: 'listings', label: 'Admin listings' }
          ]}
        />
      </div>
      {view === 'review' && reviewView}
      {view === 'add' && addView}
      {view === 'listings' && listingsView}
    </>
  );
}
