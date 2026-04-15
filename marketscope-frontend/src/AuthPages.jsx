import React, { useRef, useState, useEffect } from 'react';
import './Auth.css';
import { apiUrl } from './api';

export default function AuthPages({ onLoginSuccess, onAdminLoginSuccess, initialView = 'landing', onAuthPagesMounted }) {
  // Map initialView 'landing' to 'hero' view, but keep 'login' as is
  const [currentView, setCurrentView] = useState(initialView === 'landing' ? 'hero' : initialView); 
  const [isBurgerOpen, setIsBurgerOpen] = useState(false);
  const [password, setPassword] = useState('');
  const [passwordStrength, setPasswordStrength] = useState(0);
  const [errorMsg, setErrorMsg] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [rememberMe, setRememberMe] = useState(false);
  const [rememberedLogin, setRememberedLogin] = useState({ email: '', password: '' });

  // NEW: State to track password visibility
  const [showPassword, setShowPassword] = useState(false);
  const [showConfirmPassword, setShowConfirmPassword] = useState(false);
  const [registerAvatarDataUrl, setRegisterAvatarDataUrl] = useState('');
  const [registerAvatarFileName, setRegisterAvatarFileName] = useState('');
  const [isAvatarReading, setIsAvatarReading] = useState(false);
  const registerAvatarInputRef = useRef(null);

  const readFileAsDataUrl = (file) => new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(String(reader.result || ''));
    reader.onerror = () => reject(new Error('Failed to read image file'));
    reader.readAsDataURL(file);
  });

  useEffect(() => {
    let score = 0;
    if (password.length > 5) score += 1;
    if (password.length > 8) score += 1;
    if (/[A-Z]/.test(password)) score += 1;
    if (/[0-9]/.test(password)) score += 1;
    setPasswordStrength(score);
  }, [password]);

  useEffect(() => {
    try {
      const savedLogin = localStorage.getItem('marketscope_login_remembered');
      if (!savedLogin) return;

      const parsed = JSON.parse(savedLogin);
      setRememberMe(true);
      setRememberedLogin({
        email: parsed.email || '',
        password: parsed.password || ''
      });
    } catch {
      localStorage.removeItem('marketscope_login_remembered');
    }
  }, []);

  useEffect(() => {
    if (onAuthPagesMounted) {
      onAuthPagesMounted();
    }
  }, [onAuthPagesMounted]);

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

  const UploadIcon = () => (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
      <polyline points="17 8 12 3 7 8" />
      <line x1="12" y1="3" x2="12" y2="15" />
    </svg>
  );

  const handleLogin = async (e) => {
    e.preventDefault();
    setErrorMsg('');
    setIsLoading(true);
    const email = e.target.email.value;
    const pwd = e.target.password.value;
    const shouldRemember = e.target.rememberMe?.checked;

    try {
      const userResponse = await fetch(apiUrl('/login'), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email, password: pwd })
      });

      const userData = await userResponse.json();
      if (userResponse.ok) {
        if (shouldRemember) {
          localStorage.setItem('marketscope_login_remembered', JSON.stringify({ email, password: pwd }));
        } else {
          localStorage.removeItem('marketscope_login_remembered');
        }
        onLoginSuccess(userData.user);
        return;
      }

      const shouldTryAdmin = userResponse.status === 401 || userResponse.status === 404;
      if (shouldTryAdmin && onAdminLoginSuccess) {
        const adminResponse = await fetch(apiUrl('/admin/login'), {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ email, password: pwd })
        });

        const adminData = await adminResponse.json();
        if (adminResponse.ok) {
          if (shouldRemember) {
            localStorage.setItem('marketscope_login_remembered', JSON.stringify({ email, password: pwd }));
          } else {
            localStorage.removeItem('marketscope_login_remembered');
          }
          onAdminLoginSuccess(adminData.admin);
          return;
        }

        if (adminResponse.status === 404) {
          throw new Error('Admin login endpoint not found. Restart backend server and try again.');
        }

        throw new Error(adminData.detail || userData.detail || 'Invalid email or password');
      }

      throw new Error(userData.detail || 'Invalid email or password');
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

    if (isAvatarReading) {
      setErrorMsg('Please wait for the profile picture to finish loading.');
      setIsLoading(false);
      return;
    }
    
    const fullName = e.target.full_name.value;
    const email = e.target.email.value;
    const address = e.target.address.value;
    const cellphoneNumber = e.target.cellphone_number.value;
    const primaryBusiness = e.target.primary_business.value;
    const birthday = e.target.birthday.value;
    const ageInput = e.target.age.value;
    const pwd = e.target.password.value;
    const confirm = e.target.confirm.value;

    const computedAge = birthday
      ? Math.max(0, new Date().getFullYear() - new Date(birthday).getFullYear())
      : null;
    const parsedAge = ageInput ? Number(ageInput) : computedAge;

    if (pwd !== confirm) {
      setErrorMsg("Passwords do not match");
      setIsLoading(false);
      return;
    }

    try {
      const response = await fetch(apiUrl('/register'), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          full_name: fullName,
          email,
          password: pwd,
          address,
          cellphone_number: cellphoneNumber,
          avatar_url: registerAvatarDataUrl || null,
          age: Number.isFinite(parsedAge) ? parsedAge : null,
          birthday: birthday || null,
          primary_business: primaryBusiness
        })
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

  const renderHero = () => (
    <div className="hero-container">
      {/* Burger Menu */}
      <div className="hero-header">
        {currentView === 'register' && (
          <button className="back-btn" onClick={() => setCurrentView('hero')} aria-label="Back to landing">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <line x1="19" y1="12" x2="5" y2="12"></line>
              <polyline points="12 19 5 12 12 5"></polyline>
            </svg>
          </button>
        )}
        <button className="burger-menu-btn" onClick={() => setIsBurgerOpen(!isBurgerOpen)}>
          <span></span>
          <span></span>
          <span></span>
        </button>
        {isBurgerOpen && (
          <div className="burger-menu">
            <button className="burger-item">About Us</button>
            <button className="burger-item">How Does This Work</button>
          </div>
        )}
      </div>

      {/* Centered Hero */}
      <div className="hero-content">
        <div className="hero-badge mb-6">MCDA ENGINE V1.0</div>
        <h1 className="hero-title">Discover<br/>Panabo's<br/>Hidden Markets.</h1>
        <p className="hero-description">The geospatial viability engine designed<br/>exclusively for local entrepreneurs and MSMEs.</p>
        {currentView === 'hero' && (
          <button className="get-started-btn" onClick={() => setCurrentView('register')}>
            Get Started
          </button>
        )}
      </div>
    </div>
  );

  const renderLogin = () => (
    <div className="fade-in">
      <h2 style={{ color: 'white' }}>Welcome Back</h2>
      <p className="auth-subtitle" style={{ color: 'white' }}>Access your MarketScope dashboard.</p>
      
      {errorMsg && <div className="error-alert">{errorMsg}</div>}

      <form onSubmit={handleLogin} className="mt-6">
        <div className="input-group">
          <label>Email Address</label>
          <input type="email" name="email" placeholder="msme@panabo.com" defaultValue={rememberedLogin.email} autoComplete="username" required />
        </div>

        <div className="input-group">
          <label>Password</label>
          <div className="password-input-wrapper">
            <input 
              type={showPassword ? "text" : "password"} 
              name="password" 
              placeholder="••••••••" 
              defaultValue={rememberedLogin.password}
              autoComplete="current-password"
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

        <label className="remember-me-row">
          <input
            type="checkbox"
            name="rememberMe"
            checked={rememberMe}
            onChange={(event) => setRememberMe(event.target.checked)}
          />
          <span>Remember me</span>
        </label>

        <button type="submit" className="btn-primary w-full mt-6 mb-8" disabled={isLoading}>
          {isLoading ? 'Authenticating...' : 'Log In'}
        </button>

        <p className="auth-footer">
          New to MarketScope? <span onClick={() => setCurrentView('register')}>Create Account</span>
        </p>
      </form>
    </div>
  );

  const renderRegister = () => (
    <div className="fade-in">
      <h2 style={{ color: 'white' }}>Create Account</h2>
      <p className="auth-subtitle" style={{ color: 'white' }}>Start analyzing Panabo's markets today.</p>

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
          <label>Cellphone Number</label>
          <input type="tel" name="cellphone_number" placeholder="09XX XXX XXXX" />
        </div>

        <div className="input-group">
          <label>Address</label>
          <input type="text" name="address" placeholder="Barangay, City" />
        </div>

        <div className="input-group">
          <label>Primary Business Interest</label>
          <input type="text" name="primary_business" placeholder="e.g., Pharmacy / Food Kiosk" />
        </div>

        <div className="input-group">
          <label>Birthday</label>
          <input type="date" name="birthday" />
        </div>

        <div className="input-group">
          <label>Age</label>
          <input type="number" name="age" min="0" max="120" placeholder="Optional if birthday is set" />
        </div>

        <div className="input-group">
          <label>Profile Picture</label>
          <input
            className="upload-input-hidden"
            ref={registerAvatarInputRef}
            type="file"
            accept="image/*"
            tabIndex={-1}
            onChange={async (event) => {
              const file = event.target.files?.[0];
              if (!file) {
                setRegisterAvatarDataUrl('');
                setRegisterAvatarFileName('');
                return;
              }

              if (file.size > 2 * 1024 * 1024) {
                setErrorMsg('Profile picture must be 2MB or smaller.');
                event.target.value = '';
                return;
              }

              try {
                setIsAvatarReading(true);
                const dataUrl = await readFileAsDataUrl(file);
                setErrorMsg('');
                setRegisterAvatarDataUrl(dataUrl);
                setRegisterAvatarFileName(file.name);
              } catch (error) {
                setErrorMsg(error.message || 'Unable to read selected image.');
              } finally {
                setIsAvatarReading(false);
                event.target.blur();
              }
            }}
          />
          <button
            type="button"
            className="upload-trigger"
            onClick={() => registerAvatarInputRef.current?.click()}
            onMouseDown={(event) => event.preventDefault()}
          >
            <UploadIcon />
            <span>{registerAvatarFileName ? 'Change image' : 'Upload image'}</span>
          </button>
          <p className="upload-file-name">
            {registerAvatarFileName ? `Selected: ${registerAvatarFileName}` : 'No image selected'}
          </p>
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

        <button type="submit" className="btn-primary w-full mt-4 mb-8" disabled={isLoading || isAvatarReading}>
          {isLoading ? 'Creating Account...' : 'Create Account'}
        </button>

        <p className="auth-footer">
          Already have an account? <span onClick={() => setCurrentView('login')}>Log In</span>
        </p>
      </form>
    </div>
  );

  return (
    <div className={`auth-container ${currentView === 'hero' ? 'view-hero' : currentView === 'register' ? 'view-register' : 'view-login'}`}>
      {/* Hero View */}
      {currentView === 'hero' && (
        <div className="auth-hero">
          {renderHero()}
        </div>
      )}

      {/* Register & Login Views */}
      {currentView !== 'hero' && (
        <>
          <div className="auth-hero">
            {renderHero()}
          </div>

          {/* Form Side */}
          <div className="auth-form-wrapper">
            {currentView === 'register' && renderRegister()}
            {currentView === 'login' && renderLogin()}
          </div>
        </>
      )}
    </div>
  );
}