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

  return (
    <nav className="fixed bottom-[calc(22px+env(safe-area-inset-bottom))] left-1/2 z-[2000] flex w-[min(92vw,420px)] -translate-x-1/2 rounded-full border border-white/10 bg-slate-950/70 p-2 shadow-[0_20px_50px_rgba(0,0,0,0.6)] backdrop-blur-2xl">
      <div
        className="fluid-indicator pointer-events-none absolute inset-y-2 left-2 w-[calc((100%-16px)/3)] rounded-full bg-violet-500/15 transition-transform duration-500 ease-[cubic-bezier(0.68,-0.55,0.26,1.55)]"
        style={{ transform: `translateX(${tabs.findIndex((tab) => tab.id === activeTab) * 100}%)` }}
      />

      {tabs.map((tab) => {
        const isActive = activeTab === tab.id;
        return (
          <button
            key={tab.id}
            className={`nav-item relative z-10 flex-1 rounded-full px-0 py-2 text-center transition duration-200 ${isActive ? 'active text-violet-400' : 'text-slate-400 hover:-translate-y-0.5 hover:text-violet-300'}`}
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