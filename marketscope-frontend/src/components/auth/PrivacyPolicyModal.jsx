import React, { useEffect, useRef } from 'react';
import { XMarkIcon } from '@heroicons/react/24/outline';
import Modal from '../common/Modal';
import {
  PRIVACY_POLICY_INTRO,
  PRIVACY_POLICY_IS_DRAFT,
  PRIVACY_POLICY_SECTIONS,
  PRIVACY_POLICY_TITLE,
  PRIVACY_POLICY_VERSION,
} from '../../content/privacyPolicy';

export default function PrivacyPolicyModal({ isOpen, onClose }) {
  const closeRef = useRef(null);
  const bodyRef = useRef(null);

  // Modal doesn't manage focus: start on Close, keep Tab inside the dialog, close
  // on Escape, and return to whatever opened it.
  useEffect(() => {
    if (!isOpen) return undefined;

    const opener = document.activeElement;
    closeRef.current?.focus();

    const handleKeyDown = (event) => {
      if (event.key === 'Escape') {
        onClose();
        return;
      }
      if (event.key !== 'Tab') return;
      event.preventDefault();
      const next = document.activeElement === closeRef.current ? bodyRef.current : closeRef.current;
      next?.focus();
    };

    document.addEventListener('keydown', handleKeyDown);
    return () => {
      document.removeEventListener('keydown', handleKeyDown);
      opener?.focus?.();
    };
  }, [isOpen, onClose]);

  return (
    <Modal
      isOpen={isOpen}
      onClose={onClose}
      variant="center"
      overlayClassName="auth-policy-overlay"
      panelClassName="auth-policy-panel"
      ariaLabelledBy="privacy-policy-title"
    >
      <div className="auth-policy-header">
        <div>
          <h2 className="auth-policy-title" id="privacy-policy-title">{PRIVACY_POLICY_TITLE}</h2>
          <p className="auth-hint">Version {PRIVACY_POLICY_VERSION}</p>
        </div>
        <button type="button" className="auth-back" ref={closeRef} onClick={onClose} aria-label="Close policy">
          <XMarkIcon aria-hidden="true" />
        </button>
      </div>

      <div className="auth-policy-body" ref={bodyRef} tabIndex={0} role="region" aria-labelledby="privacy-policy-title">
        {PRIVACY_POLICY_IS_DRAFT && (
          <p className="auth-policy-draft">Draft for review. Highlighted items still need to be filled in.</p>
        )}
        <p>{PRIVACY_POLICY_INTRO}</p>
        {PRIVACY_POLICY_SECTIONS.map((section) => (
          <section key={section.heading}>
            <h3 className="auth-policy-heading">{section.heading}</h3>
            {section.body}
          </section>
        ))}
      </div>
    </Modal>
  );
}
