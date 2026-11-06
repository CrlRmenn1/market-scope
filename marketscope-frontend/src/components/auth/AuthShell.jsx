import React from 'react';
import { ArrowLeftIcon } from '@heroicons/react/24/outline';
import { BrandLockup } from './AuthField';
import ScanMapArt from './ScanMapArt';

// Layout for the login, registration and reset screens: a slim brand bar above
// the form on phones, the map panel beside it on desktop. It all sits in one
// scrolling page, so the bar moves away with the form when the keyboard opens.
export default function AuthShell({ onBack, backLabel, children }) {
  return (
    <div className="auth-shell">
      <aside className="auth-panel">
        <ScanMapArt />
        <BrandLockup className="auth-brand-on-dark" />
        <div className="auth-panel-copy">
          <p className="auth-panel-title">Discover Panabo's hidden markets.</p>
          <p className="auth-panel-text">Drop a pin anywhere in the city and see how viable your business idea is there.</p>
        </div>
      </aside>

      <main className="auth-main">
        <header className="auth-bar">
          <button type="button" className="auth-back" onClick={onBack} aria-label={backLabel}>
            <ArrowLeftIcon aria-hidden="true" />
          </button>
          <BrandLockup className="auth-bar-brand" />
        </header>
        <div className="auth-column">{children}</div>
      </main>
    </div>
  );
}
