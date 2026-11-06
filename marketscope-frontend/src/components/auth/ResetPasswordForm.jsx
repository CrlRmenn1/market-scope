import React, { useState } from 'react';
import { AuthAlert, AuthHeading, AuthInput } from './AuthField';
import PasswordField from './PasswordField';
import { MIN_PASSWORD_LENGTH, errorDetail, postJson } from './authApi';

// Two steps: ask for the email, then take the emailed code and the new password.
export default function ResetPasswordForm({ initialEmail, focusTitle, onReset }) {
  const [step, setStep] = useState('email');
  const [email, setEmail] = useState(initialEmail);
  const [notice, setNotice] = useState('');
  const [errorMsg, setErrorMsg] = useState('');
  const [confirmError, setConfirmError] = useState('');
  const [isLoading, setIsLoading] = useState(false);

  const requestCode = async () => {
    setErrorMsg('');
    setNotice('');
    setIsLoading(true);
    try {
      const { ok, data } = await postJson('/forgot-password', { email });
      if (!ok) throw new Error(errorDetail(data, "The code couldn't be sent. Try again in a moment."));
      setNotice(`If an account exists for ${email}, we sent it a 6-digit code. Check your inbox and spam folder.`);
      setStep('code');
    } catch (error) {
      setErrorMsg(error.message);
    } finally {
      setIsLoading(false);
    }
  };

  const handleEmailSubmit = (event) => {
    event.preventDefault();
    requestCode();
  };

  const handleCodeSubmit = async (event) => {
    event.preventDefault();
    const fields = event.currentTarget.elements;
    setErrorMsg('');
    setConfirmError('');

    if (fields.new_password.value !== fields.confirm_password.value) {
      setConfirmError("Passwords don't match. Retype your new password.");
      fields.confirm_password.focus();
      return;
    }

    setIsLoading(true);
    try {
      const { ok, data } = await postJson('/reset-password', {
        email,
        code: fields.code.value.trim(),
        new_password: fields.new_password.value,
      });
      if (!ok) throw new Error(errorDetail(data, "Your password couldn't be reset. Check the code and try again."));
      onReset(email);
    } catch (error) {
      setErrorMsg(error.message);
    } finally {
      setIsLoading(false);
    }
  };

  if (step === 'email') {
    return (
      <>
        <AuthHeading title="Reset your password" subtitle="Enter your account email and we'll send you a 6-digit code." focusOnMount={focusTitle} />
        <form className="auth-form" onSubmit={handleEmailSubmit}>
          <AuthInput
            id="reset-email"
            label="Email"
            type="email"
            name="email"
            inputMode="email"
            autoComplete="email"
            placeholder="juan@business.com"
            value={email}
            onChange={(event) => setEmail(event.target.value)}
            required
          />
          <AuthAlert>{errorMsg}</AuthAlert>
          <button type="submit" className="auth-button" disabled={isLoading}>
            {isLoading ? 'Sending code...' : 'Send code'}
          </button>
        </form>
      </>
    );
  }

  return (
    <>
      <AuthHeading key="code-step" title="Enter your code" subtitle="Then choose a new password." focusOnMount />
      <AuthAlert tone="success">{notice}</AuthAlert>

      <form className="auth-form" onSubmit={handleCodeSubmit}>
        <AuthInput
          id="reset-code"
          label="6-digit code"
          type="text"
          name="code"
          inputMode="numeric"
          autoComplete="one-time-code"
          pattern="[0-9]{6}"
          maxLength={6}
          title="Enter the 6 digits from the email"
          required
        />
        <PasswordField
          id="reset-new-password"
          label="New password"
          name="new_password"
          autoComplete="new-password"
          minLength={MIN_PASSWORD_LENGTH}
          hint={`At least ${MIN_PASSWORD_LENGTH} characters.`}
          required
        />
        <PasswordField
          id="reset-confirm-password"
          label="Confirm new password"
          name="confirm_password"
          autoComplete="new-password"
          error={confirmError}
          required
        />

        <AuthAlert>{errorMsg}</AuthAlert>

        <button type="submit" className="auth-button" disabled={isLoading}>
          {isLoading ? 'Resetting password...' : 'Reset password'}
        </button>
      </form>

      <div className="auth-actions-row">
        <button type="button" className="auth-link" onClick={requestCode} disabled={isLoading}>Send a new code</button>
        <button
          type="button"
          className="auth-link auth-link-quiet"
          onClick={() => {
            setErrorMsg('');
            setStep('email');
          }}
        >
          Use a different email
        </button>
      </div>
    </>
  );
}
