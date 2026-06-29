import React from 'react';

const NAV_ITEMS = [
  {
    id: 'msmes',
    label: 'MSMEs',
    icon: (
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
        <path d="M4 10l8-6 8 6v10a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1z" />
        <path d="M9 21V12h6v9" />
      </svg>
    )
  },
  {
    id: 'users',
    label: 'Users',
    icon: (
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
        <path d="M17 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2" />
        <circle cx="10.5" cy="7.5" r="3.5" />
        <path d="M20 21v-2a3.5 3.5 0 0 0-2.5-3.35" />
        <path d="M16.5 4.5a3.5 3.5 0 0 1 0 7" />
      </svg>
    )
  },
  {
    id: 'spaces',
    label: 'Spaces',
    icon: (
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
        <path d="M4 6h16v12H4z" />
        <path d="M8 6v12" />
        <path d="M16 6v12" />
      </svg>
    )
  },
  {
    id: 'flood',
    label: 'Map Layers',
    icon: (
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
        <path d="M12 3l9 16H3z" />
        <path d="M12 9v4" />
        <path d="M12 17h.01" />
      </svg>
    )
  }
];

export default function AdminNavbar({ activeTab, onChange }) {
  return (
    <nav className="admin-navbar" aria-label="Admin sections">
      {NAV_ITEMS.map((item) => {
        const isActive = activeTab === item.id;

        return (
          <button
            key={item.id}
            type="button"
            className={`admin-nav-item ${isActive ? 'active' : ''}`}
            onClick={() => onChange(item.id)}
            aria-pressed={isActive}
          >
            <span className="admin-nav-icon" aria-hidden="true">{item.icon}</span>
            <span className="admin-nav-label">{item.label}</span>
          </button>
        );
      })}
    </nav>
  );
}