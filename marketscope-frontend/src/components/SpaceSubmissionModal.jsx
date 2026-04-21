import React, { useMemo, useState } from 'react';
import { apiUrl } from '../api';

const BUSINESS_TYPE_OPTIONS = [
  { value: '', label: 'Not specific' },
  { value: 'coffee', label: 'Coffee Shops / Cafes' },
  { value: 'print', label: 'Print / Copy Centers' },
  { value: 'laundry', label: 'Laundry Shops' },
  { value: 'carwash', label: 'Car Washes' },
  { value: 'kiosk', label: 'Food Kiosks / Stalls' },
  { value: 'water', label: 'Water Refilling Stations' },
  { value: 'bakery', label: 'Bakeries' },
  { value: 'pharmacy', label: 'Small Pharmacies' },
  { value: 'barber', label: 'Barbershops / Salons' },
  { value: 'moto', label: 'Motorcycle Repair Shops' },
  { value: 'internet', label: 'Internet Cafes' },
  { value: 'meat', label: 'Meat Shops' },
  { value: 'hardware', label: 'Hardware / Construction Supplies' }
];

const defaultForm = {
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
  notes: ''
};

export default function SpaceSubmissionModal({ isOpen, onClose, userId }) {
  const [form, setForm] = useState(defaultForm);
  const [submitting, setSubmitting] = useState(false);
  const [errorMessage, setErrorMessage] = useState('');
  const [successMessage, setSuccessMessage] = useState('');

  const canSubmit = useMemo(() => {
    return form.title.trim() && form.latitude !== '' && form.longitude !== '';
  }, [form]);

  const handleFieldChange = (key, value) => {
    setForm((current) => ({ ...current, [key]: value }));
  };

  const handleSubmit = async () => {
    if (!userId) {
      setErrorMessage('User session is required to submit a space.');
      return;
    }

    const latitude = Number(form.latitude);
    const longitude = Number(form.longitude);
    if (!Number.isFinite(latitude) || !Number.isFinite(longitude)) {
      setErrorMessage('Latitude and longitude must be valid numbers.');
      return;
    }

    setSubmitting(true);
    setErrorMessage('');
    setSuccessMessage('');

    try {
      const response = await fetch(apiUrl('/spaces/user-submissions'), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          user_id: userId,
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
          notes: form.notes.trim() || null
        })
      });

      const data = await response.json();
      if (!response.ok) {
        throw new Error(data?.detail || 'Unable to submit space listing.');
      }

      setSuccessMessage('Submission sent. Admin can now review it.');
      setForm(defaultForm);
    } catch (error) {
      setErrorMessage(error.message || 'Unable to submit space listing.');
    } finally {
      setSubmitting(false);
    }
  };

  if (!isOpen) return null;

  return (
    <div className="sheet-overlay" onClick={onClose} role="presentation">
      <div className="bottom-sheet" onClick={(event) => event.stopPropagation()} role="dialog" aria-modal="true" aria-label="Submit a space listing">
        <div className="drag-handle"></div>
        <button className="close-btn" onClick={onClose}>
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><line x1="18" y1="6" x2="6" y2="18"></line><line x1="6" y1="6" x2="18" y2="18"></line></svg>
        </button>

        <div className="sheet-content">
          <h2 className="sheet-title">Submit Space Listing</h2>
          <p className="sheet-subtitle">Send a guaranteed listing to admin review for map publishing.</p>

          {errorMessage && <div className="error-alert mt-3">{errorMessage}</div>}
          {successMessage && <div className="admin-success-alert mt-3">{successMessage}</div>}

          <div className="input-group">
            <label className="input-label">Listing Title</label>
            <input className="history-search-input" value={form.title} onChange={(event) => handleFieldChange('title', event.target.value)} placeholder="Example: Corner stall near market" />
          </div>

          <div className="input-group">
            <label className="input-label">Listing Mode</label>
            <select className="app-select" value={form.listing_mode} onChange={(event) => handleFieldChange('listing_mode', event.target.value)}>
              <option value="rent">For Rent</option>
              <option value="buy">For Buy</option>
            </select>
          </div>

          <div className="input-group">
            <label className="input-label">Property Type</label>
            <input className="history-search-input" value={form.property_type} onChange={(event) => handleFieldChange('property_type', event.target.value)} placeholder="Example: Storefront, Kiosk, Lot" />
          </div>

          <div className="input-group">
            <label className="input-label">Business Type (Optional)</label>
            <select className="app-select" value={form.business_type} onChange={(event) => handleFieldChange('business_type', event.target.value)}>
              {BUSINESS_TYPE_OPTIONS.map((option) => (
                <option key={option.value || 'none'} value={option.value}>{option.label}</option>
              ))}
            </select>
          </div>

          <div className="history-tools-grid" style={{ marginBottom: 12 }}>
            <div className="input-group" style={{ marginBottom: 0 }}>
              <label className="input-label">Latitude</label>
              <input className="history-search-input" value={form.latitude} onChange={(event) => handleFieldChange('latitude', event.target.value)} placeholder="7.30750" />
            </div>
            <div className="input-group" style={{ marginBottom: 0 }}>
              <label className="input-label">Longitude</label>
              <input className="history-search-input" value={form.longitude} onChange={(event) => handleFieldChange('longitude', event.target.value)} placeholder="125.68110" />
            </div>
          </div>

          <div className="input-group">
            <label className="input-label">Address</label>
            <input className="history-search-input" value={form.address_text} onChange={(event) => handleFieldChange('address_text', event.target.value)} placeholder="Street and landmark" />
          </div>

          <div className="history-tools-grid" style={{ marginBottom: 12 }}>
            <div className="input-group" style={{ marginBottom: 0 }}>
              <label className="input-label">Min Price (PHP)</label>
              <input className="history-search-input" value={form.price_min} onChange={(event) => handleFieldChange('price_min', event.target.value)} placeholder="5000" />
            </div>
            <div className="input-group" style={{ marginBottom: 0 }}>
              <label className="input-label">Max Price (PHP)</label>
              <input className="history-search-input" value={form.price_max} onChange={(event) => handleFieldChange('price_max', event.target.value)} placeholder="10000" />
            </div>
          </div>

          <div className="input-group">
            <label className="input-label">Contact Info</label>
            <input className="history-search-input" value={form.contact_info} onChange={(event) => handleFieldChange('contact_info', event.target.value)} placeholder="Phone or Facebook page" />
          </div>

          <div className="input-group">
            <label className="input-label">Notes</label>
            <textarea className="history-search-input" rows={3} value={form.notes} onChange={(event) => handleFieldChange('notes', event.target.value)} placeholder="Extra details for admin review" />
          </div>

          <button type="button" className="primary-btn mt-4" disabled={!canSubmit || submitting} onClick={handleSubmit}>
            {submitting ? 'Submitting...' : 'Submit to Admin'}
          </button>
        </div>
      </div>
    </div>
  );
}
