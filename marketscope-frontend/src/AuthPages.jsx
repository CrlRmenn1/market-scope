import React, { useRef, useState, useEffect } from 'react';
import './Auth.css';
import { apiUrl } from './api';

export default function AuthPages({ onLoginSuccess, onAdminLoginSuccess, initialView = 'landing', onAuthPagesMounted }) {
  const AUTH_VIEW_KEY = 'marketscope_auth_view';
  const getInitialAuthView = () => {
    if (initialView === 'login') return 'login';
    const savedView = localStorage.getItem(AUTH_VIEW_KEY);
    if (savedView === 'hero' || savedView === 'register' || savedView === 'login') {
      return savedView;
    }
    return 'hero';
  };

  const [currentView, setCurrentView] = useState(getInitialAuthView);
  const [isBurgerOpen, setIsBurgerOpen] = useState(false);
  const [password, setPassword] = useState('');
  const [passwordStrength, setPasswordStrength] = useState(0);
  const [errorMsg, setErrorMsg] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [rememberMe, setRememberMe] = useState(false);
  const [rememberedLogin, setRememberedLogin] = useState({ email: '', password: '' });
  const [showForgotPassword, setShowForgotPassword] = useState(false);
  const [forgotEmail, setForgotEmail] = useState('');
  const [forgotNewPassword, setForgotNewPassword] = useState('');
  const [forgotConfirmPassword, setForgotConfirmPassword] = useState('');
  const [forgotMsg, setForgotMsg] = useState('');
  const [forgotError, setForgotError] = useState('');
  const [isResetLoading, setIsResetLoading] = useState(false);

  // NEW: State to track password visibility
  const [showPassword, setShowPassword] = useState(false);
  const [showConfirmPassword, setShowConfirmPassword] = useState(false);
  const [registerAvatarDataUrl, setRegisterAvatarDataUrl] = useState('');
  const [registerAvatarFileName, setRegisterAvatarFileName] = useState('');
  const [isAvatarReading, setIsAvatarReading] = useState(false);
  const registerAvatarInputRef = useRef(null);
  const authContainerRef = useRef(null);
  const authFormWrapperRef = useRef(null);
  const savedScrollTopRef = useRef(0);
  const viewportBaselineRef = useRef(0);
  const keyboardOpenRef = useRef(false);

  const authPanelClass = 'fade-in !w-full !max-w-[520px] space-y-5 !rounded-[30px] !border !border-white/10 !bg-slate-950/80 !p-6 !shadow-[0_30px_90px_rgba(2,6,23,0.55)] !backdrop-blur-xl sm:!p-8';
  const authSectionTitleClass = 'text-3xl font-semibold tracking-tight !text-white sm:text-[2.15rem]';
  const authSectionSubtitleClass = 'text-sm text-slate-200/90';
  const authLabelClass = 'mb-2 block text-[0.72rem] font-semibold uppercase tracking-[0.22em] text-slate-300';
  const authInputClass = 'mt-0 w-full rounded-xl border border-white/10 bg-slate-950/80 px-4 py-3 text-sm text-white placeholder:text-slate-500 outline-none transition focus:border-violet-400 focus:ring-2 focus:ring-violet-400/20';
  const authPrimaryButtonClass = 'btn-primary w-full rounded-xl bg-gradient-to-r from-violet-600 via-violet-500 to-fuchsia-500 px-4 py-3 text-sm font-semibold shadow-lg shadow-violet-500/25 transition hover:from-violet-500 hover:to-fuchsia-400';
  const authSecondaryButtonClass = 'btn-secondary w-full rounded-xl border border-violet-300/50 bg-white/5 px-4 py-3 text-sm font-semibold text-violet-100 transition hover:bg-violet-500/10';

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

  useEffect(() => {
    localStorage.setItem(AUTH_VIEW_KEY, currentView);
  }, [currentView]);

  useEffect(() => {
    const container = authContainerRef.current;
    const formWrapper = authFormWrapperRef.current;
    if (!container || !formWrapper || currentView !== 'register') return;

    const isTextLikeField = (element) => {
      if (!element) return false;
      const tagName = element.tagName;
      return tagName === 'INPUT' || tagName === 'TEXTAREA' || tagName === 'SELECT';
    };

    const handleFocusIn = (event) => {
      if (isTextLikeField(event.target)) {
        savedScrollTopRef.current = formWrapper.scrollTop;
      }
    };

    const restoreScrollPosition = () => {
      window.setTimeout(() => {
        const activeElement = document.activeElement;
        if (!container.contains(activeElement)) {
          formWrapper.scrollTo({ top: savedScrollTopRef.current, behavior: 'auto' });
        }
      }, 50);
    };

    container.addEventListener('focusin', handleFocusIn);
    container.addEventListener('focusout', restoreScrollPosition);

    return () => {
      container.removeEventListener('focusin', handleFocusIn);
      container.removeEventListener('focusout', restoreScrollPosition);
    };
  }, [currentView]);

  useEffect(() => {
    const formWrapper = authFormWrapperRef.current;
    if (!formWrapper) return;

    const viewport = window.visualViewport;
    const getHeight = () => viewport?.height || window.innerHeight;

    viewportBaselineRef.current = Math.max(viewportBaselineRef.current, getHeight());

    const recoverLayout = () => {
      window.requestAnimationFrame(() => {
        const active = document.activeElement;
        if (active && (active.tagName === 'INPUT' || active.tagName === 'TEXTAREA' || active.tagName === 'SELECT')) {
          return;
        }

        window.scrollTo(0, 0);
        document.documentElement.scrollTop = 0;
        document.body.scrollTop = 0;

        const restoreTop = currentView === 'register' ? savedScrollTopRef.current : 0;
        formWrapper.scrollTo({ top: restoreTop, behavior: 'auto' });
      });
    };

    const handleViewportResize = () => {
      const currentHeight = getHeight();
      viewportBaselineRef.current = Math.max(viewportBaselineRef.current, currentHeight);
      const keyboardNowOpen = currentHeight < (viewportBaselineRef.current - 120);

      if (keyboardOpenRef.current && !keyboardNowOpen) {
        recoverLayout();
      }

      keyboardOpenRef.current = keyboardNowOpen;
    };

    const handleWindowResize = () => {
      viewportBaselineRef.current = Math.max(viewportBaselineRef.current, getHeight());
      recoverLayout();
    };

    viewport?.addEventListener('resize', handleViewportResize);
    window.addEventListener('resize', handleWindowResize);
    window.addEventListener('orientationchange', handleWindowResize);

    return () => {
      viewport?.removeEventListener('resize', handleViewportResize);
      window.removeEventListener('resize', handleWindowResize);
      window.removeEventListener('orientationchange', handleWindowResize);
    };
  }, [currentView]);

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

  const handleResetPassword = async (e) => {
    e.preventDefault();
    setForgotMsg('');
    setForgotError('');

    if (!forgotEmail || !forgotNewPassword || !forgotConfirmPassword) {
      setForgotError('Please complete all fields.');
      return;
    }

    if (forgotNewPassword !== forgotConfirmPassword) {
      setForgotError('New password and confirm password do not match.');
      return;
    }

    if (forgotNewPassword.length < 6) {
      setForgotError('New password must be at least 6 characters.');
      return;
    }

    setIsResetLoading(true);

    try {
      const response = await fetch(apiUrl('/reset-password-direct'), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          email: forgotEmail,
          new_password: forgotNewPassword
        })
      });

      let payload = {};
      try {
        payload = await response.json();
      } catch {
        payload = {};
      }

      if (!response.ok) {
        setForgotError(payload.detail || 'Unable to reset password right now.');
        return;
      }

      setForgotMsg(payload.detail || 'Password reset successful. You can now log in.');
      setForgotNewPassword('');
      setForgotConfirmPassword('');
    } catch {
      setForgotError('Network error while resetting password. Please try again.');
    } finally {
      setIsResetLoading(false);
    }
  };

  const renderHero = () => (
    <div className="hero-container relative isolate flex min-h-[100dvh] w-full overflow-hidden bg-[radial-gradient(circle_at_top_left,rgba(168,85,247,0.28),transparent_34%),radial-gradient(circle_at_top_right,rgba(59,7,100,0.72),transparent_32%),linear-gradient(180deg,#22073a_0%,#0b1120_45%,#050816_100%)] px-5 py-4 text-center sm:px-8 lg:px-12">
      <div className="pointer-events-none absolute inset-0 opacity-60 [background-image:linear-gradient(rgba(255,255,255,0.04)_1px,transparent_1px),linear-gradient(90deg,rgba(255,255,255,0.04)_1px,transparent_1px)] [background-size:24px_24px]" />
      <div className="pointer-events-none absolute left-1/2 top-1/2 h-[560px] w-[560px] -translate-x-1/2 -translate-y-1/2 rounded-full bg-violet-500/12 blur-3xl" />
      <div className="hero-logo-corner !left-4 !top-[calc(env(safe-area-inset-top)+12px)] !z-10 !gap-2.5 !rounded-full !border !border-white/10 !bg-black/20 !px-3 !py-2 !backdrop-blur-xl">
        <div className="brand-mark">
          <div className="lens-left"></div>
          <div className="lens-center">
            <div className="lens-reflection"></div>
          </div>
          <div className="lens-right"></div>
        </div>
        <span className="hero-logo-text">
          Market<span className="hero-logo-highlight">Scope</span>
        </span>
      </div>

      <div className="hero-header !right-4 !top-[calc(env(safe-area-inset-top)+12px)] !z-40">
        <button className="burger-menu-btn" onClick={() => setIsBurgerOpen(!isBurgerOpen)} aria-label="Open menu">
          <span></span>
          <span></span>
          <span></span>
        </button>
        {isBurgerOpen && (
          <div className="burger-menu">
            <button
              className="burger-item"
              onClick={() => {
                setCurrentView('login');
                setIsBurgerOpen(false);
              }}
            >
              Login
            </button>
            <button className="burger-item">About Us</button>
            <button className="burger-item">How Does This Work</button>
          </div>
        )}
      </div>

      <div className="hero-content relative z-10 flex max-w-[680px] flex-col items-center gap-5 px-4 py-8 sm:gap-6 sm:px-6 lg:py-0">
        <div className="hero-badge rounded-full border border-violet-300/30 bg-violet-500/15 px-4 py-2 text-[0.7rem] font-bold uppercase tracking-[0.18em] text-violet-100 shadow-[0_10px_30px_rgba(168,85,247,0.15)]">MCDA ENGINE V1.0</div>
        <h1 className="hero-title max-w-[11ch] text-[clamp(2.7rem,7vw,4.5rem)] font-black leading-[0.96] tracking-[-0.06em] text-white drop-shadow-[0_12px_30px_rgba(0,0,0,0.35)]">Discover<br/>Panabo's<br/>Hidden Markets.</h1>
        <p className="hero-description max-w-[28rem] text-base leading-7 text-violet-100/90 sm:text-lg">The geospatial viability engine designed exclusively for local entrepreneurs and MSMEs.</p>
        <p className="hero-instruction rounded-full border border-violet-200/20 bg-white/5 px-4 py-2 text-sm font-semibold leading-6 text-violet-50 shadow-[0_10px_35px_rgba(0,0,0,0.18)] backdrop-blur-md">Quick Start: Tap Get Started, drop a pin, and scan market potential in seconds.</p>
        <button className="get-started-btn mt-2 rounded-xl bg-gradient-to-r from-violet-600 via-violet-500 to-fuchsia-500 px-8 py-4 text-base font-semibold text-white shadow-[0_16px_40px_rgba(168,85,247,0.35)] transition duration-300 hover:-translate-y-0.5 hover:shadow-[0_22px_48px_rgba(168,85,247,0.45)]" onClick={() => setCurrentView('register')}>
          Get Started
        </button>
      </div>
    </div>
  );

  const renderLogin = () => (
    <div className={authPanelClass}>
      <h2 className={authSectionTitleClass}>Welcome Back</h2>
      <p className={authSectionSubtitleClass}>Access your MarketScope dashboard.</p>
      
      {errorMsg && <div className="error-alert">{errorMsg}</div>}

      <form onSubmit={handleLogin} className="mt-6 space-y-4">
        <div className="input-group">
          <label className={authLabelClass}>Email Address</label>
          <input className={authInputClass} type="email" name="email" placeholder="msme@panabo.com" defaultValue={rememberedLogin.email} autoComplete="username" required />
        </div>

        <div className="input-group">
          <label className={authLabelClass}>Password</label>
          <div className="password-input-wrapper">
            <input 
              className={authInputClass}
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

        <button
          type="button"
          className="forgot-password-link"
          onClick={() => {
            setShowForgotPassword((prev) => !prev);
            setForgotError('');
            setForgotMsg('');
            if (!forgotEmail && rememberedLogin.email) {
              setForgotEmail(rememberedLogin.email);
            }
          }}
        >
          {showForgotPassword ? 'Hide password reset' : 'Forgot password?'}
        </button>

        {showForgotPassword && (
          <div className="forgot-password-panel rounded-xl border border-violet-400/30 bg-violet-950/20 p-3">
            <p className="forgot-password-note text-xs text-violet-100">Enter your account email and set a new password.</p>
            <div className="input-group forgot-input-group">
              <label className={authLabelClass}>Reset Email</label>
              <input
                className={authInputClass}
                type="email"
                name="forgotEmail"
                placeholder="msme@panabo.com"
                value={forgotEmail}
                onChange={(event) => setForgotEmail(event.target.value)}
                autoComplete="email"
                required
              />
            </div>

            <div className="input-group forgot-input-group">
              <label className={authLabelClass}>New Password</label>
              <input
                className={authInputClass}
                type="password"
                name="forgotNewPassword"
                placeholder="At least 6 characters"
                value={forgotNewPassword}
                onChange={(event) => setForgotNewPassword(event.target.value)}
                autoComplete="new-password"
              />
            </div>

            <div className="input-group forgot-input-group">
              <label className={authLabelClass}>Confirm New Password</label>
              <input
                className={authInputClass}
                type="password"
                name="forgotConfirmPassword"
                placeholder="Repeat new password"
                value={forgotConfirmPassword}
                onChange={(event) => setForgotConfirmPassword(event.target.value)}
                autoComplete="new-password"
              />
            </div>

            <button
              type="button"
              className={authSecondaryButtonClass}
              disabled={isResetLoading}
              onClick={handleResetPassword}
            >
              {isResetLoading ? 'Resetting password...' : 'Reset Password'}
            </button>

            {forgotMsg && <div className="info-alert mt-2">{forgotMsg}</div>}
            {forgotError && <div className="error-alert mt-2">{forgotError}</div>}
          </div>
        )}

        <button type="submit" className={authPrimaryButtonClass} disabled={isLoading}>
          {isLoading ? 'Authenticating...' : 'Log In'}
        </button>

        <p className="auth-footer">
          New to MarketScope? <span className="!text-white" onClick={() => setCurrentView('register')}>Create Account</span>
        </p>
      </form>
    </div>
  );

  const renderRegister = () => (
    <div className={authPanelClass}>
      <h2 className={authSectionTitleClass}>Create Account</h2>
      <p className={authSectionSubtitleClass}>Start analyzing Panabo's markets today.</p>

      {errorMsg && <div className="error-alert">{errorMsg}</div>}

      <form onSubmit={handleRegister} className="mt-6 space-y-4">
        <div className="input-group">
          <label className={authLabelClass}>Full Name</label>
          <input className={authInputClass} type="text" name="full_name" placeholder="Juan Dela Cruz" required />
        </div>

        <div className="input-group">
          <label className={authLabelClass}>Email Address</label>
          <input className={authInputClass} type="email" name="email" placeholder="juan@business.com" required />
        </div>

        <div className="input-group">
          <label className={authLabelClass}>Cellphone Number</label>
          <input className={authInputClass} type="tel" name="cellphone_number" placeholder="09XX XXX XXXX" />
        </div>

        <div className="input-group">
          <label className={authLabelClass}>Address</label>
          <input className={authInputClass} type="text" name="address" placeholder="Barangay, City" />
        </div>

        <div className="input-group">
          <label className={authLabelClass}>Primary Business Interest</label>
          <input className={authInputClass} type="text" name="primary_business" placeholder="e.g., Pharmacy / Food Kiosk" />
        </div>

        <div className="input-group">
          <label className={authLabelClass}>Birthday</label>
          <div className="field-hint" id="birthday-hint">Tap the field to open the calendar</div>
          <input className={authInputClass} type="date" name="birthday" aria-describedby="birthday-hint" title="Tap to choose your birthday" />
        </div>

        <div className="input-group">
          <label className={authLabelClass}>Age</label>
          <input className={authInputClass} type="number" name="age" min="0" max="120" placeholder="Optional if birthday is set" />
        </div>

        <div className="input-group">
          <label className={authLabelClass}>Profile Picture</label>
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
            className="upload-trigger inline-flex w-full items-center justify-center gap-2 rounded-xl border border-violet-300/40 bg-white/5 px-4 py-3 text-sm font-semibold text-violet-100 transition hover:bg-violet-500/10"
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
          <label className={authLabelClass}>Password</label>
          <div className="password-input-wrapper">
            <input 
              className={authInputClass}
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
          <label className={authLabelClass}>Confirm Password</label>
          <div className="password-input-wrapper">
            <input 
              className={authInputClass}
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

        <button type="submit" className={authPrimaryButtonClass} disabled={isLoading || isAvatarReading}>
          {isLoading ? 'Creating Account...' : 'Create Account'}
        </button>

        <p className="auth-footer">
          Already have an account? <span className="!text-white" onClick={() => setCurrentView('login')}>Log In</span>
        </p>
      </form>
    </div>
  );

  if (currentView === 'hero') {
    return (
      <div className="auth-container view-hero" ref={authContainerRef}>
        <div className="auth-hero">
          {renderHero()}
        </div>
      </div>
    );
  }

  return (
    <div className={`auth-container ${currentView === 'login' ? 'view-login' : 'view-landing'}`} ref={authContainerRef}>
      <div className="mobile-auth-hero">
        {currentView === 'register' && (
          <button className="hero-side-back-btn" onClick={() => setCurrentView('hero')} aria-label="Back to landing">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <line x1="19" y1="12" x2="5" y2="12"></line>
              <polyline points="12 19 5 12 12 5"></polyline>
            </svg>
          </button>
        )}
        <div className="mobile-hero-text">
          <div className="hero-badge mb-4">MCDA ENGINE V1.0</div>
          <h2>Discover<br />Panabo's<br />Hidden Markets.</h2>
          <p>The geospatial viability engine built for local entrepreneurs and MSMEs.</p>
        </div>
      </div>

      <div className="auth-hero">
        {currentView === 'register' && (
          <button className="hero-side-back-btn" onClick={() => setCurrentView('hero')} aria-label="Back to landing">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <line x1="19" y1="12" x2="5" y2="12"></line>
              <polyline points="12 19 5 12 12 5"></polyline>
            </svg>
          </button>
        )}
        <div className="hero-text">
          <div className="hero-badge mb-6">MCDA ENGINE V1.0</div>
          <h1>Discover<br/>Panabo's<br/>Hidden Markets.</h1>
          <p>The ultimate geospatial viability engine designed<br/>exclusively for local entrepreneurs and MSMEs.</p>
        </div>
      </div>

      <div className="auth-form-wrapper" ref={authFormWrapperRef}>
        {currentView === 'register' && renderRegister()}
        {currentView === 'login' && renderLogin()}
      </div>
    </div>
  );
}