import React, { useState } from 'react';
import { EyeIcon, EyeSlashIcon } from '@heroicons/react/24/outline';
import { FieldShell } from './AuthField';

export default function PasswordField({ id, label, hint, error, labelAction, ...inputProps }) {
  const [isVisible, setIsVisible] = useState(false);
  const Icon = isVisible ? EyeSlashIcon : EyeIcon;

  return (
    <FieldShell id={id} label={label} hint={hint} error={error} labelAction={labelAction}>
      {(ariaProps) => (
        <div className="auth-password">
          <input
            id={id}
            className="auth-input auth-password-input"
            type={isVisible ? 'text' : 'password'}
            {...ariaProps}
            {...inputProps}
          />
          <button
            type="button"
            className="auth-password-toggle"
            aria-label={`Show ${label.toLowerCase()}`}
            aria-pressed={isVisible}
            onClick={() => setIsVisible((current) => !current)}
          >
            <Icon aria-hidden="true" />
          </button>
        </div>
      )}
    </FieldShell>
  );
}
