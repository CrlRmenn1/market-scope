import React, { useState, useEffect } from 'react';
import AuthPages from './AuthPages';
import Header from './components/Header';
import Home from './pages/Home';
import Profile from './pages/Profile';
import History from './pages/History';
import BottomNav from './components/BottomNav';
import BottomSheet from './components/BottomSheet';
import Report from './pages/Report';
import AdminPanel from './pages/AdminPanel';
import './App.css';

export default function App() {
  const validTabs = ['home', 'profile', 'history'];
  const OPEN_REPORT_KEY = 'marketscope_open_report';
  const ADMIN_SESSION_KEY = 'marketscope_admin_session';
  const [session, setSession] = useState(null);
  const [adminSession, setAdminSession] = useState(null);
  const [activeTab, setActiveTab] = useState(() => {
    const savedTab = localStorage.getItem('marketscope_active_tab');
    return validTabs.includes(savedTab) ? savedTab : 'home';
  });
  const [theme, setTheme] = useState(() => localStorage.getItem('marketscope_theme') || 'light');
  const [showBottomSheet, setShowBottomSheet] = useState(false);
  const [selectedCoords, setSelectedCoords] = useState(null);
  const [reportData, setReportData] = useState(null);
  const [justLoggedOut, setJustLoggedOut] = useState(false);

  const saveOpenReport = (data, coords) => {
    localStorage.setItem(OPEN_REPORT_KEY, JSON.stringify({ data, coords }));
  };

  const clearOpenReport = () => {
    localStorage.removeItem(OPEN_REPORT_KEY);
  };

  useEffect(() => {
    const savedUser = localStorage.getItem('marketscope_session');
    if (savedUser) {
      setSession(JSON.parse(savedUser));
    }

    const savedAdmin = localStorage.getItem(ADMIN_SESSION_KEY);
    if (savedAdmin) {
      setAdminSession(JSON.parse(savedAdmin));
    }

    const savedTheme = localStorage.getItem('marketscope_theme') || 'light';
    document.documentElement.setAttribute('data-theme', savedTheme);
  }, []);

  useEffect(() => {
    if (!session || reportData) return;

    const raw = localStorage.getItem(OPEN_REPORT_KEY);
    if (!raw) return;

    try {
      const parsed = JSON.parse(raw);
      if (parsed?.data) {
        setReportData(parsed.data);
        setSelectedCoords(parsed.coords || parsed.data.target_coords || null);
      } else {
        clearOpenReport();
      }
    } catch {
      clearOpenReport();
    }
  }, [session, reportData]);

  useEffect(() => {
    const handleOpenReport = (event) => {
      const payload = event.detail;
      if (!payload) return;
      const coords = payload.target_coords || null;
      setSelectedCoords(coords);
      setReportData(payload);
      saveOpenReport(payload, coords);
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

  const handleAdminLoginSuccess = (adminData) => {
    const nextAdminSession = {
      email: adminData.email,
      token: adminData.token
    };
    localStorage.setItem(ADMIN_SESSION_KEY, JSON.stringify(nextAdminSession));
    localStorage.removeItem('marketscope_session');
    setSession(null);
    setAdminSession(nextAdminSession);
  };

  const handleAdminLogout = () => {
    localStorage.removeItem(ADMIN_SESSION_KEY);
    setAdminSession(null);
  };

  const handleLogout = () => {
    localStorage.removeItem('marketscope_session');
    localStorage.removeItem('marketscope_active_tab');
    clearOpenReport();
    setSession(null);
    setJustLoggedOut(true);
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
    const coords = data?.target_coords || selectedCoords || null;
    setSelectedCoords(coords);
    setReportData(data);
    saveOpenReport(data, coords);
    setShowBottomSheet(false);
  };

  const handleCloseReport = () => {
    setReportData(null);
    clearOpenReport();
  };

  if (!session && !adminSession) {
    const initialView = justLoggedOut ? 'login' : 'landing';
    return (
      <AuthPages 
        onLoginSuccess={handleLoginSuccess} 
        onAdminLoginSuccess={handleAdminLoginSuccess}
        initialView={initialView}
        onAuthPagesMounted={() => setJustLoggedOut(false)}
      />
    );
  }

  if (adminSession) {
    const adminName = adminSession.email
      ? `Admin (${adminSession.email.split('@')[0]})`
      : 'Admin';

    return (
      <div className="app-container">
        <Header
          theme={theme}
          toggleTheme={toggleTheme}
          onLogout={handleAdminLogout}
          onGoHome={() => {}}
          userName={adminName}
          userAvatarUrl={null}
        />

        <main className="app-content admin-content">
          <AdminPanel adminSession={adminSession} onAdminLogout={handleAdminLogout} />
        </main>
      </div>
    );
  }

  return (
    <div className="app-container">
      <Header 
        theme={theme} 
        toggleTheme={toggleTheme} 
        onLogout={handleLogout} 
        onGoHome={() => {
          setActiveTab('home');
          handleCloseReport();
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
          const coords = payload.target_coords || null;
          setSelectedCoords(coords);
          setReportData(payload);
          saveOpenReport(payload, coords);
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
            onClose={handleCloseReport} 
          />
        )}
      </main>

      {!showBottomSheet && !reportData && (
        <BottomNav activeTab={activeTab} setActiveTab={setActiveTab} />
      )}
    </div>
  );
}