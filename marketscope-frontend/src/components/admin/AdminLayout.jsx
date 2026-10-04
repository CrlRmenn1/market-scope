import React, { useState } from 'react';
import { ArrowRightOnRectangleIcon, MoonIcon, SunIcon } from '@heroicons/react/24/outline';
import BrandMark from '../layout/BrandMark';
import Header from '../layout/Header';
import AdminNavbar from '../layout/AdminNavbar';
import Modal from '../common/Modal';
import useIsDesktop from '../../utils/useIsDesktop';
import { ADMIN_NAV_ITEMS } from './adminNav';

function LogoutDialog({ isOpen, onCancel, onConfirm }) {
  return (
    <Modal
      isOpen={isOpen}
      onClose={onCancel}
      variant="center"
      overlayClassName="history-confirm-overlay"
      panelClassName="history-confirm-modal"
      ariaLabelledBy="admin-logout-title"
    >
      <h3 id="admin-logout-title" className="text-xl font-semibold text-[var(--text-main)]">Log out of the admin console?</h3>
      <p className="mt-2 text-sm leading-6 text-[var(--text-muted)]">You will need the admin password to sign in again.</p>
      <div className="mt-5 flex flex-col gap-3 sm:flex-row sm:justify-end">
        <button
          type="button"
          className="inline-flex min-h-[44px] cursor-pointer items-center justify-center rounded-xl border border-[var(--border-color)] bg-[var(--bg-sheet)] px-4 text-sm font-medium text-[var(--text-main)] hover:bg-[var(--accent-hover)]"
          onClick={onCancel}
        >
          Cancel
        </button>
        <button
          type="button"
          className="inline-flex min-h-[44px] cursor-pointer items-center justify-center gap-2 rounded-xl bg-[var(--trend-down)] px-4 text-sm font-semibold text-white hover:opacity-90"
          onClick={onConfirm}
        >
          <ArrowRightOnRectangleIcon className="h-4 w-4" aria-hidden="true" /> Log out
        </button>
      </div>
    </Modal>
  );
}

function Sidebar({ activeTab, onTabChange, pendingCount, adminEmail, theme, toggleTheme, onRequestLogout }) {
  const initial = (adminEmail || 'A').charAt(0).toUpperCase();
  const isDark = theme === 'dark';

  return (
    <aside className="admin-sidebar flex w-64 flex-none flex-col border-r border-[var(--border-color)] bg-[var(--bg-sheet)]">
      <div className="brand-wrapper px-5 py-6">
        <button type="button" className="brand-home-btn" onClick={() => onTabChange(ADMIN_NAV_ITEMS[0].id)} aria-label="Go to the first admin page">
          <BrandMark />
        </button>
        <div className="min-w-0">
          <p className="app-title">
            Market<span className="highlight-text">Scope</span>
          </p>
          <p className="text-xs text-[var(--text-muted)]">Admin console</p>
        </div>
      </div>

      <nav aria-label="Admin sections" className="flex-1 space-y-1 px-3">
        {ADMIN_NAV_ITEMS.map((item) => {
          const Icon = item.icon;
          const isActive = activeTab === item.id;
          const badge = item.id === 'spaces' && pendingCount > 0 ? pendingCount : null;
          return (
            <button
              key={item.id}
              type="button"
              onClick={() => onTabChange(item.id)}
              aria-current={isActive ? 'page' : undefined}
              className={`admin-side-item ${isActive ? 'is-active' : ''}`}
            >
              <Icon className="h-5 w-5 flex-none" aria-hidden="true" />
              <span className="flex-1 text-left">{item.label}</span>
              {badge && (
                <span className="rounded-full bg-[var(--btn-primary-bg)] px-2 py-0.5 text-xs font-bold tabular-nums text-[var(--btn-primary-text)]" aria-label={`${badge} pending`}>
                  {badge}
                </span>
              )}
            </button>
          );
        })}
      </nav>

      <div className="space-y-1 border-t border-[var(--border-color)] p-3">
        <div className="flex items-center gap-3 px-3 py-2">
          <span className="inline-flex h-8 w-8 flex-none items-center justify-center rounded-full bg-[var(--accent-hover)] text-sm font-semibold text-[var(--accent)]" aria-hidden="true">
            {initial}
          </span>
          <div className="min-w-0">
            <p className="text-xs text-[var(--text-muted)]">Signed in as</p>
            <p className="truncate text-sm font-medium text-[var(--text-main)]" title={adminEmail}>{adminEmail || 'Admin'}</p>
          </div>
        </div>
        <button type="button" className="admin-side-item" onClick={toggleTheme}>
          {isDark ? <SunIcon className="h-5 w-5" aria-hidden="true" /> : <MoonIcon className="h-5 w-5" aria-hidden="true" />}
          <span>{isDark ? 'Light mode' : 'Dark mode'}</span>
        </button>
        <button type="button" className="admin-side-item admin-side-item--danger" onClick={onRequestLogout}>
          <ArrowRightOnRectangleIcon className="h-5 w-5" aria-hidden="true" />
          <span>Log out</span>
        </button>
      </div>
    </aside>
  );
}

// Desktop (>= 1024px): fixed sidebar + scrolling content area.
// Mobile: the app's top Header + a bottom tab bar, content stacked in between.
export default function AdminLayout({ activeTab, onTabChange, pendingCount, adminEmail, theme, toggleTheme, onLogout, children }) {
  const isDesktop = useIsDesktop();
  const [showLogoutConfirm, setShowLogoutConfirm] = useState(false);

  if (isDesktop) {
    return (
      <div className="admin-console flex h-[100svh] w-full overflow-hidden bg-[var(--bg-app)] text-[var(--text-main)]">
        <a href="#admin-main" className="sr-only focus:not-sr-only focus:absolute focus:left-4 focus:top-4 focus:z-50 focus:rounded-lg focus:bg-[var(--bg-sheet)] focus:px-3 focus:py-2">
          Skip to content
        </a>
        <Sidebar
          activeTab={activeTab}
          onTabChange={onTabChange}
          pendingCount={pendingCount}
          adminEmail={adminEmail}
          theme={theme}
          toggleTheme={toggleTheme}
          onRequestLogout={() => setShowLogoutConfirm(true)}
        />
        <main id="admin-main" className="min-w-0 flex-1 overflow-y-auto">
          <div className="mx-auto w-full max-w-[1200px] px-8 py-8">{children}</div>
        </main>
        <LogoutDialog
          isOpen={showLogoutConfirm}
          onCancel={() => setShowLogoutConfirm(false)}
          onConfirm={() => {
            setShowLogoutConfirm(false);
            onLogout();
          }}
        />
      </div>
    );
  }

  const adminName = adminEmail ? `Admin (${adminEmail.split('@')[0]})` : 'Admin';
  return (
    <div className="admin-console relative flex h-[100svh] w-full flex-col overflow-hidden bg-[var(--bg-app)] text-[var(--text-main)]">
      <Header
        theme={theme}
        toggleTheme={toggleTheme}
        onLogout={onLogout}
        onGoHome={() => onTabChange(ADMIN_NAV_ITEMS[0].id)}
        userName={adminName}
        userAvatarUrl={null}
        onOpenSpaceSubmission={null}
      />
      <main id="admin-main" className="min-h-0 flex-1 overflow-y-auto overflow-x-hidden pb-28 pt-[88px]">
        <div className="px-4">{children}</div>
      </main>
      <AdminNavbar activeTab={activeTab} onChange={onTabChange} pendingCount={pendingCount} />
    </div>
  );
}
