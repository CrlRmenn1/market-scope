import React, { useState } from 'react';
import { clearRememberedEmail, readRememberedEmail, saveRememberedEmail } from '../../utils/rememberedLogin';
import { AuthAlert, AuthHeading, AuthInput } from './AuthField';
import PasswordField from './PasswordField';
import { errorDetail, postJson } from './authApi';

export default function LoginForm({
  initialEmail,
  notice,
  focusTitle,
  onLoginSuccess,
  onAdminLoginSuccess,
  onForgotPassword,
  onCreateAccount,
  onOpenPolicy,
}) {
  const [email, setEmail] = useState(initialEmail);
  const [rememberEmail, setRememberEmail] = useState(() => Boolean(readRememberedEmail()));
  const [errorMsg, setErrorMsg] = useState('');
  const [isLoading, setIsLoading] = useState(false);

  const applyRememberChoice = () => {
    if (rememberEmail) saveRememberedEmail(email);
    else clearRememberedEmail();
  };

  const handleSubmit = async (event) => {
    event.preventDefault();
    setErrorMsg('');
    setIsLoading(true);
    const credentials = { email, password: event.currentTarget.elements.password.value };

    try {
      const user = await postJson('/login', credentials);
      if (user.ok) {
        applyRememberChoice();
        onLoginSuccess(user.data.user, user.data);
        return;
      }

      // Admins sign in through this same form.
      const shouldTryAdmin = user.status === 401 || user.status === 404;
      if (!shouldTryAdmin || !onAdminLoginSuccess) {
        throw new Error(errorDetail(user.data, 'Invalid email or password'));
      }

      const admin = await postJson('/admin/login', credentials);
      if (admin.ok) {
        applyRememberChoice();
        onAdminLoginSuccess(admin.data.admin);
        return;
      }
      if (admin.status === 404) {
        throw new Error('Admin login endpoint not found. Restart backend server and try again.');
      }
      throw new Error(errorDetail(admin.data, errorDetail(user.data, 'Invalid email or password')));
    } catch (error) {
      setErrorMsg(error.message);
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <>
      <AuthHeading title="Log in" subtitle="See your saved scans and trends." focusOnMount={focusTitle} />
      <AuthAlert tone="success">{notice}</AuthAlert>

      <form className="auth-form" onSubmit={handleSubmit}>
        <AuthInput
          id="login-email"
          label="Email"
          type="email"
          name="email"
          inputMode="email"
          autoComplete="username"
          placeholder="juan@business.com"
          value={email}
          onChange={(event) => setEmail(event.target.value)}
          required
        />

        <PasswordField
          id="login-password"
          label="Password"
          name="password"
          autoComplete="current-password"
          required
          labelAction={(
            <button type="button" className="auth-link auth-link-quiet" onClick={() => onForgotPassword(email)}>
              Forgot password?
            </button>
          )}
        />

        <label className="auth-check">
          <input type="checkbox" checked={rememberEmail} onChange={(event) => setRememberEmail(event.target.checked)} />
          <span>Remember my email</span>
        </label>

        <AuthAlert>{errorMsg}</AuthAlert>

        <button type="submit" className="auth-button" disabled={isLoading}>
          {isLoading ? 'Logging in...' : 'Log in'}
        </button>
      </form>

      <p className="auth-switch">
        New to MarketScope?{' '}
        <button type="button" className="auth-link" onClick={onCreateAccount}>Create account</button>
      </p>
      <p className="auth-switch auth-switch-small">
        <button type="button" className="auth-link auth-link-quiet" onClick={onOpenPolicy}>Data Privacy Policy</button>
      </p>
    </>
  );
}
