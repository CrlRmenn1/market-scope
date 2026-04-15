import React, { useEffect, useMemo, useState } from 'react';
import { apiUrl } from '../api';

const defaultMsmeForm = {
  name: '',
  business_type: '',
  latitude: '',
  longitude: ''
};

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

export default function AdminPanel({ adminSession, onAdminLogout }) {
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

  const [errorMessage, setErrorMessage] = useState('');
  const [successMessage, setSuccessMessage] = useState('');

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
      if (msmeSortBy === 'name-asc') {
        return aName.localeCompare(bName);
      }
      if (msmeSortBy === 'name-desc') {
        return bName.localeCompare(aName);
      }

      if (aType !== bType) return aType.localeCompare(bType);
      return aName.localeCompare(bName);
    });

    return items;
  }, [customMsmes, msmeSearchTerm, msmeSortBy]);

  const headers = useMemo(() => ({
    'Content-Type': 'application/json',
    'x-admin-token': token || ''
  }), [token]);

  const resetMessages = () => {
    setErrorMessage('');
    setSuccessMessage('');
  };

  const loadCustomMsmes = async () => {
    if (!token) return;
    setMsmeLoading(true);
    resetMessages();
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
    resetMessages();
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

  useEffect(() => {
    loadCustomMsmes();
    loadUsers();
  }, [token]);

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
    const url = isEditing
      ? apiUrl(`/admin/custom-msmes/${editingMsmeId}`)
      : apiUrl('/admin/custom-msmes');
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

  return (
    <div className="profile-page page-enter admin-page">
      <div className="profile-card fade-in" style={{ textAlign: 'left' }}>
        <h2 className="profile-name" style={{ marginBottom: '6px' }}>Admin Panel</h2>
        <p className="profile-email">Manage users and custom MSME records without editing backend code.</p>
        <button className="edit-btn mt-4" onClick={onAdminLogout}>Log Out Admin</button>
      </div>

      {errorMessage && <div className="error-alert mt-4">{errorMessage}</div>}
      {successMessage && <div className="admin-success-alert mt-4">{successMessage}</div>}

      <div className="admin-tabs mt-6">
        <button
          type="button"
          className={`admin-tab-btn ${activeTab === 'msmes' ? 'active' : ''}`}
          onClick={() => setActiveTab('msmes')}
        >
          Custom MSMEs
        </button>
        <button
          type="button"
          className={`admin-tab-btn ${activeTab === 'users' ? 'active' : ''}`}
          onClick={() => setActiveTab('users')}
        >
          Users
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
                <input value={msmeForm.business_type} onChange={(e) => setMsmeForm((c) => ({ ...c, business_type: e.target.value }))} placeholder="coffee, pharmacy, bakery..." />
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
                <input
                  value={msmeSearchTerm}
                  onChange={(e) => setMsmeSearchTerm(e.target.value)}
                  placeholder="Search name or business type..."
                />
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
    </div>
  );
}
