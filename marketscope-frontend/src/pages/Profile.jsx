import React, { useEffect, useMemo, useRef, useState } from 'react';
import { apiUrl } from '../lib/api';
import { getBusinessTypeLabel, BUSINESS_TYPE_OPTIONS as PRIMARY_BUSINESS_OPTIONS } from '../utils/businessTypes';
import { getScoreTone } from '../utils/scoreTone';
import { computeAgeFromBirthday, todayYmd } from '../utils/age';
import { PANABO_BARANGAYS, PANABO_CITY, PANABO_REGION } from '../constants/panaboBarangays';

// Accounts created before names were split only have full_name, which can't be
// divided reliably ("Juan Dela Cruz"), so it starts under First Name to correct.
const mapProfileToFormValues = (value) => ({
  full_name: value?.full_name || value?.name || '',
  first_name: value?.first_name || value?.full_name || value?.name || '',
  last_name: value?.last_name || '',
  email: value?.email || '',
  cellphone_number: value?.cellphone_number || '',
  address: value?.address || '',
  street: value?.street || '',
  barangay: value?.barangay || '',
  primary_business: value?.primary_business || '',
  preferred_setup: value?.preferred_setup || '',
  birthday: value?.birthday ? String(value.birthday).slice(0, 10) : '',
  avatar_url: value?.avatar_url || ''
});

const readFileAsDataUrl = (file) => new Promise((resolve, reject) => {
  const reader = new FileReader();
  reader.onload = () => resolve(String(reader.result || ''));
  reader.onerror = () => reject(new Error('Failed to read image file'));
  reader.readAsDataURL(file);
});

const inlineInputClass = 'settings-inline-input profile-form-input w-full rounded-lg border border-[var(--border-color)] bg-transparent px-3 py-2 text-sm text-[var(--text-main)] outline-none transition placeholder:text-[color:var(--text-muted)] focus:border-[var(--accent)] focus:ring-2 focus:ring-[var(--focus-ring)] sm:max-w-[260px]';

const Row = ({ label, children }) => (
  <div className="flex flex-col gap-1.5 py-3 first:pt-0 last:pb-0 sm:flex-row sm:items-center sm:justify-between sm:gap-4">
    <span className="settings-label">{label}</span>
    {children}
  </div>
);

export default function Profile({ user, onProfileUpdate }) {
  const userId = user?.user_id || user?.id;
  const [profile, setProfile] = useState(user || null);
  const [loading, setLoading] = useState(Boolean(userId));
  const [editingSection, setEditingSection] = useState(null); // null | 'personal' | 'business'
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

  const avatarForDisplay = editingSection === 'personal'
    ? (formValues.avatar_url || profile?.avatar_url)
    : profile?.avatar_url;

  const selectedPrimaryBusinessLabel = useMemo(() => {
    const current = String(profile?.primary_business || '').trim();
    if (!current) return '-';
    const matched = PRIMARY_BUSINESS_OPTIONS.find((option) => option.value === current);
    return matched?.label || current;
  }, [profile?.primary_business]);

  const joinedDateLabel = profile?.created_at
    ? new Date(profile.created_at).toLocaleDateString()
    : (loading ? 'Loading...' : 'Unavailable');

  // Calculated from the birthday. Older accounts may only have a typed age.
  const ageFromBirthday = computeAgeFromBirthday(profile?.birthday);
  const ageLabel = ageFromBirthday ?? profile?.age ?? '-';
  const editingAgeLabel = formValues.birthday ? computeAgeFromBirthday(formValues.birthday) : (profile?.birthday ? '-' : ageLabel);

  // An older account's whole name sits under First Name until it's corrected.
  // Leave its split name unsaved unless the person actually changed it.
  const saved = mapProfileToFormValues(profile);
  const nameChanged = formValues.first_name !== saved.first_name || formValues.last_name !== saved.last_name;
  const hasSplitName = Boolean(profile?.first_name);
  const hasSplitAddress = Boolean(profile?.street || profile?.barangay);

  const handleSave = async () => {
    if (!userId) return;

    const { first_name, last_name, ...otherValues } = formValues;
    const shouldSaveName = hasSplitName || nameChanged;
    if (shouldSaveName && (!first_name.trim() || !last_name.trim())) {
      alert('Enter both your first name and last name.');
      return;
    }

    setSaving(true);
    try {
      const response = await fetch(apiUrl(`/users/${userId}`), {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          ...otherValues,
          ...(shouldSaveName ? { first_name, last_name } : {}),
          // Clearing the birthday also clears the age that came from it.
          age: formValues.birthday || profile?.birthday ? null : (profile?.age ?? null),
          birthday: formValues.birthday || null
        })
      });
      const data = await response.json();
      if (!response.ok) {
        throw new Error(data.detail || 'Unable to save profile');
      }

      setProfile((current) => ({ ...current, ...data.user }));
      onProfileUpdate?.(data.user);
      setEditingSection(null);
    } catch (error) {
      alert(error.message);
    } finally {
      setSaving(false);
    }
  };

  const startEditing = (section) => {
    setFormValues(mapProfileToFormValues(profile));
    setEditingSection(section);
  };

  const cancelEditing = () => {
    setFormValues(mapProfileToFormValues(profile));
    setEditingSection(null);
  };

  const updateField = (field) => (event) => {
    const value = event.target.value;
    setFormValues((current) => ({ ...current, [field]: value }));
  };

  const sectionControls = (section) => (
    editingSection === section ? (
      <div className="flex items-center gap-2">
        <button
          type="button"
          className="min-h-[40px] rounded-lg border border-[var(--border-color)] bg-[var(--bg-sheet)] px-4 py-2 text-xs font-semibold text-[var(--text-main)] transition hover:border-[var(--border-strong)] hover:bg-[var(--accent-hover)]"
          onClick={cancelEditing}
          disabled={saving}
        >
          Cancel
        </button>
        <button
          type="button"
          className="min-h-[40px] rounded-lg bg-[var(--btn-primary-bg)] px-4 py-2 text-xs font-semibold text-[var(--btn-primary-text)] transition hover:bg-[var(--btn-primary-hover)] disabled:cursor-not-allowed disabled:opacity-60"
          onClick={handleSave}
          disabled={saving}
        >
          {saving ? 'Saving...' : 'Save'}
        </button>
      </div>
    ) : (
      <button
        type="button"
        className="min-h-[40px] rounded-lg border border-[var(--border-color)] bg-[var(--bg-sheet)] px-4 py-2 text-xs font-semibold text-[var(--text-main)] transition hover:border-[var(--border-strong)] hover:bg-[var(--accent-hover)] disabled:cursor-not-allowed disabled:opacity-50"
        onClick={() => startEditing(section)}
        disabled={editingSection !== null || saving}
      >
        Edit
      </button>
    )
  );

  const bestScore = historyStats.best?.viability_score;
  const worstScore = historyStats.worst?.viability_score;

  return (
    <div className="profile-page page-enter min-h-full">
      <div className="profile-shell mx-auto flex w-full max-w-8xl flex-col gap-4 px-6 pb-28 pt-4 sm:px-8 lg:grid lg:grid-cols-[320px_minmax(0,1fr)] lg:items-start lg:gap-6">
        <div className="profile-side-rail flex flex-col gap-4">
          <div className="profile-card profile-hero-card fade-in flex flex-col items-center gap-4 p-6 text-center">
            <div className="profile-avatar-wrapper">
              {avatarForDisplay ? (
                <img src={avatarForDisplay} alt="Profile" className="profile-avatar-image" />
              ) : (
                <div className="profile-avatar-large">{initials}</div>
              )}
              {editingSection === 'personal' && (
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
                    className="profile-avatar-edit-btn"
                    title="Change profile picture"
                    aria-label="Change profile picture"
                    onClick={() => profileAvatarInputRef.current?.click()}
                    onMouseDown={(event) => event.preventDefault()}
                  >
                    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true">
                      <path d="M14.5 4h-5L7 7H4a2 2 0 0 0-2 2v9a2 2 0 0 0 2 2h16a2 2 0 0 0 2-2V9a2 2 0 0 0-2-2h-3l-2.5-3z" />
                      <circle cx="12" cy="13" r="3" />
                    </svg>
                  </button>
                </>
              )}
            </div>
            <div className="space-y-1">
              <h2 className="profile-name">{profile?.full_name || profile?.name || 'MarketScope User'}</h2>
              <p className="profile-email">{profile?.email || 'No email available'}</p>
              <span className="profile-badge mt-2">Active Analyst</span>
              <p className="mt-2 text-xs text-[var(--text-muted)]">Joined {joinedDateLabel}</p>
              {editingSection === 'personal' && (
                <p className="text-xs text-[var(--accent)]">
                  {formValues.avatar_url !== (profile?.avatar_url || '') ? 'New image selected' : 'Tap the camera to change your photo'}
                </p>
              )}
            </div>
          </div>

          <div className="data-card profile-stat-card p-5">
            <p className="eyebrow-label mb-4">Analysis Snapshot</p>
            <div className="flex flex-col divide-y divide-[var(--border-color)]">
              <div className="flex items-center justify-between gap-3 py-3 first:pt-0 last:pb-0">
                <span className="inline-flex items-center gap-2 text-sm text-[var(--text-muted)]">
                  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className="text-[var(--accent)]" aria-hidden="true">
                    <path d="M3 3v18h18" /><path d="m19 9-5 5-4-4-3 3" />
                  </svg>
                  Analyses run
                </span>
                <strong className="text-xl font-bold tabular-nums text-[var(--text-main)]">{historyStats.total}</strong>
              </div>
              <div className="flex flex-col gap-1.5 py-3 first:pt-0 last:pb-0">
                <span className="inline-flex items-center gap-2 text-sm text-[var(--text-muted)]">
                  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className="text-[var(--trend-up)]" aria-hidden="true">
                    <path d="M8 21h8" /><path d="M12 17v4" /><path d="M17 4H7v5a5 5 0 0 0 10 0V4z" /><path d="M17 6h3a1 1 0 0 1 1 1c0 2-1.5 3.5-3.5 3.5" /><path d="M7 6H4a1 1 0 0 0-1 1c0 2 1.5 3.5 3.5 3.5" />
                  </svg>
                  Best performer
                </span>
                <span className="flex items-center justify-between gap-2">
                  <span className="truncate text-sm font-semibold text-[var(--text-main)]">
                    {historyStats.best ? (getBusinessTypeLabel(historyStats.best.business_type) || historyStats.best.business_type) : '-'}
                  </span>
                  {bestScore != null && <span className={`trends-score-badge ${getScoreTone(bestScore)}`}>{bestScore}</span>}
                </span>
              </div>
              <div className="flex flex-col gap-1.5 py-3 first:pt-0 last:pb-0">
                <span className="inline-flex items-center gap-2 text-sm text-[var(--text-muted)]">
                  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className="text-[var(--trend-down)]" aria-hidden="true">
                    <path d="M3 3v18h18" /><path d="m19 15-5-5-4 4-3-3" />
                  </svg>
                  Lowest score
                </span>
                <span className="flex items-center justify-between gap-2">
                  <span className="truncate text-sm font-semibold text-[var(--text-main)]">
                    {historyStats.worst ? (getBusinessTypeLabel(historyStats.worst.business_type) || historyStats.worst.business_type) : '-'}
                  </span>
                  {worstScore != null && <span className={`trends-score-badge ${getScoreTone(worstScore)}`}>{worstScore}</span>}
                </span>
              </div>
            </div>
          </div>
        </div>

        <div className="profile-main-col flex min-w-0 flex-col gap-4">
          <div className="data-card fade-in p-5 sm:p-6">
            <div className="mb-4 flex items-center justify-between gap-3">
              <p className="eyebrow-label">Personal Information</p>
              {sectionControls('personal')}
            </div>
            <div className="flex flex-col divide-y divide-[var(--border-color)]">
              {editingSection === 'personal' ? (
                <>
                  <Row label="First Name">
                    <input type="text" className={inlineInputClass} autoComplete="given-name" maxLength={120} value={formValues.first_name} onChange={updateField('first_name')} />
                  </Row>
                  <Row label="Last Name">
                    <input type="text" className={inlineInputClass} autoComplete="family-name" maxLength={120} value={formValues.last_name} onChange={updateField('last_name')} />
                  </Row>
                </>
              ) : (
                <Row label="Full Name">
                  <span className="settings-value">{profile?.full_name || profile?.name || '-'}</span>
                </Row>
              )}
              <Row label="Account Email">
                {editingSection === 'personal' ? (
                  <input type="email" className={inlineInputClass} value={formValues.email} onChange={updateField('email')} />
                ) : (
                  <span className="settings-value">{profile?.email || '-'}</span>
                )}
              </Row>
              <Row label="Cellphone Number">
                {editingSection === 'personal' ? (
                  <input type="tel" className={inlineInputClass} value={formValues.cellphone_number} onChange={updateField('cellphone_number')} />
                ) : (
                  <span className="settings-value">{profile?.cellphone_number || '-'}</span>
                )}
              </Row>
              {editingSection === 'personal' ? (
                <>
                  {profile?.address && !hasSplitAddress && (
                    <Row label="Current Address">
                      <span className="settings-value">{profile.address}</span>
                    </Row>
                  )}
                  <Row label="Street">
                    <input type="text" className={inlineInputClass} autoComplete="address-line1" placeholder="House no. and street" value={formValues.street} onChange={updateField('street')} />
                  </Row>
                  <Row label="Barangay">
                    <select className={inlineInputClass} value={formValues.barangay} onChange={updateField('barangay')}>
                      <option value="">Not set</option>
                      {/* Keeps a saved value selectable even if it isn't in the current list. */}
                      {formValues.barangay && !PANABO_BARANGAYS.includes(formValues.barangay) && (
                        <option value={formValues.barangay}>{formValues.barangay}</option>
                      )}
                      {PANABO_BARANGAYS.map((barangay) => (
                        <option key={barangay} value={barangay}>{barangay}</option>
                      ))}
                    </select>
                  </Row>
                  <Row label="City">
                    <span className="settings-value">{PANABO_CITY}</span>
                  </Row>
                  <Row label="Region">
                    <span className="settings-value">{PANABO_REGION}</span>
                  </Row>
                </>
              ) : (
                <Row label="Address">
                  <span className="settings-value">{profile?.address || '-'}</span>
                </Row>
              )}
              <Row label="Birthday">
                {editingSection === 'personal' ? (
                  <input type="date" className={inlineInputClass} autoComplete="bday" min="1900-01-01" max={todayYmd()} value={formValues.birthday} onChange={updateField('birthday')} />
                ) : (
                  <span className="settings-value">{profile?.birthday ? new Date(profile.birthday).toLocaleDateString() : '-'}</span>
                )}
              </Row>
              <Row label="Age">
                <span className="settings-value">{editingSection === 'personal' ? editingAgeLabel : ageLabel}</span>
              </Row>
            </div>
          </div>

          <div className="data-card fade-in p-5 sm:p-6">
            <div className="mb-4 flex items-center justify-between gap-3">
              <p className="eyebrow-label">Business Preferences</p>
              {sectionControls('business')}
            </div>
            <div className="flex flex-col divide-y divide-[var(--border-color)]">
              <Row label="Primary Business Interest">
                {editingSection === 'business' ? (
                  <select className={inlineInputClass} value={formValues.primary_business} onChange={updateField('primary_business')}>
                    <option value="">Not set</option>
                    {PRIMARY_BUSINESS_OPTIONS.map((option) => (
                      <option key={option.value} value={option.value}>{option.label}</option>
                    ))}
                  </select>
                ) : (
                  <span className="settings-value">{selectedPrimaryBusinessLabel}</span>
                )}
              </Row>
              <Row label="Preferred Setup">
                {editingSection === 'business' ? (
                  <select className={inlineInputClass} value={formValues.preferred_setup} onChange={updateField('preferred_setup')}>
                    <option value="">Not set</option>
                    <option value="kiosk">Kiosk</option>
                    <option value="storefront">Storefront</option>
                    <option value="roadside">Roadside</option>
                    <option value="market-stall">Market Stall</option>
                    <option value="warehouse">Warehouse</option>
                  </select>
                ) : (
                  <span className="settings-value capitalize">{profile?.preferred_setup || '-'}</span>
                )}
              </Row>
            </div>
          </div>

          <p className="px-1 text-xs text-[var(--text-muted)]">
            User ID {userId || '-'} · Joined {joinedDateLabel} · Last refreshed {new Date().toLocaleString()}
          </p>
        </div>
      </div>
    </div>
  );
}
