import React, { useRef, useState } from 'react';
import { ArrowUpTrayIcon, ChevronRightIcon } from '@heroicons/react/24/outline';
import { PANABO_BARANGAYS, PANABO_CITY, PANABO_REGION } from '../../constants/panaboBarangays';
import { PRIVACY_POLICY_TITLE, PRIVACY_POLICY_VERSION } from '../../content/privacyPolicy';
import { todayYmd } from '../../utils/age';
import { BUSINESS_TYPE_OPTIONS } from '../../utils/businessTypes';
import { AuthAlert, AuthHeading, AuthInput, AuthSelect, FieldError } from './AuthField';
import PasswordField from './PasswordField';
import { MIN_PASSWORD_LENGTH, errorDetail, postJson } from './authApi';

const MAX_AVATAR_BYTES = 2 * 1024 * 1024;

const STRENGTH_LEVELS = [
  { label: 'Weak', tone: 'weak' },
  { label: 'Weak', tone: 'weak' },
  { label: 'Fair', tone: 'fair' },
  { label: 'Strong', tone: 'strong' },
  { label: 'Strong', tone: 'strong' },
];

const scorePassword = (password) => [
  password.length > 5,
  password.length > 8,
  /[A-Z]/.test(password),
  /[0-9]/.test(password),
].filter(Boolean).length;

const readFileAsDataUrl = (file) => new Promise((resolve, reject) => {
  const reader = new FileReader();
  reader.onload = () => resolve(String(reader.result || ''));
  reader.onerror = () => reject(new Error("That image couldn't be read. Try a different file."));
  reader.readAsDataURL(file);
});

function PasswordStrength({ password }) {
  if (!password) return null;
  const score = scorePassword(password);
  const { label, tone } = STRENGTH_LEVELS[score];
  return (
    <div className="auth-strength">
      <div className="auth-strength-track" aria-hidden="true">
        <div className={`auth-strength-fill auth-strength-${tone}`} style={{ width: `${Math.max(score, 1) * 25}%` }} />
      </div>
      <p className="auth-hint">Password strength: {label}</p>
    </div>
  );
}

export default function RegisterForm({ focusTitle, onLoginSuccess, onLogin, onOpenPolicy }) {
  const [password, setPassword] = useState('');
  const [avatar, setAvatar] = useState({ dataUrl: '', fileName: '' });
  const [isAvatarReading, setIsAvatarReading] = useState(false);
  const [hasConsented, setHasConsented] = useState(false);
  const [errors, setErrors] = useState({});
  const [isLoading, setIsLoading] = useState(false);
  const avatarInputRef = useRef(null);

  const handleAvatarChange = async (event) => {
    const input = event.target;
    const file = input.files?.[0];
    if (!file) return;

    if (!['image/png', 'image/jpeg', 'image/webp', 'image/gif'].includes(file.type)) {
      setErrors((current) => ({ ...current, avatar: 'Choose a JPG, PNG, WebP or GIF image.' }));
      input.value = '';
      return;
    }
    if (file.size > MAX_AVATAR_BYTES) {
      setErrors((current) => ({ ...current, avatar: 'Choose an image that is 2MB or smaller.' }));
      input.value = '';
      return;
    }

    setIsAvatarReading(true);
    try {
      const dataUrl = await readFileAsDataUrl(file);
      setAvatar({ dataUrl, fileName: file.name });
      setErrors((current) => ({ ...current, avatar: '' }));
    } catch (error) {
      setErrors((current) => ({ ...current, avatar: error.message }));
    } finally {
      setIsAvatarReading(false);
    }
  };

  const removeAvatar = () => {
    setAvatar({ dataUrl: '', fileName: '' });
    if (avatarInputRef.current) avatarInputRef.current.value = '';
  };

  const handleSubmit = async (event) => {
    event.preventDefault();
    const fields = event.currentTarget.elements;
    setErrors({});

    if (fields.password.value !== fields.confirm.value) {
      setErrors({ confirm: "Passwords don't match. Retype your password." });
      fields.confirm.focus();
      return;
    }
    if (!hasConsented) {
      setErrors({ consent: `Agree to the ${PRIVACY_POLICY_TITLE} to create your account.` });
      fields.privacy_consent.focus();
      return;
    }

    setIsLoading(true);
    try {
      const { ok, data } = await postJson('/register', {
        first_name: fields.first_name.value,
        last_name: fields.last_name.value,
        email: fields.email.value,
        password: fields.password.value,
        primary_business: fields.primary_business.value,
        cellphone_number: fields.cellphone_number.value,
        street: fields.street.value,
        barangay: fields.barangay.value,
        birthday: fields.birthday.value || null,
        avatar_url: avatar.dataUrl || null,
        privacy_consent: hasConsented,
        privacy_policy_version: PRIVACY_POLICY_VERSION,
      });
      if (!ok) throw new Error(errorDetail(data, "Your account couldn't be created. Check your details and try again."));
      onLoginSuccess(data.user, data);
    } catch (error) {
      setErrors({ form: error.message });
    } finally {
      setIsLoading(false);
    }
  };

  // A field can only be invalid inside the closed section if it was filled in and
  // the section closed again. Open it, or the browser has nothing to point at.
  const revealInvalidField = (event) => {
    const section = event.target.closest('details');
    if (section) section.open = true;
  };

  return (
    <>
      <AuthHeading title="Create your account" subtitle="Start scanning locations in Panabo." focusOnMount={focusTitle} />

      <form className="auth-form" onSubmit={handleSubmit} onInvalidCapture={revealInvalidField}>
        <div className="auth-field-pair">
          <AuthInput id="register-first-name" label="First name" type="text" name="first_name" autoComplete="given-name" maxLength={120} placeholder="Juan" required />
          <AuthInput id="register-last-name" label="Last name" type="text" name="last_name" autoComplete="family-name" maxLength={120} placeholder="Dela Cruz" required />
        </div>

        <AuthInput id="register-email" label="Email" type="email" name="email" inputMode="email" autoComplete="email" placeholder="juan@business.com" required />

        <AuthSelect id="register-business" label="Primary business interest" name="primary_business" defaultValue="" required>
          <option value="" disabled>Select a business type</option>
          {BUSINESS_TYPE_OPTIONS.map((option) => (
            <option key={option.value} value={option.value}>{option.label}</option>
          ))}
        </AuthSelect>

        <div className="auth-field-group">
          <PasswordField
            id="register-password"
            label="Password"
            name="password"
            autoComplete="new-password"
            minLength={MIN_PASSWORD_LENGTH}
            hint={`At least ${MIN_PASSWORD_LENGTH} characters.`}
            value={password}
            onChange={(event) => setPassword(event.target.value)}
            required
          />
          <PasswordStrength password={password} />
        </div>

        <PasswordField
          id="register-confirm"
          label="Confirm password"
          name="confirm"
          autoComplete="new-password"
          error={errors.confirm}
          required
        />

        <details className="auth-details">
          <summary className="auth-details-summary">
            <span>
              <span className="auth-details-title">Add more details (optional)</span>
              <span className="auth-details-text">Cellphone, address, birthday and photo</span>
            </span>
            <ChevronRightIcon className="auth-details-chevron" aria-hidden="true" />
          </summary>

          <div className="auth-details-body">
            <AuthInput id="register-cellphone" label="Cellphone number" type="tel" name="cellphone_number" inputMode="tel" autoComplete="tel" placeholder="09XX XXX XXXX" />

            <fieldset className="auth-fieldset">
              <legend className="auth-legend">Address</legend>
              <p className="auth-hint">City and region are filled in for you. If you live outside Panabo, leave your address blank.</p>
              <AuthInput id="register-street" label="Street" type="text" name="street" autoComplete="address-line1" placeholder="House no. and street" />
              <AuthSelect id="register-barangay" label="Barangay" name="barangay" defaultValue="" autoComplete="off">
                <option value="">Select a barangay</option>
                {PANABO_BARANGAYS.map((barangay) => (
                  <option key={barangay} value={barangay}>{barangay}</option>
                ))}
              </AuthSelect>
              <div className="auth-field-pair">
                <AuthInput id="register-city" label="City" className="auth-input-readonly" type="text" value={PANABO_CITY} readOnly />
                <AuthInput id="register-region" label="Region" className="auth-input-readonly" type="text" value={PANABO_REGION} readOnly />
              </div>
            </fieldset>

            <AuthInput id="register-birthday" label="Birthday" type="date" name="birthday" autoComplete="bday" min="1900-01-01" max={todayYmd()} />

            <div className="auth-field">
              <span className="auth-label" id="register-photo-label">Profile picture</span>
              <input
                ref={avatarInputRef}
                className="upload-input-hidden"
                type="file"
                accept="image/png,image/jpeg,image/webp,image/gif"
                tabIndex={-1}
                aria-hidden="true"
                onChange={handleAvatarChange}
              />
              <div className="auth-photo">
                {avatar.dataUrl && <img className="auth-photo-preview" src={avatar.dataUrl} alt="Selected profile" />}
                <button
                  type="button"
                  className="auth-button-secondary"
                  aria-describedby="register-photo-label"
                  onClick={() => avatarInputRef.current?.click()}
                >
                  <ArrowUpTrayIcon aria-hidden="true" />
                  {avatar.dataUrl ? 'Change photo' : 'Upload photo'}
                </button>
                {avatar.dataUrl && (
                  <button type="button" className="auth-link auth-link-quiet" onClick={removeAvatar}>Remove</button>
                )}
              </div>
              <p className="auth-hint auth-photo-name">{avatar.fileName || 'JPG or PNG, 2MB or smaller.'}</p>
              <FieldError id="register-photo-error">{errors.avatar}</FieldError>
            </div>
          </div>
        </details>

        <div className="auth-consent">
          <label className="auth-check auth-check-top">
            <input
              type="checkbox"
              name="privacy_consent"
              checked={hasConsented}
              aria-required="true"
              aria-invalid={errors.consent ? true : undefined}
              aria-describedby={errors.consent ? 'register-consent-error' : undefined}
              onChange={(event) => {
                setHasConsented(event.target.checked);
                if (event.target.checked) setErrors((current) => ({ ...current, consent: '' }));
              }}
            />
            <span>
              I have read and agree to the {PRIVACY_POLICY_TITLE}, and I consent to MarketScope collecting and using my
              personal information as described.
            </span>
          </label>
          <button type="button" className="auth-link auth-consent-link" onClick={onOpenPolicy}>
            Read the {PRIVACY_POLICY_TITLE}
          </button>
          <FieldError id="register-consent-error">{errors.consent}</FieldError>
        </div>

        <AuthAlert>{errors.form}</AuthAlert>

        <button type="submit" className="auth-button" disabled={isLoading || isAvatarReading}>
          {isLoading ? 'Creating account...' : 'Create account'}
        </button>
      </form>

      <p className="auth-switch">
        Already have an account?{' '}
        <button type="button" className="auth-link" onClick={onLogin}>Log in</button>
      </p>
    </>
  );
}
