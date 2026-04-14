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
  const validTabs = ['home', 'profile', 'history'];
  const [session, setSession] = useState(null);
  const [activeTab, setActiveTab] = useState(() => {
    const savedTab = localStorage.getItem('marketscope_active_tab');
    return validTabs.includes(savedTab) ? savedTab : 'home';
  });
  const [theme, setTheme] = useState(() => localStorage.getItem('marketscope_theme') || 'light');
  const [showBottomSheet, setShowBottomSheet] = useState(false);
  const [selectedCoords, setSelectedCoords] = useState(null);
  const [reportData, setReportData] = useState(null);

  useEffect(() => {
    const savedUser = localStorage.getItem('marketscope_session');
    if (savedUser) {
      setSession(JSON.parse(savedUser));
    }
    const savedTheme = localStorage.getItem('marketscope_theme') || 'light';
    document.documentElement.setAttribute('data-theme', savedTheme);
  }, []);

  useEffect(() => {
    const handleOpenReport = (event) => {
      const payload = event.detail;
      if (!payload) return;
      setSelectedCoords(payload.target_coords || null);
      setReportData(payload);
      setShowBottomSheet(false);
      setActiveTab('history');
    };

    window.addEventListener('marketscope-open-report', handleOpenReport);
    return () => {
      window.removeEventListener('marketscope-open-report', handleOpenReport);
    };
  }, []);

  useEffect(() => {
    if (!session) return;
    localStorage.setItem('marketscope_active_tab', activeTab);
  }, [activeTab, session]);

  const handleLoginSuccess = (userData) => {
    const nextSession = {
      ...userData,
      name: userData.full_name || userData.name || userData.email,
    };
    localStorage.setItem('marketscope_session', JSON.stringify(nextSession));
    setSession(nextSession);
  };

  const handleProfileUpdate = (updatedUser) => {
    const nextSession = { ...session, ...updatedUser, name: updatedUser.full_name || updatedUser.name };
    localStorage.setItem('marketscope_session', JSON.stringify(nextSession));
    setSession(nextSession);
  };

  const handleLogout = () => {
    localStorage.removeItem('marketscope_session');
    localStorage.removeItem('marketscope_active_tab');
    setSession(null);
  };

  const toggleTheme = () => {
    const newTheme = theme === 'light' ? 'dark' : 'light';
    setTheme(newTheme);
    document.documentElement.setAttribute('data-theme', newTheme);
    localStorage.setItem('marketscope_theme', newTheme);
  };

  const handleMapTap = (coords) => {
    setSelectedCoords(coords);
    setShowBottomSheet(true);
  };

  const handleViewReport = (data) => {
    setReportData(data);
    setShowBottomSheet(false);
  };

  if (!session) {
    return <AuthPages onLoginSuccess={handleLoginSuccess} />;
  }

  return (
    <div className="app-container">
      <Header 
        theme={theme} 
        toggleTheme={toggleTheme} 
        onLogout={handleLogout} 
        onGoHome={() => {
          setActiveTab('home');
          setReportData(null);
          setShowBottomSheet(false);
        }}
        userName={session.full_name || session.name}
        userAvatarUrl={session.avatar_url}
      />

      <main className={`app-content ${reportData ? 'app-content-locked' : ''}`}>
        {activeTab === 'home' && (
          <Home onMapTap={handleMapTap} theme={theme} />
        )}
        
        {activeTab === 'profile' && <Profile user={session} onProfileUpdate={handleProfileUpdate} />}
        
        {activeTab === 'history' && <History user={session} onOpenReport={(payload) => {
          setSelectedCoords(payload.target_coords || null);
          setReportData(payload);
          setShowBottomSheet(false);
          setActiveTab('history');
        }} />}

        {showBottomSheet && (
          <BottomSheet 
            coords={selectedCoords} 
            onClose={() => setShowBottomSheet(false)} 
            onViewReport={handleViewReport}
            userId={session.user_id || session.id}
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

      {!showBottomSheet && !reportData && (
        <BottomNav activeTab={activeTab} setActiveTab={setActiveTab} />
      )}
    </div>
  );
}