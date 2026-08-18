import React, { useState, useEffect, useRef } from 'react';
import AuthPages from './AuthPages';
import Header from './components/Header';
import Home from './pages/Home';
import Profile from './pages/Profile';
import History from './pages/History';
import Trends from './pages/Trends';
import BottomNav from './components/BottomNav';
import Report from './pages/Report';
import AdminPanel from './pages/AdminPanel';
import AdminNavbar from './components/AdminNavbar';
import OnboardingModal from './components/OnboardingModal';
import SpaceSubmissionModal from './components/SpaceSubmissionModal';
import { apiUrl } from './api';
import './App.css';

const REQUIRED_TREND_FIELDS = [
  'primary_business',
  'startup_capital',
  'preferred_setup',
  'target_payback_months'
];

const normalizePreferenceValue = (value) => {
  if (value === null || value === undefined) return null;
  if (typeof value === 'string') {
    const trimmed = value.trim();
    return trimmed ? trimmed : null;
  }
  return value;
};

const getMissingTrendPreferenceFields = (user) => REQUIRED_TREND_FIELDS.filter((field) => normalizePreferenceValue(user?.[field]) === null);

export default function App() {
  const validTabs = ['home', 'trends', 'profile', 'history'];
  const OPEN_REPORT_KEY = 'marketscope_open_report';
  const ADMIN_SESSION_KEY = 'marketscope_admin_session';
  const appShellClass = 'relative flex h-[100svh] w-full flex-col overflow-hidden bg-[var(--bg-app)] text-[var(--text-main)] transition-colors duration-300';
  const appContentClass = 'relative min-h-0 flex-1 overflow-x-hidden overflow-y-auto antialiased';
  const adminContentClass = 'pt-[88px]';
  const [session, setSession] = useState(null);
  const [adminSession, setAdminSession] = useState(null);
  const [adminActiveTab, setAdminActiveTab] = useState('msmes');
  const [activeTab, setActiveTab] = useState(() => {
    const savedTab = localStorage.getItem('marketscope_active_tab');
    return validTabs.includes(savedTab) ? savedTab : 'home';
  });
  const [theme, setTheme] = useState(() => localStorage.getItem('marketscope_theme') || 'light');
  const [selectedCoords, setSelectedCoords] = useState(null);
  const [reportData, setReportData] = useState(null);
  const [mapPreviewSelection, setMapPreviewSelection] = useState(null);
  const [justLoggedOut, setJustLoggedOut] = useState(false);
  const [showOnboarding, setShowOnboarding] = useState(false);
  const [showSpaceSubmissionModal, setShowSpaceSubmissionModal] = useState(false);
  const [missingTrendPreferences, setMissingTrendPreferences] = useState([]);
  const [isSpaceDetailOpen, setIsSpaceDetailOpen] = useState(false);
  const [tourActive, setTourActive] = useState(false);

  const saveOpenReport = (data, coords) => {
    localStorage.setItem(OPEN_REPORT_KEY, JSON.stringify({ data, coords }));
  };

  const clearOpenReport = () => {
    localStorage.removeItem(OPEN_REPORT_KEY);
  };

  // Session-lived cache of resolved history reports, keyed by history_id.
  // History unmounts on every tab switch, so this has to live up here to
  // survive "open a report, check Trends, come back" - a plain useState/ref
  // inside History itself would be wiped each time.
  const reportCacheRef = useRef(new Map());

  const getCachedHistoryReport = (historyId) => (historyId ? reportCacheRef.current.get(historyId) || null : null);

  const cacheHistoryReport = (historyId, payload) => {
    if (historyId) reportCacheRef.current.set(historyId, payload);
  };

  const evictCachedHistoryReports = (historyIds) => {
    (Array.isArray(historyIds) ? historyIds : [historyIds]).forEach((id) => reportCacheRef.current.delete(id));
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
    if (!session) {
      setShowOnboarding(false);
      return;
    }

    // Per-account flag persisted on the user record (not device-wide storage).
    setShowOnboarding(!session.onboarding_seen);
  }, [session]);

  useEffect(() => {
    if (!session) {
      setMissingTrendPreferences([]);
      return;
    }

    const sessionMissing = Array.isArray(session.missing_trend_preferences)
      ? session.missing_trend_preferences
      : getMissingTrendPreferenceFields(session);

    setMissingTrendPreferences(sessionMissing);
  }, [session]);

  // Persist the per-account "seen" flag on the backend and in the cached session.
  const markOnboardingSeen = () => {
    setShowOnboarding(false);
    if (!session || session.onboarding_seen) return;

    const userId = session.user_id || session.id;
    if (userId) {
      fetch(apiUrl(`/users/${userId}/onboarding-seen`), { method: 'POST' }).catch(() => {});
    }

    const nextSession = { ...session, onboarding_seen: true };
    localStorage.setItem('marketscope_session', JSON.stringify(nextSession));
    setSession(nextSession);
  };

  const handleCloseOnboarding = () => {
    markOnboardingSeen();
  };

  // Kick off the hands-on scan tutorial on the map page.
  const handleStartTour = () => {
    markOnboardingSeen();
    setReportData(null);
    setActiveTab('home');
    setTourActive(true);
  };

  useEffect(() => {
    const handleOpenReport = (event) => {
      const payload = event.detail;
      if (!payload) return;
      const coords = payload.target_coords || null;
      setSelectedCoords(coords);
      setReportData(payload);
      saveOpenReport(payload, coords);
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

  const handleLoginSuccess = (userData, authMeta = null) => {
    const serverMissing = Array.isArray(authMeta?.missing_trend_preferences)
      ? authMeta.missing_trend_preferences
      : getMissingTrendPreferenceFields(userData);

    const nextSession = {
      ...userData,
      name: userData.full_name || userData.name || userData.email,
      trend_preferences_completed: serverMissing.length === 0,
      missing_trend_preferences: serverMissing,
    };

    localStorage.setItem('marketscope_session', JSON.stringify(nextSession));
    setSession(nextSession);
  };

  const handleProfileUpdate = (updatedUser) => {
    const nextMissing = getMissingTrendPreferenceFields(updatedUser);
    const nextSession = {
      ...session,
      ...updatedUser,
      name: updatedUser.full_name || updatedUser.name,
      trend_preferences_completed: nextMissing.length === 0,
      missing_trend_preferences: nextMissing,
    };
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
    reportCacheRef.current = new Map();
    setSession(null);
    setShowOnboarding(false);
    setJustLoggedOut(true);
  };

  const toggleTheme = () => {
    const newTheme = theme === 'light' ? 'dark' : 'light';
    setTheme(newTheme);
    document.documentElement.setAttribute('data-theme', newTheme);
    localStorage.setItem('marketscope_theme', newTheme);
  };

  const handleViewReport = (data) => {
    const coords = data?.target_coords || selectedCoords || null;
    setSelectedCoords(coords);
    setReportData(data);
    saveOpenReport(data, coords);
  };

  // Land on the map with the scan dock prefilled (used by Trends CTAs).
  const handleOpenScanOnMap = ({ coords, businessType, radius }) => {
    if (!coords) return;

    const nextCoords = {
      lat: Number(coords.lat),
      lng: Number(coords.lng)
    };

    setSelectedCoords(nextCoords);
    setMapPreviewSelection({
      id: Date.now(),
      coords: nextCoords,
      businessType: businessType || '',
      radius: Number(radius || 500)
    });
    setActiveTab('home');
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
      <div className={appShellClass}>
        <Header
          theme={theme}
          toggleTheme={toggleTheme}
          onLogout={handleAdminLogout}
          onGoHome={() => {}}
          userName={adminName}
          userAvatarUrl={null}
          onOpenSpaceSubmission={null}
        />

        <main className={`${appContentClass} ${adminContentClass}`}>
          <AdminPanel
            adminSession={adminSession}
            onAdminLogout={handleAdminLogout}
            activeTab={adminActiveTab}
            onActiveTabChange={setAdminActiveTab}
          />
        </main>

        <AdminNavbar activeTab={adminActiveTab} onChange={setAdminActiveTab} />
      </div>
    );
  }

  return (
    <div className={appShellClass}>
      <Header 
        theme={theme} 
        toggleTheme={toggleTheme} 
        onLogout={handleLogout} 
        onGoHome={() => {
          setActiveTab('home');
          handleCloseReport();
        }}
        userName={session.full_name || session.name}
        userAvatarUrl={session.avatar_url}
        onOpenSpaceSubmission={() => setShowSpaceSubmissionModal(true)}
        onStartTour={handleStartTour}
      />

      <main className={`${appContentClass} ${reportData ? 'overflow-hidden' : ''}`}>
        {/* Kept mounted (hidden via CSS instead of unmounted) whenever the user has a
            session, so switching tabs and back doesn't tear down and rebuild the whole
            Leaflet map (tiles, markers, hazard layer) from scratch every time - that
            was showing up as the map "disappearing" and reloading on every visit. */}
        <div style={{ display: activeTab === 'home' ? 'block' : 'none', height: '100%' }}>
          <Home
            onViewReport={handleViewReport}
            theme={theme}
            userId={session.user_id || session.id}
            previewSelection={mapPreviewSelection}
            onSpaceDetailOpenChange={setIsSpaceDetailOpen}
            tourActive={tourActive}
            onTourEnd={() => setTourActive(false)}
            isActive={activeTab === 'home'}
          />
        </div>

        {activeTab === 'profile' && <Profile user={session} onProfileUpdate={handleProfileUpdate} />}

        {activeTab === 'trends' && (
          <Trends
            user={session}
            missingTrendPreferences={missingTrendPreferences}
            onPreferencesSaved={handleProfileUpdate}
            onRunAnalysis={(coords, businessType) => {
              handleOpenScanOnMap({ coords, businessType, radius: 500 });
            }}
          />
        )}

        {activeTab === 'history' && <History
          user={session}
          onOpenReport={(payload) => {
            const coords = payload.target_coords || null;
            setSelectedCoords(coords);
            setReportData(payload);
            saveOpenReport(payload, coords);
          }}
          getCachedReport={getCachedHistoryReport}
          onCacheReport={cacheHistoryReport}
          onEvictCachedReports={evictCachedHistoryReports}
        />}

        {reportData && (
          <Report 
            data={reportData} 
            targetCoords={selectedCoords} 
            onClose={handleCloseReport} 
          />
        )}
      </main>

      {!reportData && !showSpaceSubmissionModal && !isSpaceDetailOpen && (
        <BottomNav activeTab={activeTab} setActiveTab={setActiveTab} />
      )}

      <OnboardingModal isOpen={showOnboarding} onClose={handleCloseOnboarding} onStartTour={handleStartTour} />

      <SpaceSubmissionModal
        isOpen={showSpaceSubmissionModal}
        onClose={() => setShowSpaceSubmissionModal(false)}
        userId={session?.user_id || session?.id}
      />
    </div>
  );
}