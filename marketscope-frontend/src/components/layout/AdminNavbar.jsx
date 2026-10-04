import React from 'react';
import { ADMIN_NAV_ITEMS } from '../admin/adminNav';

// Mobile-only bottom tab bar for the admin console (the desktop uses AdminLayout's sidebar).
export default function AdminNavbar({ activeTab, onChange, pendingCount = 0 }) {
  return (
    <nav className="admin-tabbar" aria-label="Admin sections">
      {ADMIN_NAV_ITEMS.map((item) => {
        const isActive = activeTab === item.id;
        const Icon = item.icon;
        const badge = item.id === 'spaces' && pendingCount > 0 ? pendingCount : null;

        return (
          <button
            key={item.id}
            type="button"
            className={`admin-tabbar-item ${isActive ? 'is-active' : ''}`}
            onClick={() => onChange(item.id)}
            aria-current={isActive ? 'page' : undefined}
          >
            <span className="relative">
              <Icon className="h-6 w-6" aria-hidden="true" />
              {badge && <span className="admin-tabbar-badge" aria-label={`${badge} pending`}>{badge > 99 ? '99+' : badge}</span>}
            </span>
            <span className="admin-tabbar-label">{item.label}</span>
          </button>
        );
      })}
    </nav>
  );
}
