import React, { useState, useEffect } from 'react';
import AuthPages from './AuthPages';
import Header from './components/Header';
import Home from './pages/Home';
import Profile from './pages/Profile';
import History from './pages/History';
import BottomNav from './components/BottomNav';
import BottomSheet from './components/BottomSheet';
import Report from './pages/Report';
import './App.css';

export default function App() {
  // 1. SESSION STATE
  const [session, setSession] = useState(null);
  const [activeTab, setActiveTab] = useState('home'); // 'home', 'profile', 'history'
  
  // ---> CHANGED HERE: Default is now 'light'
  const [theme, setTheme] = useState('light');

  // 2. ANALYSIS STATES
  const [showBottomSheet, setShowBottomSheet] = useState(false);
  const [selectedCoords, setSelectedCoords] = useState(null);
  const [reportData, setReportData] = useState(null);

  // Check for existing session on load AND force Light Mode CSS
  useEffect(() => {
    const savedUser = localStorage.getItem('marketscope_session');
    if (savedUser) {
      setSession(JSON.parse(savedUser));
    }
    // ---> CHANGED HERE: Forces the CSS to recognize Light Mode immediately
    document.documentElement.setAttribute('data-theme', 'light');
  }, []);

  // Auth Handlers
  const handleLoginSuccess = (userData) => {
    localStorage.setItem('marketscope_session', JSON.stringify(userData));
    setSession(userData);
  };

  const handleLogout = () => {
    localStorage.removeItem('marketscope_session');
    setSession(null);
  };

  const toggleTheme = () => {
    const newTheme = theme === 'light' ? 'dark' : 'light';
    setTheme(newTheme);
    document.documentElement.setAttribute('data-theme', newTheme);
  };

  // Map Interaction Handler
  const handleMapTap = (coords) => {
    setSelectedCoords(coords);
    setShowBottomSheet(true);
  };

  const handleViewReport = (data) => {
    setReportData(data);
    setShowBottomSheet(false);
  };

  // --- GATEKEEPER ---
  if (!session) {
    return <AuthPages onLoginSuccess={handleLoginSuccess} />;
  }

  // --- MAIN DASHBOARD ---
  return (
    <div className="app-container">
      <Header 
        theme={theme} 
        toggleTheme={toggleTheme} 
        onLogout={handleLogout} 
        userName={session.name} 
      />

      <main className="app-content">
        {/* TAB SWITCHING LOGIC */}
        {activeTab === 'home' && (
          <Home onMapTap={handleMapTap} theme={theme} />
        )}
        
        {activeTab === 'profile' && <Profile />}
        
        {activeTab === 'history' && <History />}

        {/* OVERLAYS */}
        {showBottomSheet && (
          <BottomSheet 
            coords={selectedCoords} 
            onClose={() => setShowBottomSheet(false)} 
            onViewReport={handleViewReport}
          />
        )}

        {reportData && (
          <Report 
            data={reportData} 
            targetCoords={selectedCoords} 
            onClose={() => setReportData(null)} 
          />
        )}
      </main>

      {/* BOTTOM NAVIGATION */}
      {!showBottomSheet && !reportData && (
        <BottomNav activeTab={activeTab} setActiveTab={setActiveTab} />
      )}
    </div>
  );
}