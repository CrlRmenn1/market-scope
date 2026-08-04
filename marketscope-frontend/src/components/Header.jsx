import React, { useState } from 'react';
import { createPortal } from 'react-dom';
import {
  Cog8ToothIcon,
  SunIcon,
  MoonIcon,
  MapPinIcon,
  AcademicCapIcon,
  ArrowRightOnRectangleIcon
} from '@heroicons/react/24/solid';

export default function Header({ theme, toggleTheme, onLogout, onGoHome, userName, userAvatarUrl, onOpenSpaceSubmission, onStartTour }) {
  const [isDropdownOpen, setIsDropdownOpen] = useState(false);
  const [showLogoutConfirm, setShowLogoutConfirm] = useState(false);

  // Get first letter of name for a fallback avatar
  const userInitial = userName ? userName.charAt(0).toUpperCase() : 'G';

  const logoutConfirmDialog = showLogoutConfirm ? (
    <div className="history-confirm-overlay" role="presentation" onClick={() => setShowLogoutConfirm(false)}>
      <div
        className="history-confirm-modal"
        role="dialog"
        aria-modal="true"
        aria-labelledby="logout-confirm-title"
        onClick={(event) => event.stopPropagation()}
      >
        <p className="history-confirm-eyebrow text-[0.72rem] font-semibold uppercase tracking-[0.08em] text-[var(--trend-down)]">Sign out</p>
        <h3 id="logout-confirm-title" className="history-confirm-title mt-2 text-xl font-semibold text-[var(--text-main)]">Log out of MarketScope?</h3>
        <p className="history-confirm-text mt-3 text-sm leading-6 text-[var(--text-muted)]">
          Your saved analyses stay in your account. You will need to sign in again to run new scans.
        </p>
        <div className="history-confirm-actions mt-5 flex flex-col gap-3 sm:flex-row">
          <button
            type="button"
            className="inline-flex min-h-[44px] items-center justify-center rounded-xl border border-[var(--border-color)] bg-[var(--bg-sheet)] px-4 py-2.5 text-sm font-medium text-[var(--text-main)] transition hover:border-[var(--border-strong)] hover:bg-[var(--accent-hover)]"
            onClick={() => setShowLogoutConfirm(false)}
          >
            Cancel
          </button>
          <button
            type="button"
            className="inline-flex min-h-[44px] items-center justify-center gap-2 rounded-xl bg-[var(--trend-down)] px-4 py-2.5 text-sm font-semibold text-white transition hover:opacity-90"
            onClick={() => {
              setShowLogoutConfirm(false);
              if (onLogout) onLogout();
            }}
          >
            <ArrowRightOnRectangleIcon className="h-4 w-4" aria-hidden="true" /> Log Out
          </button>
        </div>
      </div>
    </div>
  ) : null;

  return (
    <header className="app-header">
      <div className="brand-wrapper">
        <button className="brand-home-btn" onClick={onGoHome} aria-label="Go to Home screen">
          <div className="brand-mark" aria-hidden="true">
            <div className="lens-left" />
            <div className="lens-center">
              <div className="lens-reflection" />
            </div>
            <div className="lens-right" />
          </div>
        </button>
        <h1 className="app-title">
          Market<span className="highlight-text">Scope</span>
        </h1>
      </div>

      {/* SETTINGS MENU (Unified with Name) */}
      <div className="settings-wrapper">
        <button
          onClick={() => setIsDropdownOpen(!isDropdownOpen)}
          className={`user-settings-btn ${isDropdownOpen ? 'active' : ''}`}
        >
          {/* Small Avatar Circle */}
          {userAvatarUrl ? (
            <img src={userAvatarUrl} alt="Profile" className="user-avatar-tiny user-avatar-image" />
          ) : (
            <div className="user-avatar-tiny">{userInitial}</div>
          )}

          {/* The Name */}
          <span className="settings-user-name">{userName || 'Guest'}</span>

          {/* The Gear Icon */}
          <Cog8ToothIcon className={`gear-icon-small ${isDropdownOpen ? 'open' : ''}`} />
        </button>

        {isDropdownOpen && (
          <div className="settings-dropdown">
            <div className="dropdown-menu">
              <button
                onClick={() => {
                  toggleTheme();
                  setIsDropdownOpen(false);
                }}
                className="dropdown-item"
              >
                {theme === 'light' ? (
                  <><MoonIcon className="dropdown-icon" /> Dark Mode</>
                ) : (
                  <><SunIcon className="dropdown-icon" /> Light Mode</>
                )}
              </button>

              {onOpenSpaceSubmission && (
                <button
                  onClick={() => {
                    setIsDropdownOpen(false);
                    onOpenSpaceSubmission();
                  }}
                  className="dropdown-item"
                >
                  <MapPinIcon className="dropdown-icon" /> Submit Space Listing
                </button>
              )}

              {onStartTour && (
                <button
                  onClick={() => {
                    setIsDropdownOpen(false);
                    onStartTour();
                  }}
                  className="dropdown-item"
                >
                  <AcademicCapIcon className="dropdown-icon" /> Quick Tour
                </button>
              )}

              <div className="dropdown-divider"></div>

              <button
                onClick={() => {
                  setIsDropdownOpen(false);
                  setShowLogoutConfirm(true);
                }}
                className="dropdown-item logout"
              >
                <ArrowRightOnRectangleIcon className="dropdown-icon" /> Log Out
              </button>
            </div>
          </div>
        )}
      </div>

      {typeof document !== 'undefined' && logoutConfirmDialog && createPortal(logoutConfirmDialog, document.body)}
    </header>
  );
}
