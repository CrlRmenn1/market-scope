import React, { useState, useEffect } from 'react';
import './Auth.css';

export default function AuthPages({ onLoginSuccess }) {
  const [currentView, setCurrentView] = useState('landing'); 
  const [password, setPassword] = useState('');
  const [passwordStrength, setPasswordStrength] = useState(0);
  const [errorMsg, setErrorMsg] = useState('');
  const [isLoading, setIsLoading] = useState(false);

  // Dynamic API URL: Uses the Vercel environment variable in production 
  // and falls back to localhost during development.
  const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000';

  useEffect(() => {
    let score = 0;
    if (password.length > 5) score += 1;
    if (password.length > 8) score += 1;
    if (/[A-Z]/.test(password)) score += 1;
    if (/[0-9]/.test(password)) score += 1;
    setPasswordStrength(score);
  }, [password]);

  const getMeterColor = () => {
    if (passwordStrength <= 1) return '#ef4444'; 
    if (passwordStrength === 2) return '#facc15'; 
    if (passwordStrength >= 3) return '#a855f7'; 
    return '#334155';
  };

  const handleLogin = async (e) => {
    e.preventDefault();
    setErrorMsg('');
    setIsLoading(true);
    const email = e.target.email.value;
    const pwd = e.target.password.value;

    try {
      const response = await fetch(`${API_URL}/login`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email, password: pwd })
      });
      const data = await response.json();
      
      if (response.ok) {
        onLoginSuccess(data.user);
      } else {
        setErrorMsg(data.detail || 'Invalid credentials');
      }
    } catch (err) {
      setErrorMsg('Server connection failed. Is the backend running?');
    } finally {
      setIsLoading(false);
    }
  };

  const handleRegister = async (e) => {
    e.preventDefault();
    setErrorMsg('');
    setIsLoading(true);
    const name = e.target.name.value;
    const email = e.target.email.value;
    const pwd = password;
    const confirmPwd = e.target.confirm.value;

    if (pwd !== confirmPwd) {
      setErrorMsg("Passwords do not match!");
      setIsLoading(false);
      return;
    }

    try {
      const response = await fetch(`${API_URL}/register`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ full_name: name, email, password: pwd })
      });
      const data = await response.json();
      
      if (response.ok) {
        setCurrentView('login');
        setErrorMsg('Registration successful! Please log in.');
      } else {
        setErrorMsg(data.detail || 'Registration failed');
      }
    } catch (err) {
      setErrorMsg('Server connection failed.');
    } finally {
      setIsLoading(false);
    }
  };

  const LandingBrand = () => (
    <div className="landing-brand-container mb-6">
      <div className="brand-wrapper" style={{ justifyContent: 'center' }}>
        <div className="brand-mark mark-pulse">
          <div className="lens-left"></div>
          <div className="lens-center">
            <div className="lens-reflection"></div>
          </div>
          <div className="lens-right"></div>
        </div>
        
        <h1 className="app-title" style={{ fontSize: '2.5rem', margin: 0, color: 'white' }}>
          Market<span className="highlight-text" style={{ color: '#a855f7' }}>Scope</span>
        </h1>
      </div>
    </div>
  );

  const renderLanding = () => (
    <div className="auth-card animate-fade-in">
      <LandingBrand />
      
      <div className="mobile-hero-text mb-8">
        <div className="hero-badge mb-4">MCDA ENGINE V1.0</div>
        <h2>Discover Panabo's<br/>Hidden Markets.</h2>
        <p>The ultimate geospatial viability engine designed exclusively for local MSMEs.</p>
      </div>
      
      <div className="auth-actions-row">
        <button className="btn-primary" onClick={() => setCurrentView('register')}>
          Get Started
        </button>
        <button className="btn-secondary" onClick={() => setCurrentView('login')}>
          Sign In
        </button>
      </div>
    </div>
  );

  const renderLogin = () => (
    <div className="auth-card animate-fade-in">
      <button className="back-link mb-6" onClick={() => setCurrentView('landing')}>
        &larr; Back
      </button>
      
      <div className="auth-header mb-8">
        <h2>Welcome Back</h2>
        <p>Log in to continue to MarketScope</p>
      </div>

      {errorMsg && (
        <div className={errorMsg.includes('successful') ? "success-alert fade-in" : "error-alert fade-in"}>
          {errorMsg}
        </div>
      )}

      <form onSubmit={handleLogin}>
        <div className="input-group">
          <label>Email</label>
          <input type="email" name="email" placeholder="john@example.com" required />
        </div>
        
        <div className="input-group">
          <label>Password</label>
          <input type="password" name="password" placeholder="••••••••" required />
        </div>

        <button type="submit" className="btn-primary w-full mt-4 mb-8" disabled={isLoading}>
          {isLoading ? 'Logging in...' : 'Log In'}
        </button>
        
        <p className="auth-footer">
          Don't have an account? <span onClick={() => setCurrentView('register')}>Sign Up</span>
        </p>
      </form>
    </div>
  );

  const renderRegister = () => (
    <div className="auth-card animate-fade-in">
      <button className="back-link mb-6" onClick={() => setCurrentView('landing')}>
        &larr; Back
      </button>

      <div className="auth-header mb-8">
        <h2>Create Account</h2>
        <p>Start your journey with MarketScope</p>
      </div>

      {errorMsg && <div className="error-alert">{errorMsg}</div>}

      <form onSubmit={handleRegister}>
        <div className="input-group">
          <label>Full Name</label>
          <input type="text" name="name" placeholder="John Doe" required />
        </div>
        
        <div className="input-group">
          <label>Email</label>
          <input type="email" name="email" placeholder="john@example.com" required />
        </div>
        
        <div className="input-group" style={{ marginBottom: '12px' }}>
          <label>Password</label>
          <input 
            type="password" 
            placeholder="••••••••" 
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            required 
          />
        </div>

        <div className="password-strength-wrapper mb-6">
          <div className="strength-meter">
            <div className="strength-fill" style={{ width: `${(passwordStrength / 4) * 100}%`, backgroundColor: getMeterColor() }}></div>
          </div>
        </div>

        <div className="input-group">
          <label>Confirm Password</label>
          <input type="password" name="confirm" placeholder="••••••••" required />
        </div>

        <button type="submit" className="btn-primary w-full mt-4 mb-8" disabled={isLoading}>
          {isLoading ? 'Creating Account...' : 'Create Account'}
        </button>

        <p className="auth-footer">
          Already have an account? <span onClick={() => setCurrentView('login')}>Log In</span>
        </p>
      </form>
    </div>
  );

  return (
    <div className={`auth-container ${currentView === 'landing' ? 'view-landing' : ''}`}>
      <div className="auth-hero">
        <div className="hero-text">
          <div className="hero-badge mb-6">MCDA ENGINE V1.0</div>
          <h1>Discover<br/>Panabo's<br/>Hidden Markets.</h1>
          <p>The ultimate geospatial viability engine designed<br/>exclusively for local entrepreneurs and MSMEs.</p>
        </div>
      </div>

      <div className="auth-form-wrapper">
        {currentView === 'landing' && renderLanding()}
        {currentView === 'login' && renderLogin()}
        {currentView === 'register' && renderRegister()}
      </div>
    </div>
  );
}