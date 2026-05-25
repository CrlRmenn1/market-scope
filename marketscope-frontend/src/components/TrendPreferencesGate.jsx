import React, { useMemo, useState } from 'react';
import { apiUrl } from '../api';

const REQUIRED_FIELDS = [
  'primary_business',
  'startup_capital',
  'risk_tolerance',
  'preferred_setup',
  'time_commitment',
  'target_payback_months'
];

const BUSINESS_OPTIONS = [
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

const FIELD_LABELS = {
  primary_business: 'Primary Business Interest',
  startup_capital: 'Startup Capital (PHP)',
  risk_tolerance: 'Risk Tolerance',
  preferred_setup: 'Preferred Setup',
  time_commitment: 'Time Commitment',
  target_payback_months: 'Target Payback (Months)'
};

const normalizeField = (value) => {
  if (value === null || value === undefined) return null;
  if (typeof value === 'string') {
    const trimmed = value.trim();
    return trimmed ? trimmed : null;
  }
  return value;
};

const getMissingFields = (profile) => REQUIRED_FIELDS.filter((field) => normalizeField(profile?.[field]) === null);

export default function TrendPreferencesGate({ user, missingFields, onSaved, onLater }) {
  const userId = user?.user_id || user?.id;
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');
  const [step, setStep] = useState('intro');
  const [formValues, setFormValues] = useState({
    full_name: user?.full_name || user?.name || '',
    email: user?.email || '',
    address: user?.address || '',
    cellphone_number: user?.cellphone_number || '',
    avatar_url: user?.avatar_url || '',
    age: user?.age ?? '',
    birthday: user?.birthday ? String(user.birthday).slice(0, 10) : '',
    primary_business: user?.primary_business || '',
    startup_capital: user?.startup_capital ?? '',
    risk_tolerance: user?.risk_tolerance || '',
    preferred_setup: user?.preferred_setup || '',
    time_commitment: user?.time_commitment || '',
    target_payback_months: user?.target_payback_months ?? ''
  });

  const effectiveMissingFields = useMemo(() => {
    if (Array.isArray(missingFields) && missingFields.length > 0) {
      return missingFields;
    }
    return getMissingFields(formValues);
  }, [formValues, missingFields]);

  if (!userId) return null;

  const updateField = (field, value) => {
    setFormValues((current) => ({ ...current, [field]: value }));
  };

  const handleSave = async (event) => {
    event.preventDefault();
    setError('');

    const pendingMissing = getMissingFields(formValues);
    if (pendingMissing.length > 0) {
      setError(`Please complete: ${pendingMissing.map((field) => FIELD_LABELS[field] || field).join(', ')}`);
      return;
    }

    setSaving(true);
    try {
      const response = await fetch(apiUrl(`/users/${userId}`), {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          ...formValues,
          age: formValues.age === '' ? null : Number(formValues.age),
          startup_capital: formValues.startup_capital === '' ? null : Number(formValues.startup_capital),
          target_payback_months: formValues.target_payback_months === '' ? null : Number(formValues.target_payback_months),
          birthday: formValues.birthday || null
        })
      });

      const payload = await response.json();
      if (!response.ok) {
        const detail = payload?.detail;
        if (typeof detail === 'string') {
          throw new Error(detail);
        }
        throw new Error('Unable to save your trend preferences right now.');
      }

      if (payload?.user) {
        onSaved?.(payload.user);
      }
    } catch (saveError) {
      setError(saveError.message || 'Unable to save your trend preferences right now.');
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="trend-pref-modal fixed inset-0 z-[2200] flex items-center justify-center bg-slate-950/75 p-4 backdrop-blur-sm" role="dialog" aria-modal="true" aria-labelledby="trend-pref-title">
      <div className="w-full max-w-2xl rounded-2xl border border-white/15 bg-slate-900 p-5 text-left shadow-2xl sm:p-6">
        {step === 'intro' ? (
          <div className="animate-[fadeIn_220ms_ease-out]">
            <p className="mb-2 text-xs font-semibold uppercase tracking-[0.2em] text-violet-300">Trend Page Guide</p>
            <h2 id="trend-pref-title" className="text-xl font-semibold text-white sm:text-2xl">How the Trends page works</h2>
            <div className="mt-3 space-y-2 text-sm text-slate-300">
              <p>MarketScope uses your preferences plus citywide scan signals to rank MSME opportunities.</p>
              <p>You will see score-based recommendations, best-fit business types, and hotspot suggestions.</p>
              <p>To generate accurate results, complete your preference profile first.</p>
            </div>

            <div className="mt-5 flex flex-wrap items-center justify-end gap-2">
              <button
                type="button"
                className="rounded-lg border border-white/15 bg-white/5 px-4 py-2.5 text-sm font-semibold text-slate-200 transition hover:bg-white/10"
                onClick={() => onLater?.()}
              >
                Fill this later
              </button>
              <button
                type="button"
                className="rounded-lg bg-violet-600 px-4 py-2.5 text-sm font-semibold text-white transition hover:bg-violet-500"
                onClick={() => setStep('form')}
              >
                Next
              </button>
            </div>
          </div>
        ) : (
          <form className="animate-[slideInUp_220ms_ease-out]" onSubmit={handleSave}>
            <p className="mb-2 text-xs font-semibold uppercase tracking-[0.2em] text-violet-300">Required Setup</p>
            <h2 id="trend-pref-title" className="text-xl font-semibold text-white sm:text-2xl">Complete your Trend Preferences</h2>
            <p className="mt-2 text-sm text-slate-300">Fill the required fields below, then press Done.</p>

            <div className="mt-4 grid gap-3 sm:grid-cols-2">
              <label className="text-sm text-slate-200">
                <span className="mb-1 block text-xs uppercase tracking-[0.16em] text-slate-400">Primary Business Interest</span>
                <select className="w-full rounded-lg border border-white/10 bg-slate-950 px-3 py-2.5 text-sm text-white outline-none focus:border-violet-400" value={formValues.primary_business} onChange={(e) => updateField('primary_business', e.target.value)}>
                  <option value="">Select...</option>
                  {BUSINESS_OPTIONS.map((option) => (
                    <option key={option.value} value={option.value}>{option.label}</option>
                  ))}
                </select>
              </label>

              <label className="text-sm text-slate-200">
                <span className="mb-1 block text-xs uppercase tracking-[0.16em] text-slate-400">Startup Capital (PHP)</span>
                <input type="number" min="0" step="1000" className="w-full rounded-lg border border-white/10 bg-slate-950 px-3 py-2.5 text-sm text-white outline-none focus:border-violet-400" value={formValues.startup_capital} onChange={(e) => updateField('startup_capital', e.target.value)} />
              </label>

              <label className="text-sm text-slate-200">
                <span className="mb-1 block text-xs uppercase tracking-[0.16em] text-slate-400">Risk Tolerance</span>
                <select className="w-full rounded-lg border border-white/10 bg-slate-950 px-3 py-2.5 text-sm text-white outline-none focus:border-violet-400" value={formValues.risk_tolerance} onChange={(e) => updateField('risk_tolerance', e.target.value)}>
                  <option value="">Select...</option>
                  <option value="low">Low</option>
                  <option value="medium">Medium</option>
                  <option value="high">High</option>
                </select>
              </label>

              <label className="text-sm text-slate-200">
                <span className="mb-1 block text-xs uppercase tracking-[0.16em] text-slate-400">Preferred Setup</span>
                <select className="w-full rounded-lg border border-white/10 bg-slate-950 px-3 py-2.5 text-sm text-white outline-none focus:border-violet-400" value={formValues.preferred_setup} onChange={(e) => updateField('preferred_setup', e.target.value)}>
                  <option value="">Select...</option>
                  <option value="kiosk">Kiosk</option>
                  <option value="storefront">Storefront</option>
                  <option value="roadside">Roadside</option>
                  <option value="market-stall">Market Stall</option>
                  <option value="warehouse">Warehouse</option>
                </select>
              </label>

              <label className="text-sm text-slate-200">
                <span className="mb-1 block text-xs uppercase tracking-[0.16em] text-slate-400">Time Commitment</span>
                <select className="w-full rounded-lg border border-white/10 bg-slate-950 px-3 py-2.5 text-sm text-white outline-none focus:border-violet-400" value={formValues.time_commitment} onChange={(e) => updateField('time_commitment', e.target.value)}>
                  <option value="">Select...</option>
                  <option value="part-time">Part-time</option>
                  <option value="full-time">Full-time</option>
                </select>
              </label>

              <label className="text-sm text-slate-200">
                <span className="mb-1 block text-xs uppercase tracking-[0.16em] text-slate-400">Target Payback (Months)</span>
                <input type="number" min="1" max="120" className="w-full rounded-lg border border-white/10 bg-slate-950 px-3 py-2.5 text-sm text-white outline-none focus:border-violet-400" value={formValues.target_payback_months} onChange={(e) => updateField('target_payback_months', e.target.value)} />
              </label>
            </div>

            {effectiveMissingFields.length > 0 && (
              <p className="mt-3 rounded-lg border border-amber-400/30 bg-amber-500/10 px-3 py-2 text-xs text-amber-200">
                Missing: {effectiveMissingFields.map((field) => FIELD_LABELS[field] || field).join(', ')}
              </p>
            )}

            {error && (
              <p className="mt-3 rounded-lg border border-rose-400/30 bg-rose-500/10 px-3 py-2 text-sm text-rose-200">{error}</p>
            )}

            <div className="mt-4 flex flex-wrap items-center justify-end gap-2">
              <button
                type="button"
                className="rounded-lg border border-white/15 bg-white/5 px-4 py-2.5 text-sm font-semibold text-slate-200 transition hover:bg-white/10"
                onClick={() => setStep('intro')}
              >
                Back
              </button>
              <button
                type="button"
                className="rounded-lg border border-white/15 bg-white/5 px-4 py-2.5 text-sm font-semibold text-slate-200 transition hover:bg-white/10"
                onClick={() => onLater?.()}
              >
                Fill later
              </button>
              <button type="submit" className="rounded-lg bg-violet-600 px-4 py-2.5 text-sm font-semibold text-white transition hover:bg-violet-500 disabled:cursor-not-allowed disabled:opacity-70" disabled={saving}>
                {saving ? 'Saving...' : 'Done'}
              </button>
            </div>
          </form>
        )}
      </div>
    </div>
  );
}
