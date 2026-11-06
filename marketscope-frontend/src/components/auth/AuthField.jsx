import React, { useEffect, useRef } from 'react';
import { CheckCircleIcon, ExclamationCircleIcon } from '@heroicons/react/24/solid';
import BrandMark from '../layout/BrandMark';

export function BrandLockup({ className = '' }) {
  return (
    <span className={`auth-brand ${className}`.trim()}>
      <BrandMark />
      <span className="auth-brand-name">
        Market<span className="auth-brand-highlight">Scope</span>
      </span>
    </span>
  );
}

// The page title. Takes focus when the person moved here from another auth
// screen, so screen readers announce it, without opening a phone's keyboard.
export function AuthHeading({ title, subtitle, focusOnMount = false }) {
  const titleRef = useRef(null);

  useEffect(() => {
    if (focusOnMount) titleRef.current?.focus();
  }, [focusOnMount]);

  return (
    <div className="auth-heading">
      <h1 className="auth-title" ref={titleRef} tabIndex={-1}>{title}</h1>
      {subtitle && <p className="auth-subtitle">{subtitle}</p>}
    </div>
  );
}

export function AuthAlert({ tone = 'error', children }) {
  if (!children) return null;
  const Icon = tone === 'success' ? CheckCircleIcon : ExclamationCircleIcon;
  return (
    <div className={`auth-alert auth-alert-${tone}`} role={tone === 'error' ? 'alert' : 'status'}>
      <Icon className="auth-alert-icon" aria-hidden="true" />
      <span>{children}</span>
    </div>
  );
}

export function FieldError({ id, children }) {
  if (!children) return null;
  return (
    <p className="auth-field-error" id={id} role="alert">
      <ExclamationCircleIcon className="auth-field-error-icon" aria-hidden="true" />
      <span>{children}</span>
    </p>
  );
}

// Label, hint and error around a control. `children` receives the aria props the
// control needs so the hint and error are announced with it.
export function FieldShell({ id, label, hint, error, labelAction, children }) {
  const hintId = hint ? `${id}-hint` : null;
  const errorId = error ? `${id}-error` : null;
  const describedBy = [hintId, errorId].filter(Boolean).join(' ') || undefined;

  return (
    <div className="auth-field">
      <div className="auth-label-row">
        <label className="auth-label" htmlFor={id}>{label}</label>
        {labelAction}
      </div>
      {children({ 'aria-describedby': describedBy, 'aria-invalid': error ? true : undefined })}
      {hint && <p className="auth-hint" id={hintId}>{hint}</p>}
      <FieldError id={errorId}>{error}</FieldError>
    </div>
  );
}

export function AuthInput({ id, label, hint, error, labelAction, className = '', ...inputProps }) {
  return (
    <FieldShell id={id} label={label} hint={hint} error={error} labelAction={labelAction}>
      {(ariaProps) => <input id={id} className={`auth-input ${className}`.trim()} {...ariaProps} {...inputProps} />}
    </FieldShell>
  );
}

export function AuthSelect({ id, label, hint, error, children, ...selectProps }) {
  return (
    <FieldShell id={id} label={label} hint={hint} error={error}>
      {(ariaProps) => <select id={id} className="auth-input auth-select" {...ariaProps} {...selectProps}>{children}</select>}
    </FieldShell>
  );
}
