import React, { useEffect, useMemo, useRef, useState } from 'react';
import { apiUrl } from '../lib/api';

const mapProfileToFormValues = (value) => ({
  full_name: value?.full_name || value?.name || '',
  email: value?.email || '',
  cellphone_number: value?.cellphone_number || '',
  address: value?.address || '',
  primary_business: value?.primary_business || '',
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
    <div className="profile-page page-enter">
      <div className="profile-card fade-in">
        {avatarForDisplay ? (
          <img src={avatarForDisplay} alt="Profile" className="profile-avatar-image" />
        ) : (
          <div className="profile-avatar-large">{initials}</div>
        )}
        <h2 className="profile-name">{profile?.full_name || profile?.name || 'MarketScope User'}</h2>
        <p className="profile-email">{profile?.email || 'No email available'}</p>
        <span className="profile-badge">Active Analyst</span>
      </div>

      <div className="profile-stats-grid mt-6">
        <div className="data-card profile-stat-card">
          <span className="settings-label">Total Businesses Analyzed</span>
          <strong className="profile-stat-number">{historyStats.total}</strong>
        </div>
        <div className="data-card profile-stat-card">
          <span className="settings-label">Most Successful</span>
          <strong className="profile-stat-number">{historyStats.best?.business_type || '—'}</strong>
          <span className="history-meta">Score {historyStats.best?.viability_score ?? '—'}</span>
        </div>
        <div className="data-card profile-stat-card">
          <span className="settings-label">Most Poor</span>
          <strong className="profile-stat-number">{historyStats.worst?.business_type || '—'}</strong>
          <span className="history-meta">Score {historyStats.worst?.viability_score ?? '—'}</span>
        </div>
      </div>

      <div className="settings-list mt-6">
        <div className="settings-item">
          <div className="settings-info">
            <span className="settings-label">User ID</span>
            <span className="settings-value">{userId || '—'}</span>
          </div>
        </div>
        <div className="settings-item">
          <div className="settings-info">
            <span className="settings-label">Joined</span>
            <span className="settings-value">{profile?.created_at ? new Date(profile.created_at).toLocaleDateString() : (loading ? 'Loading...' : 'Unavailable')}</span>
          </div>
        </div>
        <div className="settings-item">
          <div className="settings-info">
            <span className="settings-label">Full Name</span>
            {editing ? (
              <input
                type="text"
                className="settings-inline-input profile-form-input"
                value={formValues.full_name}
                onChange={(e) => setFormValues((current) => ({ ...current, full_name: e.target.value }))}
              />
            ) : (
              <span className="settings-value">{profile?.full_name || profile?.name || '—'}</span>
            )}
          </div>
        </div>
        <div className="settings-item">
          <div className="settings-info">
            <span className="settings-label">Account Email</span>
            {editing ? (
              <input
                type="email"
                className="settings-inline-input profile-form-input"
                value={formValues.email}
                onChange={(e) => setFormValues((current) => ({ ...current, email: e.target.value }))}
              />
            ) : (
              <span className="settings-value">{profile?.email || '—'}</span>
            )}
          </div>
        </div>
        <div className="settings-item">
          <div className="settings-info">
            <span className="settings-label">Cellphone Number</span>
            {editing ? (
              <input
                type="tel"
                className="settings-inline-input profile-form-input"
                value={formValues.cellphone_number}
                onChange={(e) => setFormValues((current) => ({ ...current, cellphone_number: e.target.value }))}
              />
            ) : (
              <span className="settings-value">{profile?.cellphone_number || '—'}</span>
            )}
          </div>
        </div>
        <div className="settings-item">
          <div className="settings-info">
            <span className="settings-label">Address</span>
            {editing ? (
              <input
                type="text"
                className="settings-inline-input profile-form-input"
                value={formValues.address}
                onChange={(e) => setFormValues((current) => ({ ...current, address: e.target.value }))}
              />
            ) : (
              <span className="settings-value">{profile?.address || '—'}</span>
            )}
          </div>
        </div>
        <div className="settings-item">
          <div className="settings-info">
            <span className="settings-label">Birthday</span>
            {editing ? (
              <input
                type="date"
                className="settings-inline-input profile-form-input"
                value={formValues.birthday}
                onChange={(e) => setFormValues((current) => ({ ...current, birthday: e.target.value }))}
              />
            ) : (
              <span className="settings-value">{profile?.birthday ? new Date(profile.birthday).toLocaleDateString() : '—'}</span>
            )}
          </div>
        </div>
        <div className="settings-item">
          <div className="settings-info">
            <span className="settings-label">Age</span>
            {editing ? (
              <input
                type="number"
                min="0"
                max="120"
                className="settings-inline-input profile-form-input"
                value={formValues.age}
                onChange={(e) => setFormValues((current) => ({ ...current, age: e.target.value }))}
              />
            ) : (
              <span className="settings-value">{profile?.age ?? '—'}</span>
            )}
          </div>
        </div>
        <div className="settings-item">
          <div className="settings-info">
            <span className="settings-label">Primary Business Interest</span>
            {editing ? (
              <input
                type="text"
                className="settings-inline-input profile-form-input"
                value={formValues.primary_business}
                onChange={(e) => setFormValues((current) => ({ ...current, primary_business: e.target.value }))}
              />
            ) : (
              <span className="settings-value">{profile?.primary_business || '—'}</span>
            )}
          </div>
        </div>
        <div className="settings-item">
          <div className="settings-info">
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
                  className="upload-trigger profile-upload-trigger"
                  onClick={() => profileAvatarInputRef.current?.click()}
                  onMouseDown={(event) => event.preventDefault()}
                >
                  <span>{formValues.avatar_url ? 'Change image' : 'Upload image'}</span>
                </button>
                <span className="settings-value profile-upload-status">
                  {formValues.avatar_url ? 'Image selected' : 'No image selected'}
                </span>
              </>
            ) : (
              <span className="settings-value profile-url-value">{profile?.avatar_url ? 'Uploaded image' : '—'}</span>
            )}
          </div>
        </div>
        <div className="settings-item">
          <div className="settings-info">
            <span className="settings-label">Last Refresh</span>
            <span className="settings-value">{new Date().toLocaleString()}</span>
          </div>
        </div>
      </div>

      <div className="profile-actions mt-6">
        <button className="edit-btn" onClick={handleEditToggle}>
          {editing ? 'Cancel Edit' : 'Edit'}
        </button>
        {editing && (
          <button className="primary-btn" onClick={handleSave} disabled={saving}>
            {saving ? 'Saving...' : 'Save'}
          </button>
        )}
      </div>
    </div>
  );
}