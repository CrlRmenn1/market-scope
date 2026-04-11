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
  const [session, setSession] = useState(null);
  const [activeTab, setActiveTab] = useState('home');
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
        userName={session.name} 
      />

      <main className="app-content">
        {activeTab === 'home' && (
          <Home onMapTap={handleMapTap} theme={theme} />
        )}
        
        {activeTab === 'profile' && <Profile />}
        
        {activeTab === 'history' && <History />}

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

      {!showBottomSheet && !reportData && (
        <BottomNav activeTab={activeTab} setActiveTab={setActiveTab} />
      )}
    </div>
  );
}