import React, { useCallback, useEffect, useState } from 'react';
import AdminLayout from '../components/admin/AdminLayout';
import { DEFAULT_ADMIN_TAB, isAdminTab } from '../components/admin/adminNav';
import { Notice } from '../components/admin/ui/AdminUi';
import useAdminApi from '../components/admin/ui/useAdminApi';
import useIsDesktop from '../utils/useIsDesktop';
import MapLayersPage from './admin/MapLayersPage';
import MsmesPage from './admin/MsmesPage';
import SpacesPage from './admin/SpacesPage';
import UsersPage from './admin/UsersPage';

const SUCCESS_NOTICE_MS = 4000;

// The admin console: layout (sidebar on desktop, tab bar on mobile), one shared
// notice area, the pending-spaces badge, and the page for the active tab.
// Each page lives in pages/admin/ and loads its own data.
export default function AdminPanel({ adminSession, activeTab, onActiveTabChange, theme, toggleTheme, onLogout }) {
  const isDesktop = useIsDesktop();
  const api = useAdminApi(adminSession?.token);
  const [notice, setNotice] = useState(null);
  const [pendingCount, setPendingCount] = useState(0);

  const notify = useCallback((tone, message) => {
    setNotice({ tone, message, id: Date.now() });
  }, []);

  useEffect(() => {
    if (notice?.tone !== 'success') return undefined;
    const timer = setTimeout(() => setNotice(null), SUCCESS_NOTICE_MS);
    return () => clearTimeout(timer);
  }, [notice]);

  const refreshPendingCount = useCallback(async () => {
    try {
      const data = await api('/admin/spaces/user-submissions?status=pending');
      setPendingCount(Array.isArray(data?.submissions) ? data.submissions.length : 0);
    } catch {
      // The badge is a convenience; the Spaces page reports real load errors.
    }
  }, [api]);

  useEffect(() => {
    let cancelled = false;
    api('/admin/spaces/user-submissions?status=pending')
      .then((data) => {
        if (!cancelled) setPendingCount(Array.isArray(data?.submissions) ? data.submissions.length : 0);
      })
      .catch(() => {});
    return () => {
      cancelled = true;
    };
  }, [api]);

  const tab = isAdminTab(activeTab) ? activeTab : DEFAULT_ADMIN_TAB;
  const changeTab = (nextTab) => {
    setNotice(null);
    onActiveTabChange(nextTab);
  };

  const pageProps = { api, notify, isDesktop };

  return (
    <AdminLayout
      activeTab={tab}
      onTabChange={changeTab}
      pendingCount={pendingCount}
      adminEmail={adminSession?.email}
      theme={theme}
      toggleTheme={toggleTheme}
      onLogout={onLogout}
    >
      {notice && (
        <Notice key={notice.id} tone={notice.tone} onDismiss={() => setNotice(null)}>
          {notice.message}
        </Notice>
      )}
      {tab === 'msmes' && <MsmesPage {...pageProps} />}
      {tab === 'users' && <UsersPage {...pageProps} />}
      {tab === 'spaces' && <SpacesPage {...pageProps} pendingCount={pendingCount} onPendingChanged={refreshPendingCount} />}
      {tab === 'flood' && <MapLayersPage token={adminSession?.token} />}
    </AdminLayout>
  );
}
