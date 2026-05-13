import React, { useEffect, useMemo, useState } from 'react';
import { apiUrl } from '../api';
import { parseCoordinatePairText } from '../utils/coordinates';

const defaultMsmeForm = {
  name: '',
  business_type: '',
  latitude: '',
  longitude: ''
};

const defaultAdminSpaceForm = {
  title: '',
  listing_mode: 'rent',
  guarantee_level: 'potential',
  confidence_score: '',
  property_type: '',
  business_type: '',
  latitude: '',
  longitude: '',
  address_text: '',
  price_min: '',
  price_max: '',
  source_note: '',
  contact_info: '',
  notes: '',
  verified_at: '',
  expires_at: '',
  is_active: true
};

const BUSINESS_TYPE_OPTIONS = [
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

const mapUserToForm = (user) => ({
  full_name: user?.full_name || user?.name || '',
  email: user?.email || '',
  address: user?.address || '',
  cellphone_number: user?.cellphone_number || '',
  avatar_url: user?.avatar_url || '',
  age: user?.age ?? '',
  birthday: user?.birthday ? String(user.birthday).slice(0, 10) : '',
  primary_business: user?.primary_business || ''
});

const getBusinessTypeLabel = (value) => {
  const found = BUSINESS_TYPE_OPTIONS.find((option) => option.value === value);
  return found?.label || value || '-';
};

const getListingModeLabel = (value) => {
  const normalized = String(value || '').toLowerCase();
  if (normalized === 'buy') return 'For Sale';
  if (normalized === 'rent') return 'For Rent';
  return value || '-';
};

const getSubmissionStatusMeta = (status) => {
  const normalized = String(status || '').toLowerCase();

  if (normalized === 'approved') {
    return {
      label: 'Approved',
      className: 'status-approved',
      message: 'Approved listings are prioritized for map publishing.'
    };
  }

  if (normalized === 'rejected') {
    return {
      label: 'Rejected',
      className: 'status-rejected',
      message: 'Rejected listings stay in records for audit and follow-up.'
    };
  }

  if (normalized === 'archived') {
    return {
      label: 'Archived',
      className: 'status-archived',
      message: 'Archived listings are hidden from active review workflows.'
    };
  }

  return {
    label: 'Pending',
    className: 'status-pending',
    message: 'Pending listings need admin action before publication.'
  };
};

const formatPesoRange = (minValue, maxValue) => {
  const min = Number(minValue || 0);
  const max = Number(maxValue || 0);

  if (min > 0 && max > 0) return `PHP ${min.toLocaleString()} - PHP ${max.toLocaleString()}`;
  if (min > 0) return `From PHP ${min.toLocaleString()}`;
  if (max > 0) return `Up to PHP ${max.toLocaleString()}`;
  return 'Not set';
};

export default function AdminPanel({ adminSession }) {
  const token = adminSession?.token;
  const [activeTab, setActiveTab] = useState('msmes');

  const [customMsmes, setCustomMsmes] = useState([]);
  const [msmeForm, setMsmeForm] = useState(defaultMsmeForm);
  const [editingMsmeId, setEditingMsmeId] = useState(null);
  const [msmeLoading, setMsmeLoading] = useState(true);
  const [msmeSearchTerm, setMsmeSearchTerm] = useState('');
  const [msmeSortBy, setMsmeSortBy] = useState('type-asc');

  const [users, setUsers] = useState([]);
  const [userLoading, setUserLoading] = useState(true);
  const [editingUserId, setEditingUserId] = useState(null);
  const [userForm, setUserForm] = useState(null);

  const [userSpaceSubmissions, setUserSpaceSubmissions] = useState([]);
  const [adminSpaceSubmissions, setAdminSpaceSubmissions] = useState([]);
  const [spaceLoading, setSpaceLoading] = useState(true);
  const [spaceFilterStatus, setSpaceFilterStatus] = useState('pending');
  const [adminSpaceForm, setAdminSpaceForm] = useState(defaultAdminSpaceForm);

  const [errorMessage, setErrorMessage] = useState('');
  const [successMessage, setSuccessMessage] = useState('');

  const headers = useMemo(() => ({
    'Content-Type': 'application/json',
    'x-admin-token': token || ''
  }), [token]);

  const filteredCustomMsmes = useMemo(() => {
    const search = msmeSearchTerm.trim().toLowerCase();
    let items = Array.isArray(customMsmes) ? [...customMsmes] : [];

    if (search) {
      items = items.filter((item) => {
        const name = String(item?.name || '').toLowerCase();
        const type = String(item?.business_type || '').toLowerCase();
        return name.includes(search) || type.includes(search);
      });
    }

    items.sort((a, b) => {
      const aType = String(a?.business_type || '').toLowerCase();
      const bType = String(b?.business_type || '').toLowerCase();
      const aName = String(a?.name || '').toLowerCase();
      const bName = String(b?.name || '').toLowerCase();

      if (msmeSortBy === 'type-desc') {
        if (aType !== bType) return bType.localeCompare(aType);
        return aName.localeCompare(bName);
      }
      if (msmeSortBy === 'name-asc') return aName.localeCompare(bName);
      if (msmeSortBy === 'name-desc') return bName.localeCompare(aName);

      if (aType !== bType) return aType.localeCompare(bType);
      return aName.localeCompare(bName);
    });

    return items;
  }, [customMsmes, msmeSearchTerm, msmeSortBy]);

  const resetMessages = () => {
    setErrorMessage('');
    setSuccessMessage('');
  };

  const handleCoordinatePaste = (setter) => (event) => {
    const clipboardText = event.clipboardData?.getData('text');
    const parsed = parseCoordinatePairText(clipboardText);
    if (!parsed) return;

    event.preventDefault();
    setter((current) => ({
      ...current,
      latitude: String(parsed.latitude),
      longitude: String(parsed.longitude)
    }));
  };

  const loadCustomMsmes = async () => {
    if (!token) return;
    setMsmeLoading(true);
    try {
      const response = await fetch(apiUrl('/admin/custom-msmes'), { headers });
      const data = await response.json();
      if (!response.ok) throw new Error(data.detail || 'Failed to load custom MSMEs');
      setCustomMsmes(Array.isArray(data.custom_msmes) ? data.custom_msmes : []);
    } catch (error) {
      setErrorMessage(error.message || 'Failed to load custom MSMEs');
    } finally {
      setMsmeLoading(false);
    }
  };

  const loadUsers = async () => {
    if (!token) return;
    setUserLoading(true);
    try {
      const response = await fetch(apiUrl('/admin/users'), { headers });
      const data = await response.json();
      if (!response.ok) throw new Error(data.detail || 'Failed to load users');
      setUsers(Array.isArray(data.users) ? data.users : []);
    } catch (error) {
      setErrorMessage(error.message || 'Failed to load users');
    } finally {
      setUserLoading(false);
    }
  };

  const loadSpaces = async (statusOverride) => {
    if (!token) return;
    setSpaceLoading(true);
    const status = statusOverride || spaceFilterStatus;

    try {
      const [userResponse, adminResponse] = await Promise.all([
        fetch(apiUrl(`/admin/spaces/user-submissions${status === 'all' ? '' : `?status=${status}`}`), { headers }),
        fetch(apiUrl('/admin/spaces/admin-submissions'), { headers })
      ]);

      const userData = await userResponse.json();
      const adminData = await adminResponse.json();

      if (!userResponse.ok) throw new Error(userData.detail || 'Failed to load user submissions');
      if (!adminResponse.ok) throw new Error(adminData.detail || 'Failed to load admin submissions');

      setUserSpaceSubmissions(Array.isArray(userData.submissions) ? userData.submissions : []);
      setAdminSpaceSubmissions(Array.isArray(adminData.submissions) ? adminData.submissions : []);
    } catch (error) {
      setErrorMessage(error.message || 'Failed to load space submissions');
    } finally {
      setSpaceLoading(false);
    }
  };

  useEffect(() => {
    resetMessages();
    loadCustomMsmes();
    loadUsers();
    loadSpaces('pending');
  }, [token]);

  useEffect(() => {
    if (activeTab === 'spaces') {
      loadSpaces(spaceFilterStatus);
    }
  }, [spaceFilterStatus, activeTab]);

  const submitMsme = async (event) => {
    event.preventDefault();
    resetMessages();

    const payload = {
      name: msmeForm.name.trim(),
      business_type: msmeForm.business_type.trim(),
      latitude: Number(msmeForm.latitude),
      longitude: Number(msmeForm.longitude)
    };

    if (!payload.name || !payload.business_type || Number.isNaN(payload.latitude) || Number.isNaN(payload.longitude)) {
      setErrorMessage('Please complete all custom MSME fields with valid coordinates.');
      return;
    }

    const isEditing = Boolean(editingMsmeId);
    const url = isEditing ? apiUrl(`/admin/custom-msmes/${editingMsmeId}`) : apiUrl('/admin/custom-msmes');
    const method = isEditing ? 'PUT' : 'POST';

    try {
      const response = await fetch(url, {
        method,
        headers,
        body: JSON.stringify(payload)
      });
      const data = await response.json();
      if (!response.ok) throw new Error(data.detail || 'Unable to save custom MSME');

      setSuccessMessage(isEditing ? 'Custom MSME updated.' : 'Custom MSME created.');
      setMsmeForm(defaultMsmeForm);
      setEditingMsmeId(null);
      await loadCustomMsmes();
    } catch (error) {
      setErrorMessage(error.message || 'Unable to save custom MSME');
    }
  };

  const startEditMsme = (item) => {
    resetMessages();
    setEditingMsmeId(item.id);
    setMsmeForm({
      name: item.name || '',
      business_type: item.business_type || '',
      latitude: item.latitude ?? '',
      longitude: item.longitude ?? ''
    });
  };

  const deleteMsme = async (item) => {
    if (!window.confirm(`Delete custom MSME: ${item.name}?`)) return;
    resetMessages();

    try {
      const response = await fetch(apiUrl(`/admin/custom-msmes/${item.id}`), {
        method: 'DELETE',
        headers
      });
      const data = await response.json();
      if (!response.ok) throw new Error(data.detail || 'Unable to delete custom MSME');

      setSuccessMessage('Custom MSME deleted.');
      if (editingMsmeId === item.id) {
        setEditingMsmeId(null);
        setMsmeForm(defaultMsmeForm);
      }
      await loadCustomMsmes();
    } catch (error) {
      setErrorMessage(error.message || 'Unable to delete custom MSME');
    }
  };

  const startEditUser = (user) => {
    resetMessages();
    setEditingUserId(user.user_id);
    setUserForm(mapUserToForm(user));
  };

  const cancelEditUser = () => {
    setEditingUserId(null);
    setUserForm(null);
  };

  const saveUser = async () => {
    if (!editingUserId || !userForm) return;
    resetMessages();

    const payload = {
      ...userForm,
      age: userForm.age === '' ? null : Number(userForm.age),
      birthday: userForm.birthday || null
    };

    if (!payload.full_name.trim() || !payload.email.trim()) {
      setErrorMessage('Full name and email are required.');
      return;
    }

    try {
      const response = await fetch(apiUrl(`/admin/users/${editingUserId}`), {
        method: 'PUT',
        headers,
        body: JSON.stringify(payload)
      });
      const data = await response.json();
      if (!response.ok) throw new Error(data.detail || 'Unable to update user');

      setSuccessMessage('User profile updated.');
      setEditingUserId(null);
      setUserForm(null);
      await loadUsers();
    } catch (error) {
      setErrorMessage(error.message || 'Unable to update user');
    }
  };

  const deleteUser = async (user) => {
    if (!window.confirm(`Delete user: ${user.full_name || user.email}?`)) return;
    resetMessages();

    try {
      const response = await fetch(apiUrl(`/admin/users/${user.user_id}`), {
        method: 'DELETE',
        headers
      });
      const data = await response.json();
      if (!response.ok) throw new Error(data.detail || 'Unable to delete user');

      setSuccessMessage('User deleted.');
      if (editingUserId === user.user_id) {
        setEditingUserId(null);
        setUserForm(null);
      }
      await loadUsers();
    } catch (error) {
      setErrorMessage(error.message || 'Unable to delete user');
    }
  };

  const submitAdminSpace = async (event) => {
    event.preventDefault();
    resetMessages();

    const payload = {
      title: adminSpaceForm.title.trim(),
      listing_mode: adminSpaceForm.listing_mode,
      guarantee_level: adminSpaceForm.guarantee_level,
      confidence_score: adminSpaceForm.confidence_score === '' ? null : Number(adminSpaceForm.confidence_score),
      property_type: adminSpaceForm.property_type.trim() || null,
      business_type: adminSpaceForm.business_type || null,
      latitude: Number(adminSpaceForm.latitude),
      longitude: Number(adminSpaceForm.longitude),
      address_text: adminSpaceForm.address_text.trim() || null,
      price_min: adminSpaceForm.price_min === '' ? null : Number(adminSpaceForm.price_min),
      price_max: adminSpaceForm.price_max === '' ? null : Number(adminSpaceForm.price_max),
      source_note: adminSpaceForm.source_note.trim() || null,
      contact_info: adminSpaceForm.contact_info.trim() || null,
      notes: adminSpaceForm.notes.trim() || null,
      verified_at: adminSpaceForm.verified_at || null,
      expires_at: adminSpaceForm.expires_at || null,
      is_active: Boolean(adminSpaceForm.is_active)
    };

    if (!payload.title || Number.isNaN(payload.latitude) || Number.isNaN(payload.longitude)) {
      setErrorMessage('Title and valid coordinates are required for admin space submission.');
      return;
    }

    if (payload.confidence_score !== null && (payload.confidence_score < 0 || payload.confidence_score > 100)) {
      setErrorMessage('Confidence score must be between 0 and 100.');
      return;
    }

    try {
      const response = await fetch(apiUrl('/admin/spaces/admin-submissions'), {
        method: 'POST',
        headers,
        body: JSON.stringify(payload)
      });
      const data = await response.json();
      if (!response.ok) throw new Error(data.detail || 'Unable to save admin space submission');

      setSuccessMessage('Admin space submission created.');
      setAdminSpaceForm(defaultAdminSpaceForm);
      await loadSpaces(spaceFilterStatus);
    } catch (error) {
      setErrorMessage(error.message || 'Unable to save admin space submission');
    }
  };

  const reviewUserSubmission = async (submissionId, status) => {
    resetMessages();
    try {
      const response = await fetch(apiUrl(`/admin/spaces/user-submissions/${submissionId}/status`), {
        method: 'PUT',
        headers,
        body: JSON.stringify({ status })
      });
      const data = await response.json();
      if (!response.ok) throw new Error(data.detail || 'Unable to update submission status');

      setSuccessMessage(`Submission ${status}.`);
      await loadSpaces(spaceFilterStatus);
    } catch (error) {
      setErrorMessage(error.message || 'Unable to update submission status');
    }
  };

  return (
    <div className="profile-page page-enter admin-page">
      <div className="profile-card fade-in" style={{ textAlign: 'left' }}>
        <h2 className="profile-name" style={{ marginBottom: '6px' }}>Admin Panel</h2>
        <p className="profile-email">Manage users, custom MSMEs, and space submission workflows.</p>
      </div>

      {errorMessage && <div className="error-alert mt-4">{errorMessage}</div>}
      {successMessage && <div className="admin-success-alert mt-4">{successMessage}</div>}

      <div className="admin-tabs mt-6" style={{ gridTemplateColumns: 'repeat(3, minmax(0, 1fr))' }}>
        <button type="button" className={`admin-tab-btn ${activeTab === 'msmes' ? 'active' : ''}`} onClick={() => setActiveTab('msmes')}>
          Custom MSMEs
        </button>
        <button type="button" className={`admin-tab-btn ${activeTab === 'users' ? 'active' : ''}`} onClick={() => setActiveTab('users')}>
          Users
        </button>
        <button type="button" className={`admin-tab-btn ${activeTab === 'spaces' ? 'active' : ''}`} onClick={() => setActiveTab('spaces')}>
          Space Submissions
        </button>
      </div>

      {activeTab === 'msmes' && (
        <>
          <div className="data-card mt-6 admin-card">
            <h3 className="section-heading" style={{ marginBottom: '12px' }}>{editingMsmeId ? 'Edit Custom MSME' : 'Add Custom MSME'}</h3>
            <form onSubmit={submitMsme}>
              <div className="input-group">
                <label>Name</label>
                <input value={msmeForm.name} onChange={(e) => setMsmeForm((c) => ({ ...c, name: e.target.value }))} />
              </div>
              <div className="input-group">
                <label>Business Type Key</label>
                <select className="app-select" value={msmeForm.business_type} onChange={(e) => setMsmeForm((c) => ({ ...c, business_type: e.target.value }))}>
                  <option value="">Choose a business type...</option>
                  {BUSINESS_TYPE_OPTIONS.map((option) => (
                    <option key={option.value} value={option.value}>{option.label}</option>
                  ))}
                </select>
              </div>
              <div className="input-group">
                <label>Latitude</label>
                <input value={msmeForm.latitude} onChange={(e) => setMsmeForm((c) => ({ ...c, latitude: e.target.value }))} />
              </div>
              <div className="input-group">
                <label>Longitude</label>
                <input value={msmeForm.longitude} onChange={(e) => setMsmeForm((c) => ({ ...c, longitude: e.target.value }))} />
              </div>
              <button type="submit" className="primary-btn">{editingMsmeId ? 'Update MSME' : 'Create MSME'}</button>
              {editingMsmeId && (
                <button
                  type="button"
                  className="secondary-btn"
                  onClick={() => {
                    setEditingMsmeId(null);
                    setMsmeForm(defaultMsmeForm);
                  }}
                >
                  Cancel Edit
                </button>
              )}
            </form>
          </div>

          <div className="data-card admin-card admin-tools-card">
            <div className="admin-tools-grid">
              <div className="input-group" style={{ marginBottom: 0 }}>
                <label>Search MSME</label>
                <input value={msmeSearchTerm} onChange={(e) => setMsmeSearchTerm(e.target.value)} placeholder="Search name or business type..." />
              </div>
              <div className="input-group" style={{ marginBottom: 0 }}>
                <label>Sort By</label>
                <select className="app-select" value={msmeSortBy} onChange={(e) => setMsmeSortBy(e.target.value)}>
                  <option value="type-asc">Business Type (A-Z)</option>
                  <option value="type-desc">Business Type (Z-A)</option>
                  <option value="name-asc">Name (A-Z)</option>
                  <option value="name-desc">Name (Z-A)</option>
                </select>
              </div>
            </div>
          </div>

          <div className="history-list mt-6">
            {msmeLoading && <div className="data-card">Loading custom MSMEs...</div>}
            {!msmeLoading && filteredCustomMsmes.map((item) => (
              <div className="data-card history-card" key={item.id}>
                <div className="history-card-top">
                  <div>
                    <h4 className="history-title">{item.name}</h4>
                    <p className="history-meta">Type: {item.business_type}</p>
                    <p className="history-meta">Lat: {Number(item.latitude).toFixed(6)} | Lon: {Number(item.longitude).toFixed(6)}</p>
                  </div>
                </div>
                <div className="admin-actions-row">
                  <button className="admin-action-btn admin-action-btn-edit" onClick={() => startEditMsme(item)}>Edit</button>
                  <button className="admin-action-btn admin-action-btn-delete" onClick={() => deleteMsme(item)}>Delete</button>
                </div>
              </div>
            ))}
            {!msmeLoading && filteredCustomMsmes.length === 0 && (
              <div className="data-card">No MSMEs match your search.</div>
            )}
          </div>
        </>
      )}

      {activeTab === 'users' && (
        <div className="history-list mt-6">
          {userLoading && <div className="data-card">Loading users...</div>}
          {!userLoading && users.map((user) => {
            const editing = editingUserId === user.user_id;
            return (
              <div className="data-card history-card" key={user.user_id}>
                {!editing ? (
                  <>
                    <div className="history-card-top">
                      <div>
                        <h4 className="history-title">{user.full_name || 'Unnamed User'}</h4>
                        <p className="history-meta">{user.email}</p>
                        <p className="history-meta">User ID: {user.user_id}</p>
                      </div>
                    </div>
                    <div className="admin-actions-row">
                      <button className="admin-action-btn admin-action-btn-edit" onClick={() => startEditUser(user)}>Edit</button>
                      <button className="admin-action-btn admin-action-btn-delete" onClick={() => deleteUser(user)}>Delete</button>
                    </div>
                  </>
                ) : (
                  <div>
                    <div className="input-group">
                      <label>Full Name</label>
                      <input value={userForm.full_name} onChange={(e) => setUserForm((c) => ({ ...c, full_name: e.target.value }))} />
                    </div>
                    <div className="input-group">
                      <label>Email</label>
                      <input value={userForm.email} onChange={(e) => setUserForm((c) => ({ ...c, email: e.target.value }))} />
                    </div>
                    <div className="input-group">
                      <label>Cellphone Number</label>
                      <input value={userForm.cellphone_number} onChange={(e) => setUserForm((c) => ({ ...c, cellphone_number: e.target.value }))} />
                    </div>
                    <div className="input-group">
                      <label>Address</label>
                      <input value={userForm.address} onChange={(e) => setUserForm((c) => ({ ...c, address: e.target.value }))} />
                    </div>
                    <div className="input-group">
                      <label>Birthday</label>
                      <input type="date" value={userForm.birthday} onChange={(e) => setUserForm((c) => ({ ...c, birthday: e.target.value }))} />
                    </div>
                    <div className="input-group">
                      <label>Age</label>
                      <input value={userForm.age} onChange={(e) => setUserForm((c) => ({ ...c, age: e.target.value }))} />
                    </div>
                    <div className="input-group">
                      <label>Primary Business</label>
                      <input value={userForm.primary_business} onChange={(e) => setUserForm((c) => ({ ...c, primary_business: e.target.value }))} />
                    </div>
                    <div className="history-actions-row">
                      <button className="primary-btn history-open-btn" onClick={saveUser}>Save</button>
                      <button className="secondary-btn" onClick={cancelEditUser}>Cancel</button>
                    </div>
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}

      {activeTab === 'spaces' && (
        <>
          <div className="data-card mt-6 admin-card">
            <h3 className="section-heading" style={{ marginBottom: '12px' }}>Add Admin Space Submission</h3>
            <form onSubmit={submitAdminSpace}>
              <div className="input-group">
                <label>Title <span className="required-indicator">*</span></label>
                <input required value={adminSpaceForm.title} onChange={(e) => setAdminSpaceForm((c) => ({ ...c, title: e.target.value }))} />
              </div>

              <div className="admin-tools-grid" style={{ marginBottom: 12 }}>
                <div className="input-group" style={{ marginBottom: 0 }}>
                  <label>Listing Mode</label>
                  <select className="app-select" value={adminSpaceForm.listing_mode} onChange={(e) => setAdminSpaceForm((c) => ({ ...c, listing_mode: e.target.value }))}>
                    <option value="rent">For Rent</option>
                    <option value="buy">For Sale</option>
                  </select>
                </div>
                <div className="input-group" style={{ marginBottom: 0 }}>
                  <label>Guarantee Level</label>
                  <select className="app-select" value={adminSpaceForm.guarantee_level} onChange={(e) => setAdminSpaceForm((c) => ({ ...c, guarantee_level: e.target.value }))}>
                    <option value="potential">Potential</option>
                    <option value="guaranteed">Guaranteed</option>
                  </select>
                </div>
              </div>

              <div className="admin-tools-grid" style={{ marginBottom: 12 }}>
                <div className="input-group" style={{ marginBottom: 0 }}>
                  <label>Business Type</label>
                  <select className="app-select" value={adminSpaceForm.business_type} onChange={(e) => setAdminSpaceForm((c) => ({ ...c, business_type: e.target.value }))}>
                    <option value="">Not specific</option>
                    {BUSINESS_TYPE_OPTIONS.map((option) => (
                      <option key={option.value} value={option.value}>{option.label}</option>
                    ))}
                  </select>
                </div>
                <div className="input-group" style={{ marginBottom: 0 }}>
                  <label>Confidence (0-100)</label>
                  <input
                    value={adminSpaceForm.confidence_score}
                    onChange={(e) => setAdminSpaceForm((c) => ({ ...c, confidence_score: e.target.value }))}
                    placeholder="85"
                    disabled={adminSpaceForm.guarantee_level === 'guaranteed'}
                  />
                </div>
              </div>

              <div className="admin-tools-grid" style={{ marginBottom: 12 }}>
                <div className="input-group" style={{ marginBottom: 0 }}>
                  <label>Latitude <span className="required-indicator">*</span></label>
                  <input required type="text" inputMode="decimal" step="any" value={adminSpaceForm.latitude} onChange={(e) => setAdminSpaceForm((c) => ({ ...c, latitude: e.target.value }))} onPaste={handleCoordinatePaste(setAdminSpaceForm)} placeholder="7.310967506654152, 125.6853653454886" />
                </div>
                <div className="input-group" style={{ marginBottom: 0 }}>
                  <label>Longitude <span className="required-indicator">*</span></label>
                  <input required type="text" inputMode="decimal" step="any" value={adminSpaceForm.longitude} onChange={(e) => setAdminSpaceForm((c) => ({ ...c, longitude: e.target.value }))} onPaste={handleCoordinatePaste(setAdminSpaceForm)} />
                </div>
              </div>

              <div className="input-group">
                <label>Property Type</label>
                <input value={adminSpaceForm.property_type} onChange={(e) => setAdminSpaceForm((c) => ({ ...c, property_type: e.target.value }))} placeholder="Storefront, Lot, Stall" />
              </div>

              <div className="input-group">
                <label>Address</label>
                <input value={adminSpaceForm.address_text} onChange={(e) => setAdminSpaceForm((c) => ({ ...c, address_text: e.target.value }))} placeholder="Address or landmark" />
              </div>

              <div className="admin-tools-grid" style={{ marginBottom: 12 }}>
                <div className="input-group" style={{ marginBottom: 0 }}>
                  <label>Min Price (PHP)</label>
                  <input value={adminSpaceForm.price_min} onChange={(e) => setAdminSpaceForm((c) => ({ ...c, price_min: e.target.value }))} />
                </div>
                <div className="input-group" style={{ marginBottom: 0 }}>
                  <label>Max Price (PHP)</label>
                  <input value={adminSpaceForm.price_max} onChange={(e) => setAdminSpaceForm((c) => ({ ...c, price_max: e.target.value }))} />
                </div>
              </div>

              <div className="input-group">
                <label>Contact Info</label>
                <input value={adminSpaceForm.contact_info} onChange={(e) => setAdminSpaceForm((c) => ({ ...c, contact_info: e.target.value }))} />
              </div>

              <div className="input-group">
                <label>Source Note</label>
                <input value={adminSpaceForm.source_note} onChange={(e) => setAdminSpaceForm((c) => ({ ...c, source_note: e.target.value }))} placeholder="Field survey, broker tip, etc." />
              </div>

              <div className="input-group">
                <label>Notes</label>
                <textarea value={adminSpaceForm.notes} onChange={(e) => setAdminSpaceForm((c) => ({ ...c, notes: e.target.value }))} rows={3} />
              </div>

              <div className="admin-tools-grid" style={{ marginBottom: 12 }}>
                <div className="input-group" style={{ marginBottom: 0 }}>
                  <label>Verified Date</label>
                  <input type="date" value={adminSpaceForm.verified_at} onChange={(e) => setAdminSpaceForm((c) => ({ ...c, verified_at: e.target.value }))} />
                  <p className="admin-field-help">When the listing was last confirmed as real and available.</p>
                </div>
                <div className="input-group" style={{ marginBottom: 0 }}>
                  <label>Expires Date</label>
                  <input type="date" value={adminSpaceForm.expires_at} onChange={(e) => setAdminSpaceForm((c) => ({ ...c, expires_at: e.target.value }))} />
                  <p className="admin-field-help">After this date, the listing should be rechecked or marked inactive.</p>
                </div>
              </div>

              <div className="input-group">
                <label>
                  <input type="checkbox" checked={adminSpaceForm.is_active} onChange={(e) => setAdminSpaceForm((c) => ({ ...c, is_active: e.target.checked }))} style={{ marginRight: 8 }} />
                  Active on map
                </label>
              </div>

              <button type="submit" className="primary-btn">Create Admin Space Entry</button>
            </form>
          </div>

          <div className="data-card admin-card admin-tools-card">
            <div className="admin-tools-grid">
              <div className="input-group" style={{ marginBottom: 0 }}>
                <label>User Submission Filter</label>
                <select className="app-select" value={spaceFilterStatus} onChange={(e) => setSpaceFilterStatus(e.target.value)}>
                  <option value="pending">Pending</option>
                  <option value="approved">Approved</option>
                  <option value="rejected">Rejected</option>
                  <option value="archived">Archived</option>
                  <option value="all">All</option>
                </select>
              </div>
              <div className="input-group" style={{ marginBottom: 0 }}>
                <label>Refresh</label>
                <button type="button" className="secondary-btn" onClick={() => loadSpaces(spaceFilterStatus)}>Reload Space Data</button>
              </div>
            </div>
          </div>

          <div className="history-list mt-6">
            <div className="data-card admin-card">
              <h3 className="section-heading" style={{ marginBottom: 12 }}>User Submissions ({spaceFilterStatus})</h3>

              {spaceLoading && <p className="history-meta">Loading submissions...</p>}
              {!spaceLoading && userSpaceSubmissions.length === 0 && <p className="history-meta">No user submissions in this filter.</p>}

              {!spaceLoading && userSpaceSubmissions.map((item) => {
                const statusMeta = getSubmissionStatusMeta(item.status);
                const statusClass = `admin-submission-card ${statusMeta.className}`;
                const normalizedStatus = String(item.status || '').toLowerCase();

                return (
                <div key={item.id} className={statusClass} style={{ marginTop: 12 }}>
                  <div className="history-card-top">
                    <div>
                      <h4 className="history-title">{item.title}</h4>
                      <div className="admin-submission-head">
                        <span className={`submission-status-pill ${statusMeta.className}`}>{statusMeta.label}</span>
                        <p className="history-meta">Mode: {getListingModeLabel(item.listing_mode)} | Guarantee: {item.guarantee_level}</p>
                      </div>
                      <p className="history-meta">Lat: {Number(item.latitude).toFixed(6)} | Lon: {Number(item.longitude).toFixed(6)}</p>
                      <p className="history-meta">Business: {getBusinessTypeLabel(item.business_type)} | Price: {formatPesoRange(item.price_min, item.price_max)}</p>
                      {item.address_text && <p className="history-meta">Address: {item.address_text}</p>}
                      {item.contact_info && <p className="history-meta">Contact: {item.contact_info}</p>}
                      <p className="admin-submission-note">{statusMeta.message}</p>
                    </div>
                  </div>

                  {normalizedStatus === 'pending' ? (
                    <div className="admin-actions-row">
                      <button className="admin-action-btn admin-action-btn-edit" onClick={() => reviewUserSubmission(item.id, 'approved')}>Approve</button>
                      <button className="admin-action-btn" style={{ border: '1px solid rgba(250,204,21,0.35)', background: 'rgba(250,204,21,0.12)', color: '#facc15' }} onClick={() => reviewUserSubmission(item.id, 'rejected')}>Reject</button>
                      <button className="admin-action-btn admin-action-btn-delete" onClick={() => reviewUserSubmission(item.id, 'archived')}>Archive</button>
                    </div>
                  ) : normalizedStatus === 'approved' ? (
                    <div className="admin-actions-row">
                      <button className="admin-action-btn" style={{ border: '1px solid rgba(250,204,21,0.35)', background: 'rgba(250,204,21,0.12)', color: '#facc15' }} onClick={() => reviewUserSubmission(item.id, 'rejected')}>Move to Rejected</button>
                      <button className="admin-action-btn admin-action-btn-delete" onClick={() => reviewUserSubmission(item.id, 'archived')}>Archive</button>
                    </div>
                  ) : (
                    <div className="admin-actions-row">
                      <button className="admin-action-btn admin-action-btn-edit" onClick={() => reviewUserSubmission(item.id, 'approved')}>Mark Approved</button>
                      <button className="admin-action-btn admin-action-btn-delete" onClick={() => reviewUserSubmission(item.id, 'archived')}>Archive</button>
                    </div>
                  )}
                </div>
              )})}
            </div>

            <div className="data-card admin-card">
              <h3 className="section-heading" style={{ marginBottom: 12 }}>Admin Space Entries</h3>

              {spaceLoading && <p className="history-meta">Loading admin entries...</p>}
              {!spaceLoading && adminSpaceSubmissions.length === 0 && <p className="history-meta">No admin entries yet.</p>}

              {!spaceLoading && adminSpaceSubmissions.map((item) => (
                <div key={item.id} className="history-card" style={{ marginTop: 12 }}>
                  <div className="history-card-top">
                    <div>
                      <h4 className="history-title">{item.title}</h4>
                      <p className="history-meta">Mode: {getListingModeLabel(item.listing_mode)} | Guarantee: {item.guarantee_level} | Active: {item.is_active ? 'Yes' : 'No'}</p>
                      <p className="history-meta">Lat: {Number(item.latitude).toFixed(6)} | Lon: {Number(item.longitude).toFixed(6)}</p>
                      <p className="history-meta">Business: {getBusinessTypeLabel(item.business_type)} | Price: {formatPesoRange(item.price_min, item.price_max)}</p>
                      <p className="history-meta">Confidence: {item.confidence_score ?? '-'} | Expires: {item.expires_at ? String(item.expires_at).slice(0, 10) : '-'}</p>
                    </div>
                  </div>
                </div>
              ))}
            </div>
          </div>
        </>
      )}
    </div>
  );
}
