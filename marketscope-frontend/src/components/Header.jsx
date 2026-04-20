import React, { useState } from 'react';
import { 
  Cog8ToothIcon, 
  SunIcon, 
  MoonIcon, 
  ArrowRightOnRectangleIcon 
} from '@heroicons/react/24/solid';

export default function Header({ theme, toggleTheme, onLogout, onGoHome, userName, userAvatarUrl }) {
  const [isDropdownOpen, setIsDropdownOpen] = useState(false);

  // Get first letter of name for a fallback avatar
  const userInitial = userName ? userName.charAt(0).toUpperCase() : 'G';

  return (
    <header className="app-header">
      <div className="brand-wrapper">
        <button className="brand-home-btn" onClick={onGoHome} aria-label="Go to Home screen">
          <div className="brand-mark" aria-hidden="true">
            <div className="lens-left" />
            <div className="lens-center">
              <div className="lens-reflection" />
            </div>
            <div className="lens-right" />
          </div>
        </button>
        <h1 className="app-title">
          Market<span className="highlight-text">Scope</span>
        </h1>
      </div>

      {/* SETTINGS MENU (Unified with Name) */}
      <div className="settings-wrapper">
        <button 
          onClick={() => setIsDropdownOpen(!isDropdownOpen)}
          className={`user-settings-btn ${isDropdownOpen ? 'active' : ''}`}
        >
          {/* Small Avatar Circle */}
          {userAvatarUrl ? (
            <img src={userAvatarUrl} alt="Profile" className="user-avatar-tiny user-avatar-image" />
          ) : (
            <div className="user-avatar-tiny">{userInitial}</div>
          )}
          
          {/* The Name */}
          <span className="settings-user-name">{userName || 'Guest'}</span>
          
          {/* The Gear Icon */}
          <Cog8ToothIcon className={`gear-icon-small ${isDropdownOpen ? 'open' : ''}`} />
        </button>

        {isDropdownOpen && (
          <div className="settings-dropdown">
            <div className="dropdown-menu">
              <button 
                onClick={() => {
                  toggleTheme();
                  setIsDropdownOpen(false);
                }}
                className="dropdown-item"
              >
                {theme === 'light' ? (
                  <><MoonIcon className="dropdown-icon" /> Dark Mode</>
                ) : (
                  <><SunIcon className="dropdown-icon" /> Light Mode</>
                )}
              </button>
              
              <div className="dropdown-divider"></div>
              
              <button 
                onClick={() => {
                  setIsDropdownOpen(false);
                  if (onLogout) onLogout();
                }}
                className="dropdown-item logout"
              >
                <ArrowRightOnRectangleIcon className="dropdown-icon" /> Log Out
              </button>
            </div>
          </div>
        )}
      </div>
    </header>
  );
}