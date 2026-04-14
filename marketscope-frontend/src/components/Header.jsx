import React, { useState } from 'react';
import { 
  Cog8ToothIcon, 
  SunIcon, 
  MoonIcon, 
  ArrowRightOnRectangleIcon 
} from '@heroicons/react/24/solid';

export default function Header({ theme, toggleTheme, onLogout, userName, userAvatarUrl, onGoHome }) {
  const [isDropdownOpen, setIsDropdownOpen] = useState(false);

  // Get first letter of name for a fallback avatar
  const userInitial = userName ? userName.charAt(0).toUpperCase() : 'G';

  return (
    <header className="app-header">
      
      {/* BRANDING */}
      <button type="button" className="brand-home-btn" onClick={() => onGoHome?.()}>
        <div className="brand-wrapper">
          <div className="brand-mark mark-pulse">
            <div className="lens-left"></div>
            <div className="lens-center">
              <div className="lens-reflection"></div>
            </div>
            <div className="lens-right"></div>
          </div>
          
          <h1 className="app-title">
            Market<span className="highlight-text">Scope</span>
          </h1>
        </div>
      </button>

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