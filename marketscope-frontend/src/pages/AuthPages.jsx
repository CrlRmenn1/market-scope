import React, { useCallback, useEffect, useRef, useState } from 'react';
import { AnimatePresence, motion, useReducedMotion } from 'framer-motion';
import '../styles/auth.css';
import { EASE_STANDARD } from '../constants/motion';
import AuthShell from '../components/auth/AuthShell';
import LoginForm from '../components/auth/LoginForm';
import PrivacyPolicyModal from '../components/auth/PrivacyPolicyModal';
import RegisterForm from '../components/auth/RegisterForm';
import ResetPasswordForm from '../components/auth/ResetPasswordForm';
import { readRememberedEmail } from '../utils/rememberedLogin';

const AUTH_VIEW_KEY = 'marketscope_auth_view';

const getInitialAuthView = (initialView) => {
  if (initialView === 'login') return 'login';
  const savedView = localStorage.getItem(AUTH_VIEW_KEY);
  return savedView === 'register' || savedView === 'login' ? savedView : 'hero';
};

export default function AuthPages({ onLoginSuccess, onAdminLoginSuccess, initialView = 'landing', initialNotice = '', onAuthPagesMounted }) {
  const shouldReduceMotion = useReducedMotion();
  const [currentView, setCurrentView] = useState(() => getInitialAuthView(initialView));
  const [hasNavigated, setHasNavigated] = useState(false);
  const [email, setEmail] = useState(readRememberedEmail);
  const [loginNotice, setLoginNotice] = useState(initialNotice);
  const [isPolicyOpen, setIsPolicyOpen] = useState(false);
  const containerRef = useRef(null);

  useEffect(() => {
    if (onAuthPagesMounted) onAuthPagesMounted();
  }, [onAuthPagesMounted]);

  // The reset screen isn't saved: a reload there returns to where the person came from.
  useEffect(() => {
    if (currentView !== 'reset') localStorage.setItem(AUTH_VIEW_KEY, currentView);
    containerRef.current?.scrollTo?.({ top: 0 });
  }, [currentView]);

  const goTo = (view) => {
    setHasNavigated(true);
    setLoginNotice('');
    setCurrentView(view);
  };

  const openPolicy = useCallback(() => setIsPolicyOpen(true), []);
  const closePolicy = useCallback(() => setIsPolicyOpen(false), []);

  const viewTransition = { duration: shouldReduceMotion ? 0 : 0.2, ease: EASE_STANDARD };

  const renderForm = () => {
    if (currentView === 'register') {
      return (
        <RegisterForm
          focusTitle={hasNavigated}
          onLoginSuccess={onLoginSuccess}
          onLogin={() => goTo('login')}
          onOpenPolicy={openPolicy}
        />
      );
    }
    if (currentView === 'reset') {
      return (
        <ResetPasswordForm
          initialEmail={email}
          focusTitle={hasNavigated}
          onReset={(resetEmail) => {
            setEmail(resetEmail);
            setCurrentView('login');
            setLoginNotice('Password reset. Log in with your new password.');
          }}
        />
      );
    }
    return (
      <LoginForm
        initialEmail={email}
        notice={loginNotice}
        focusTitle={hasNavigated}
        onLoginSuccess={onLoginSuccess}
        onAdminLoginSuccess={onAdminLoginSuccess}
        onForgotPassword={(typedEmail) => {
          setEmail(typedEmail);
          goTo('reset');
        }}
        onCreateAccount={() => goTo('register')}
        onOpenPolicy={openPolicy}
      />
    );
  };

  return (
    <>
      <AnimatePresence mode="wait">
        {currentView === 'hero' ? (
          <motion.div
            key="hero"
            className="auth-container view-hero"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            transition={viewTransition}
          >
            <div className="auth-hero">
              <div className="hero-container relative isolate flex min-h-[100dvh] w-full overflow-hidden bg-[radial-gradient(circle_at_top_left,rgba(168,85,247,0.28),transparent_34%),radial-gradient(circle_at_top_right,rgba(59,7,100,0.72),transparent_32%),linear-gradient(180deg,#22073a_0%,#0b1120_45%,#050816_100%)] px-5 py-4 text-center sm:px-8 lg:px-12">
                <div className="pointer-events-none absolute inset-0 opacity-60 [background-image:linear-gradient(rgba(255,255,255,0.04)_1px,transparent_1px),linear-gradient(90deg,rgba(255,255,255,0.04)_1px,transparent_1px)] [background-size:24px_24px]" />

                <div className="hero-header">
                  <button type="button" className="hero-login-btn" onClick={() => goTo('login')}>Log in</button>
                </div>

                <div className="hero-content relative z-10 flex max-w-[680px] flex-col items-center gap-5 px-4 py-8 sm:gap-6 sm:px-6 lg:py-0">
                  <div className="hero-badge hero-badge-brand">
                    <div className="brand-mark hero-badge-mark" aria-hidden="true">
                      <div className="lens-left"></div>
                      <div className="lens-center">
                        <div className="lens-reflection"></div>
                      </div>
                      <div className="lens-right"></div>
                    </div>
                    <span className="hero-badge-logo-text">
                      Market<span className="hero-logo-highlight">Scope</span>
                    </span>
                  </div>
                  <h1 className="hero-title max-w-[11ch] text-[clamp(2.7rem,7vw,4.5rem)] font-black leading-[0.96] tracking-[-0.06em] text-white">Discover<br/>Panabo's<br/>Hidden Markets.</h1>
                  <p className="hero-description max-w-[28rem] text-base leading-7 text-white/70 sm:text-lg">The geospatial viability engine designed exclusively for local entrepreneurs and MSMEs.</p>
                  <p className="hero-instruction rounded-full border border-white/15 bg-white/10 px-4 py-2 text-sm font-semibold leading-6 text-white/90">Quick Start: Tap Get Started, drop a pin, and scan market potential in seconds.</p>
                  <button type="button" className="get-started-btn mt-2 rounded-xl bg-white px-8 py-4 text-base font-semibold text-neutral-900 transition duration-300 hover:-translate-y-0.5 hover:bg-neutral-200" onClick={() => goTo('register')}>
                    Get Started
                  </button>
                </div>
              </div>
            </div>
          </motion.div>
        ) : (
          <motion.div
            key="shell"
            className="auth-container"
            ref={containerRef}
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            transition={viewTransition}
          >
            <AuthShell
              onBack={() => goTo(currentView === 'reset' ? 'login' : 'hero')}
              backLabel={currentView === 'reset' ? 'Back to log in' : 'Back to home'}
            >
              <AnimatePresence mode="wait" initial={false}>
                <motion.div
                  key={currentView}
                  initial={{ opacity: 0 }}
                  animate={{ opacity: 1 }}
                  exit={{ opacity: 0 }}
                  transition={viewTransition}
                >
                  {renderForm()}
                </motion.div>
              </AnimatePresence>
            </AuthShell>
          </motion.div>
        )}
      </AnimatePresence>

      <PrivacyPolicyModal isOpen={isPolicyOpen} onClose={closePolicy} />
    </>
  );
}
