import React, { useEffect, useMemo, useRef, useState } from 'react';
import { apiUrl } from '../api';

const mapProfileToFormValues = (value) => ({
  full_name: value?.full_name || value?.name || '',
  email: value?.email || '',
  cellphone_number: value?.cellphone_number || '',
  address: value?.address || '',
  primary_business: value?.primary_business || '',
  startup_capital: value?.startup_capital ?? '',
  risk_tolerance: value?.risk_tolerance || '',
  preferred_setup: value?.preferred_setup || '',
  time_commitment: value?.time_commitment || '',
  target_payback_months: value?.target_payback_months ?? '',
  birthday: value?.birthday ? String(value.birthday).slice(0, 10) : '',
  age: value?.age ?? '',
  avatar_url: value?.avatar_url || ''
});

const readFileAsDataUrl = (file) => new Promise((resolve, reject) => {
  const reader = new FileReader();
  reader.onload = () => resolve(String(reader.result || ''));
  reader.onerror = () => reject(new Error('Failed to read image file'));
  reader.readAsDataURL(file);
});

export default function Profile({ user, onProfileUpdate }) {
  const userId = user?.user_id || user?.id;
  const [profile, setProfile] = useState(user || null);
  const [loading, setLoading] = useState(Boolean(userId));
  const [editing, setEditing] = useState(false);
  const [formValues, setFormValues] = useState(mapProfileToFormValues(user));
  const [saving, setSaving] = useState(false);
  const [historyStats, setHistoryStats] = useState({ total: 0, best: null, worst: null });
  const profileAvatarInputRef = useRef(null);

  useEffect(() => {
    if (!userId) return;

    let active = true;
    setLoading(true);

    fetch(apiUrl(`/users/${userId}`), { cache: 'no-store' })
      .then((response) => response.json())
      .then((data) => {
        if (!active) return;
        if (data?.user) {
          setProfile((current) => ({ ...current, ...data.user }));
          setFormValues(mapProfileToFormValues(data.user));
        }
      })
      .catch(() => {})
      .finally(() => {
        if (active) setLoading(false);
      });

    return () => {
      active = false;
    };
  }, [userId]);

  useEffect(() => {
    if (!userId) return;

    let active = true;
    fetch(apiUrl(`/users/${userId}/history`), { cache: 'no-store' })
      .then((response) => response.json())
      .then((data) => {
        if (!active) return;
        const items = Array.isArray(data?.history) ? data.history : [];
        const sorted = [...items].sort((left, right) => (right.viability_score || 0) - (left.viability_score || 0));
        setHistoryStats({
          total: items.length,
          best: sorted[0] || null,
          worst: sorted[sorted.length - 1] || null
        });
      })
      .catch(() => {});

    return () => {
      active = false;
    };
  }, [userId]);

  const initials = useMemo(() => {
    const name = profile?.full_name || profile?.name || 'U';
    return name
      .split(' ')
      .filter(Boolean)
      .slice(0, 2)
      .map((part) => part[0])
      .join('')
      .toUpperCase();
  }, [profile]);

  const avatarForDisplay = editing ? formValues.avatar_url : profile?.avatar_url;

  const handleSave = async () => {
    if (!userId) return;
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
      const data = await response.json();
      if (!response.ok) {
        throw new Error(data.detail || 'Unable to save profile');
      }

      setProfile((current) => ({ ...current, ...data.user }));
      onProfileUpdate?.(data.user);
      setEditing(false);
    } catch (error) {
      alert(error.message);
    } finally {
      setSaving(false);
    }
  };

  const handleEditToggle = () => {
    if (editing) {
      setFormValues(mapProfileToFormValues(profile));
      setEditing(false);
      return;
    }

    setEditing(true);
  };

  return (
    <div className="profile-page page-enter min-h-full">
      <div className="mx-auto flex w-full max-w-4xl flex-col gap-4 px-4 pb-28 pt-4 sm:px-6">
        <div className="profile-card fade-in flex flex-col items-center gap-4 rounded-2xl border border-white/10 bg-slate-900/70 p-5 text-center shadow-sm sm:flex-row sm:items-center sm:text-left">
          {avatarForDisplay ? (
            <img src={avatarForDisplay} alt="Profile" className="profile-avatar-image h-24 w-24 rounded-2xl border border-white/10 object-cover sm:h-28 sm:w-28" />
          ) : (
            <div className="profile-avatar-large flex h-24 w-24 items-center justify-center rounded-2xl bg-violet-600 text-2xl font-bold text-white sm:h-28 sm:w-28">{initials}</div>
          )}
          <div className="space-y-1">
            <h2 className="profile-name text-2xl font-semibold tracking-tight text-slate-50 sm:text-3xl">{profile?.full_name || profile?.name || 'MarketScope User'}</h2>
            <p className="profile-email text-sm text-slate-300">{profile?.email || 'No email available'}</p>
            <span className="profile-badge mt-2 inline-flex rounded-full border border-violet-400/20 bg-violet-500/10 px-3 py-1 text-xs font-medium uppercase tracking-[0.12em] text-violet-200">Active Analyst</span>
          </div>
        </div>

        <div className="profile-stats-grid grid gap-4 sm:grid-cols-3">
          <div className="data-card profile-stat-card flex flex-col gap-2 rounded-2xl border border-white/10 bg-slate-900/60 p-4 shadow-sm">
            <span className="settings-label text-[0.72rem] font-semibold uppercase tracking-[0.18em] text-slate-400">Total Businesses Analyzed</span>
            <strong className="profile-stat-number text-3xl font-semibold text-slate-50">{historyStats.total}</strong>
          </div>
          <div className="data-card profile-stat-card flex flex-col gap-2 rounded-2xl border border-white/10 bg-slate-900/60 p-4 shadow-sm">
            <span className="settings-label text-[0.72rem] font-semibold uppercase tracking-[0.18em] text-slate-400">Most Successful</span>
            <strong className="profile-stat-number text-xl font-semibold text-slate-50">{historyStats.best?.business_type || 'â€”'}</strong>
            <span className="history-meta text-sm text-slate-400">Score {historyStats.best?.viability_score ?? 'â€”'}</span>
          </div>
          <div className="data-card profile-stat-card flex flex-col gap-2 rounded-2xl border border-white/10 bg-slate-900/60 p-4 shadow-sm">
            <span className="settings-label text-[0.72rem] font-semibold uppercase tracking-[0.18em] text-slate-400">Most Poor</span>
            <strong className="profile-stat-number text-xl font-semibold text-slate-50">{historyStats.worst?.business_type || 'â€”'}</strong>
            <span className="history-meta text-sm text-slate-400">Score {historyStats.worst?.viability_score ?? 'â€”'}</span>
          </div>
        </div>

        <div className="settings-list mt-6 grid gap-4">
          <div className="settings-item rounded-2xl border border-[var(--border-color)] bg-[var(--bg-app)] p-4 shadow-none">
            <div className="settings-info flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
              <span className="settings-label">User ID</span>
              <span className="settings-value">{userId || 'â€”'}</span>
            </div>
          </div>

          <div className="settings-item rounded-2xl border border-[var(--border-color)] bg-[var(--bg-app)] p-4 shadow-none">
            <div className="settings-info flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
              <span className="settings-label">Joined</span>
              <span className="settings-value">{profile?.created_at ? new Date(profile.created_at).toLocaleDateString() : (loading ? 'Loading...' : 'Unavailable')}</span>
            </div>
          </div>

          <div className="settings-item rounded-2xl border border-[var(--border-color)] bg-[var(--bg-app)] p-4 shadow-none">
            <div className="settings-info flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
              <span className="settings-label">Full Name</span>
              {editing ? (
                <input
                  type="text"
                  className="settings-inline-input profile-form-input w-full rounded-lg border border-white/10 bg-transparent px-3 py-2.5 text-sm text-[var(--text-main)] outline-none transition placeholder:text-[color:var(--text-muted)] focus:border-violet-400 focus:ring-2 focus:ring-violet-400/20"
                  value={formValues.full_name}
                  onChange={(e) => setFormValues((current) => ({ ...current, full_name: e.target.value }))}
                />
              ) : (
                <span className="settings-value">{profile?.full_name || profile?.name || 'â€”'}</span>
              )}
            </div>
          </div>

          <div className="settings-item rounded-2xl border border-[var(--border-color)] bg-[var(--bg-app)] p-4 shadow-none">
            <div className="settings-info flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
              <span className="settings-label">Account Email</span>
              {editing ? (
                <input
                  type="email"
                  className="settings-inline-input profile-form-input w-full rounded-lg border border-white/10 bg-transparent px-3 py-2.5 text-sm text-[var(--text-main)] outline-none transition placeholder:text-[color:var(--text-muted)] focus:border-violet-400 focus:ring-2 focus:ring-violet-400/20"
                  value={formValues.email}
                  onChange={(e) => setFormValues((current) => ({ ...current, email: e.target.value }))}
                />
              ) : (
                <span className="settings-value">{profile?.email || 'â€”'}</span>
              )}
            </div>
          </div>

          <div className="settings-item rounded-2xl border border-[var(--border-color)] bg-[var(--bg-app)] p-4 shadow-none">
            <div className="settings-info flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
              <span className="settings-label">Cellphone Number</span>
              {editing ? (
                <input
                  type="tel"
                  className="settings-inline-input profile-form-input w-full rounded-lg border border-white/10 bg-transparent px-3 py-2.5 text-sm text-[var(--text-main)] outline-none transition placeholder:text-[color:var(--text-muted)] focus:border-violet-400 focus:ring-2 focus:ring-violet-400/20"
                  value={formValues.cellphone_number}
                  onChange={(e) => setFormValues((current) => ({ ...current, cellphone_number: e.target.value }))}
                />
              ) : (
                <span className="settings-value">{profile?.cellphone_number || 'â€”'}</span>
              )}
            </div>
          </div>

          <div className="settings-item rounded-2xl border border-[var(--border-color)] bg-[var(--bg-app)] p-4 shadow-none">
            <div className="settings-info flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
              <span className="settings-label">Address</span>
              {editing ? (
                <input
                  type="text"
                  className="settings-inline-input profile-form-input w-full rounded-lg border border-white/10 bg-transparent px-3 py-2.5 text-sm text-[var(--text-main)] outline-none transition placeholder:text-[color:var(--text-muted)] focus:border-violet-400 focus:ring-2 focus:ring-violet-400/20"
                  value={formValues.address}
                  onChange={(e) => setFormValues((current) => ({ ...current, address: e.target.value }))}
                />
              ) : (
                <span className="settings-value">{profile?.address || 'â€”'}</span>
              )}
            </div>
          </div>

          <div className="settings-item rounded-2xl border border-[var(--border-color)] bg-[var(--bg-app)] p-4 shadow-none">
            <div className="settings-info flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
              <span className="settings-label">Birthday</span>
              {editing ? (
                <input
                  type="date"
                  className="settings-inline-input profile-form-input w-full rounded-lg border border-white/10 bg-transparent px-3 py-2.5 text-sm text-[var(--text-main)] outline-none transition focus:border-violet-400 focus:ring-2 focus:ring-violet-400/20"
                  value={formValues.birthday}
                  onChange={(e) => setFormValues((current) => ({ ...current, birthday: e.target.value }))}
                />
              ) : (
                <span className="settings-value">{profile?.birthday ? new Date(profile.birthday).toLocaleDateString() : 'â€”'}</span>
              )}
            </div>
          </div>

          <div className="settings-item rounded-2xl border border-[var(--border-color)] bg-[var(--bg-app)] p-4 shadow-none">
            <div className="settings-info flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
              <span className="settings-label">Age</span>
              {editing ? (
                <input
                  type="number"
                  min="0"
                  max="120"
                  className="settings-inline-input profile-form-input w-full rounded-lg border border-white/10 bg-transparent px-3 py-2.5 text-sm text-[var(--text-main)] outline-none transition focus:border-violet-400 focus:ring-2 focus:ring-violet-400/20"
                  value={formValues.age}
                  onChange={(e) => setFormValues((current) => ({ ...current, age: e.target.value }))}
                />
              ) : (
                <span className="settings-value">{profile?.age ?? 'â€”'}</span>
              )}
            </div>
          </div>

          <div className="settings-item rounded-2xl border border-[var(--border-color)] bg-[var(--bg-app)] p-4 shadow-none">
            <div className="settings-info flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
              <span className="settings-label">Primary Business Interest</span>
              {editing ? (
                <input
                  type="text"
                  className="settings-inline-input profile-form-input w-full rounded-lg border border-white/10 bg-transparent px-3 py-2.5 text-sm text-[var(--text-main)] outline-none transition placeholder:text-[color:var(--text-muted)] focus:border-violet-400 focus:ring-2 focus:ring-violet-400/20"
                  value={formValues.primary_business}
                  onChange={(e) => setFormValues((current) => ({ ...current, primary_business: e.target.value }))}
                />
              ) : (
                <span className="settings-value">{profile?.primary_business || 'â€”'}</span>
              )}
            </div>
          </div>

          <div className="settings-item rounded-2xl border border-[var(--border-color)] bg-[var(--bg-app)] p-4 shadow-none">
            <div className="settings-info flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
              <span className="settings-label">Startup Capital (PHP)</span>
              {editing ? (
                <input
                  type="number"
                  min="0"
                  step="1000"
                  className="settings-inline-input profile-form-input w-full rounded-lg border border-white/10 bg-transparent px-3 py-2.5 text-sm text-[var(--text-main)] outline-none transition focus:border-violet-400 focus:ring-2 focus:ring-violet-400/20"
                  value={formValues.startup_capital}
                  onChange={(e) => setFormValues((current) => ({ ...current, startup_capital: e.target.value }))}
                />
              ) : (
                <span className="settings-value">{profile?.startup_capital ? `PHP ${Number(profile.startup_capital).toLocaleString()}` : 'â€”'}</span>
              )}
            </div>
          </div>

          <div className="settings-item rounded-2xl border border-[var(--border-color)] bg-[var(--bg-app)] p-4 shadow-none">
            <div className="settings-info flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
              <span className="settings-label">Risk Tolerance</span>
              {editing ? (
                <select
                  className="settings-inline-input profile-form-input w-full rounded-lg border border-white/10 bg-transparent px-3 py-2.5 text-sm text-[var(--text-main)] outline-none transition focus:border-violet-400 focus:ring-2 focus:ring-violet-400/20"
                  value={formValues.risk_tolerance}
                  onChange={(e) => setFormValues((current) => ({ ...current, risk_tolerance: e.target.value }))}
                >
                  <option value="">Not set</option>
                  <option value="low">Low</option>
                  <option value="medium">Medium</option>
                  <option value="high">High</option>
                </select>
              ) : (
                <span className="settings-value">{profile?.risk_tolerance || 'â€”'}</span>
              )}
            </div>
          </div>

          <div className="settings-item rounded-2xl border border-[var(--border-color)] bg-[var(--bg-app)] p-4 shadow-none">
            <div className="settings-info flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
              <span className="settings-label">Preferred Setup</span>
              {editing ? (
                <select
                  className="settings-inline-input profile-form-input w-full rounded-lg border border-white/10 bg-transparent px-3 py-2.5 text-sm text-[var(--text-main)] outline-none transition focus:border-violet-400 focus:ring-2 focus:ring-violet-400/20"
                  value={formValues.preferred_setup}
                  onChange={(e) => setFormValues((current) => ({ ...current, preferred_setup: e.target.value }))}
                >
                  <option value="">Not set</option>
                  <option value="kiosk">Kiosk</option>
                  <option value="storefront">Storefront</option>
                  <option value="roadside">Roadside</option>
                  <option value="market-stall">Market Stall</option>
                  <option value="warehouse">Warehouse</option>
                </select>
              ) : (
                <span className="settings-value">{profile?.preferred_setup || 'â€”'}</span>
              )}
            </div>
          </div>

          <div className="settings-item rounded-2xl border border-[var(--border-color)] bg-[var(--bg-app)] p-4 shadow-none">
            <div className="settings-info flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
              <span className="settings-label">Time Commitment</span>
              {editing ? (
                <select
                  className="settings-inline-input profile-form-input w-full rounded-lg border border-white/10 bg-transparent px-3 py-2.5 text-sm text-[var(--text-main)] outline-none transition focus:border-violet-400 focus:ring-2 focus:ring-violet-400/20"
                  value={formValues.time_commitment}
                  onChange={(e) => setFormValues((current) => ({ ...current, time_commitment: e.target.value }))}
                >
                  <option value="">Not set</option>
                  <option value="part-time">Part-time</option>
                  <option value="full-time">Full-time</option>
                </select>
              ) : (
                <span className="settings-value">{profile?.time_commitment || 'â€”'}</span>
              )}
            </div>
          </div>

          <div className="settings-item rounded-2xl border border-[var(--border-color)] bg-[var(--bg-app)] p-4 shadow-none">
            <div className="settings-info flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
              <span className="settings-label">Target Payback (Months)</span>
              {editing ? (
                <input
                  type="number"
                  min="1"
                  max="120"
                  className="settings-inline-input profile-form-input w-full rounded-lg border border-white/10 bg-transparent px-3 py-2.5 text-sm text-[var(--text-main)] outline-none transition focus:border-violet-400 focus:ring-2 focus:ring-violet-400/20"
                  value={formValues.target_payback_months}
                  onChange={(e) => setFormValues((current) => ({ ...current, target_payback_months: e.target.value }))}
                />
              ) : (
                <span className="settings-value">{profile?.target_payback_months ? `${profile.target_payback_months} months` : 'â€”'}</span>
              )}
            </div>
          </div>

          <div className="settings-item rounded-2xl border border-[var(--border-color)] bg-[var(--bg-app)] p-4 shadow-none">
            <div className="settings-info flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
              <span className="settings-label">Profile Picture</span>
              {editing ? (
                <>
                  <input
                    ref={profileAvatarInputRef}
                    type="file"
                    accept="image/*"
                    className="upload-input-hidden"
                    tabIndex={-1}
                    onChange={async (event) => {
                      const file = event.target.files?.[0];
                      if (!file) return;

                      if (file.size > 2 * 1024 * 1024) {
                        alert('Profile picture must be 2MB or smaller.');
                        event.target.value = '';
                        return;
                      }

                      try {
                        const dataUrl = await readFileAsDataUrl(file);
                        setFormValues((current) => ({ ...current, avatar_url: dataUrl }));
                      } catch (error) {
                        alert(error.message || 'Unable to read selected image.');
                      }
                    }}
                  />
                  <button
                    type="button"
                    className="upload-trigger profile-upload-trigger inline-flex items-center justify-center rounded-lg border border-white/10 bg-white/5 px-4 py-2.5 text-sm font-medium text-slate-100 transition hover:border-violet-400/40 hover:bg-violet-500/10"
                    onClick={() => profileAvatarInputRef.current?.click()}
                    onMouseDown={(event) => event.preventDefault()}
                  >
                    <span>{formValues.avatar_url ? 'Change image' : 'Upload image'}</span>
                  </button>
                  <span className="settings-value profile-upload-status text-sm text-slate-400">
                    {formValues.avatar_url ? 'Image selected' : 'No image selected'}
                  </span>
                </>
              ) : (
                <span className="settings-value profile-url-value text-sm text-slate-300">{profile?.avatar_url ? 'Uploaded image' : 'â€”'}</span>
              )}
            </div>
          </div>

          <div className="settings-item rounded-2xl border border-white/10 !bg-transparent p-4 !shadow-none">
            <div className="settings-info flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
              <span className="settings-label">Last Refresh</span>
              <span className="settings-value">{new Date().toLocaleString()}</span>
            </div>
          </div>
        </div>

      <div className="profile-actions mt-4 flex flex-col gap-3 sm:flex-row sm:justify-end">
        <button className="edit-btn inline-flex items-center justify-center rounded-lg border border-white/10 bg-white/5 px-5 py-2.5 text-sm font-medium text-slate-100 transition hover:border-violet-400/40 hover:bg-violet-500/10" onClick={handleEditToggle}>
          {editing ? 'Cancel Edit' : 'Edit'}
        </button>
        {editing && (
          <button className="primary-btn inline-flex w-full items-center justify-center rounded-lg bg-violet-600 px-5 py-2.5 text-sm font-medium text-white transition hover:bg-violet-500 disabled:cursor-not-allowed disabled:opacity-60 sm:w-auto" onClick={handleSave} disabled={saving}>
            {saving ? 'Saving...' : 'Save'}
          </button>
        )}
      </div>
    </div>
    </div>
  );
}

