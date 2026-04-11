import React, { useState, useEffect } from 'react';
import './Auth.css';

export default function AuthPages({ onLoginSuccess }) {
  const [currentView, setCurrentView] = useState('landing'); 
  const [password, setPassword] = useState('');
  const [passwordStrength, setPasswordStrength] = useState(0);
  const [errorMsg, setErrorMsg] = useState('');
  const [isLoading, setIsLoading] = useState(false);

  // NEW: State to track password visibility
  const [showPassword, setShowPassword] = useState(false);
  const [showConfirmPassword, setShowConfirmPassword] = useState(false);

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

  // SVG Icons for the Toggle Button
  const EyeIcon = () => (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"></path>
      <circle cx="12" cy="12" r="3"></circle>
    </svg>
  );

  const EyeSlashIcon = () => (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M17.94 17.94A10.07 10.07 0 0 1 12 20c-7 0-11-8-11-8a18.45 18.45 0 0 1 5.06-5.94M9.9 4.24A9.12 9.12 0 0 1 12 4c7 0 11 8 11 8a18.5 18.5 0 0 1-2.16 3.19m-6.72-1.07a3 3 0 1 1-4.24-4.24"></path>
      <line x1="1" y1="1" x2="23" y2="23"></line>
    </svg>
  );

  const handleLogin = async (e) => {
    e.preventDefault();
    setErrorMsg('');
    setIsLoading(true);
    const email = e.target.email.value;
    const pwd = e.target.password.value;

    try {
      const response = await fetch('http://localhost:8000/login', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email, password: pwd })
      });
      const data = await response.json();
      
      if (!response.ok) throw new Error(data.detail || 'Login failed');
      onLoginSuccess(data.user);
    } catch (err) {
      setErrorMsg(err.message);
    } finally {
      setIsLoading(false);
    }
  };

  const handleRegister = async (e) => {
    e.preventDefault();
    setErrorMsg('');
    setIsLoading(true);
    
    const fullName = e.target.full_name.value;
    const email = e.target.email.value;
    const pwd = e.target.password.value;
    const confirm = e.target.confirm.value;

    if (pwd !== confirm) {
      setErrorMsg("Passwords do not match");
      setIsLoading(false);
      return;
    }

    try {
      const response = await fetch('http://localhost:8000/register', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ full_name: fullName, email, password: pwd })
      });
      const data = await response.json();
      
      if (!response.ok) throw new Error(data.detail || 'Registration failed');
      onLoginSuccess(data.user);
    } catch (err) {
      setErrorMsg(err.message);
    } finally {
      setIsLoading(false);
    }
  };

  const renderLogin = () => (
    <div className="fade-in">
      <h2 style={{ color: "white" }}>Welcome Back</h2>
      <p className="auth-subtitle" style={{ color: "white" }}>Access your MarketScope dashboard.</p>
      <br />
      
      {errorMsg && <div className="error-alert">{errorMsg}</div>}

      <form onSubmit={handleLogin} className="mt-6">
        <div className="input-group">
          <label>Email Address</label>
          <input type="email" name="email" placeholder="msme@panabo.com" required />
        </div>

        <div className="input-group">
          <label>Password</label>
          <div className="password-input-wrapper">
            <input 
              type={showPassword ? "text" : "password"} 
              name="password" 
              placeholder="••••••••" 
              required 
            />
            <button 
              type="button" 
              className="password-toggle-btn" 
              onClick={() => setShowPassword(!showPassword)}
            >
              {showPassword ? <EyeSlashIcon /> : <EyeIcon />}
            </button>
          </div>
        </div>

        <button type="submit" className="btn-primary w-full mt-6 mb-8" disabled={isLoading}>
          {isLoading ? 'Authenticating...' : 'Log In'}
        </button>

        <p className="auth-footer">
          New to MarketScope? <span onClick={() => setCurrentView('landing')}>Create Account</span>
        </p>
      </form>
    </div>
  );

  const renderLanding = () => (
    <div className="fade-in">
      <h2>Create Account</h2>
      <p className="auth-subtitle">Start analyzing Panabo's markets today.</p>

      {errorMsg && <div className="error-alert">{errorMsg}</div>}

      <form onSubmit={handleRegister} className="mt-6">
        <div className="input-group">
          <label>Full Name</label>
          <input type="text" name="full_name" placeholder="Juan Dela Cruz" required />
        </div>

        <div className="input-group">
          <label>Email Address</label>
          <input type="email" name="email" placeholder="juan@business.com" required />
        </div>

        <div className="input-group">
          <label>Password</label>
          <div className="password-input-wrapper">
            <input 
              type={showPassword ? "text" : "password"} 
              name="password" 
              placeholder="••••••••" 
              required 
              onChange={(e) => setPassword(e.target.value)}
            />
            <button 
              type="button" 
              className="password-toggle-btn" 
              onClick={() => setShowPassword(!showPassword)}
            >
              {showPassword ? <EyeSlashIcon /> : <EyeIcon />}
            </button>
          </div>
          
          <div className="password-strength-wrapper mt-2">
            <div className="strength-meter">
              <div className="strength-fill" style={{ width: `${(passwordStrength / 4) * 100}%`, backgroundColor: getMeterColor() }}></div>
            </div>
          </div>
        </div>

        <div className="input-group">
          <label>Confirm Password</label>
          <div className="password-input-wrapper">
            <input 
              type={showConfirmPassword ? "text" : "password"} 
              name="confirm" 
              placeholder="••••••••" 
              required 
            />
            <button 
              type="button" 
              className="password-toggle-btn" 
              onClick={() => setShowConfirmPassword(!showConfirmPassword)}
            >
              {showConfirmPassword ? <EyeSlashIcon /> : <EyeIcon />}
            </button>
          </div>
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
      
      {/* Desktop Hero Side */}
      <div className="auth-hero">
        <div className="hero-text">
          <div className="hero-badge mb-6">MCDA ENGINE V1.0</div>
          <h1>Discover<br/>Panabo's<br/>Hidden Markets.</h1>
          <p>The ultimate geospatial viability engine designed<br/>exclusively for local entrepreneurs and MSMEs.</p>
        </div>
      </div>

      {/* Form Side */}
      <div className="auth-form-wrapper">
        {currentView === 'landing' && renderLanding()}
        {currentView === 'login' && renderLogin()}
      </div>
    </div>
  );
}