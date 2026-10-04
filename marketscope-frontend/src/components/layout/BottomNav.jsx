import React from 'react';

export default function BottomNav({ activeTab, setActiveTab }) {
  const tabs = [
    {
      id: 'home',
      label: 'Map',
      icon: (
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M3 9l9-7 9 7v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"></path></svg>
      ),
    },
    {
      id: 'trends',
      label: 'Trends',
      icon: (
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M3 17l6-6 4 4 8-8"></path><path d="M14 7h7v7"></path></svg>
      ),
    },
    {
      id: 'profile',
      label: 'Profile',
      icon: (
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"></path><circle cx="12" cy="7" r="4"></circle></svg>
      ),
    },
    {
      id: 'history',
      label: 'History',
      icon: (
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><circle cx="12" cy="12" r="10"></circle><polyline points="12 6 12 12 16 14"></polyline></svg>
      ),
    },
  ];

  const activeIndex = Math.max(0, tabs.findIndex((tab) => tab.id === activeTab));

  return (
    <nav
      className="bottom-navbar"
      style={{
        '--nav-count': tabs.length,
        '--nav-index': activeIndex,
        bottom: 'calc(22px + env(safe-area-inset-bottom))',
        transform: 'translateX(-50%)'
      }}
    >
      <div
        className="fluid-indicator pointer-events-none"
      />

      {tabs.map((tab) => {
        const isActive = activeTab === tab.id;
        return (
          <button
            key={tab.id}
            className={`nav-item ${isActive ? 'active' : ''}`}
            onClick={() => setActiveTab(tab.id)}
          >
            <span className="mx-auto mb-1 flex h-6 w-6 items-center justify-center">
              <span className="h-6 w-6 [&_svg]:h-6 [&_svg]:w-6">{tab.icon}</span>
            </span>
            <span className="block text-[0.72rem] font-semibold leading-none">{tab.label}</span>
          </button>
        );
      })}
    </nav>
  );
}