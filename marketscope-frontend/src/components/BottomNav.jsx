import React from 'react';

export default function BottomNav({ activeTab, setActiveTab }) {
  const getActiveIndex = () => {
    if (activeTab === 'home') return 0;
    if (activeTab === 'profile') return 1;
    if (activeTab === 'history') return 2;
    return 0;
  };

  return (
    <nav className="bottom-navbar">
      <div 
        className="fluid-indicator" 
        style={{ transform: `translateX(${getActiveIndex() * 100}%)` }}
      ></div>

      <button className={`nav-item ${activeTab === 'home' ? 'active' : ''}`} onClick={() => setActiveTab('home')}>
        <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M3 9l9-7 9 7v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"></path></svg>
        <span>Map</span>
      </button>

      <button className={`nav-item ${activeTab === 'profile' ? 'active' : ''}`} onClick={() => setActiveTab('profile')}>
        <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"></path><circle cx="12" cy="7" r="4"></circle></svg>
        <span>Profile</span>
      </button>

      <button className={`nav-item ${activeTab === 'history' ? 'active' : ''}`} onClick={() => setActiveTab('history')}>
        <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><circle cx="12" cy="12" r="10"></circle><polyline points="12 6 12 12 16 14"></polyline></svg>
        <span>History</span>
      </button>
    </nav>
  );
}