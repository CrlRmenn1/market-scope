import React, { useEffect, useMemo, useState } from 'react';

const steps = [
  {
    title: 'Welcome to MarketScope',
    description: 'This quick guide will help you run your first location scan in under one minute.',
    icon: (
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
        <circle cx="12" cy="12" r="10" />
        <path d="M8 12h8" />
        <path d="M12 8v8" />
      </svg>
    )
  },
  {
    title: '1. Drop a Pin on the Map',
    description: 'On the Map tab, tap any location or available space inside Panabo city boundary, then press Lock on this location.',
    icon: (
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
        <path d="M12 2c-3.31 0-6 2.69-6 6 0 4.2 4.64 9.14 5.89 10.41a1.5 1.5 0 0 0 2.12 0C13.36 17.14 18 12.2 18 8c0-3.31-2.69-6-6-6z" />
        <circle cx="12" cy="8" r="2.5" />
      </svg>
    )
  },
  {
    title: '2. Run Your Analysis',
    description: 'Choose your business type and radius, then tap Analyze. You will get zoning, hazard, saturation, and demand scores.',
    icon: (
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
        <path d="M3 3v18h18" />
        <path d="M7 14l3-3 3 2 4-5" />
        <circle cx="7" cy="14" r="1" />
        <circle cx="10" cy="11" r="1" />
        <circle cx="13" cy="13" r="1" />
        <circle cx="17" cy="8" r="1" />
      </svg>
    )
  },
  {
    title: '3. Review and Save Results',
    description: 'Open the report to view full details, then revisit your saved scans from the History tab anytime.',
    icon: (
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
        <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
        <path d="M14 2v6h6" />
        <path d="M9 13h6" />
        <path d="M9 17h6" />
      </svg>
    )
  }
];

export default function OnboardingModal({ isOpen, onClose }) {
  const [stepIndex, setStepIndex] = useState(0);
  const [doNotShowAgain, setDoNotShowAgain] = useState(false);
  const [isVisible, setIsVisible] = useState(false);

  const step = useMemo(() => steps[stepIndex], [stepIndex]);
  const isLastStep = stepIndex === steps.length - 1;

  useEffect(() => {
    if (isOpen) {
      setStepIndex(0);
      setDoNotShowAgain(false);

      const frame = window.requestAnimationFrame(() => {
        setIsVisible(true);
      });

      return () => {
        window.cancelAnimationFrame(frame);
      };
    }

    setIsVisible(false);
  }, [isOpen]);

  if (!isOpen) return null;

  return (
    <div className={`onboarding-overlay ${isVisible ? 'is-visible' : ''}`} role="presentation" onClick={() => onClose(doNotShowAgain)}>
      <div className="onboarding-modal" role="dialog" aria-modal="true" aria-labelledby="onboarding-title" onClick={(event) => event.stopPropagation()}>
        <div key={stepIndex} className="onboarding-step-card">
          <div className="onboarding-progress" aria-hidden="true">
            {steps.map((_, idx) => (
              <span key={idx} className={`onboarding-dot ${idx === stepIndex ? 'active' : ''}`} />
            ))}
          </div>

          <div className="onboarding-icon-wrap">{step.icon}</div>
          <p className="onboarding-step-label">Quick Start Guide</p>
          {stepIndex === 0 && (
            <p className="onboarding-purpose">
              We analyze business location viability using zoning, flood risk, demand, and competitor signals. Our aim is to help Panabo MSMEs choose safer, higher-potential spots faster.
            </p>
          )}
          <h3 id="onboarding-title" className="onboarding-title">{step.title}</h3>
          <p className="onboarding-description">{step.description}</p>
        </div>

        <label className="onboarding-checkbox-row">
          <input
            type="checkbox"
            checked={doNotShowAgain}
            onChange={(event) => setDoNotShowAgain(event.target.checked)}
          />
          <span>Do not show me again</span>
        </label>

        <div className="onboarding-actions">
          <button type="button" className="onboarding-btn secondary" onClick={() => onClose(doNotShowAgain)}>Skip</button>
          {stepIndex > 0 && (
            <button type="button" className="onboarding-btn ghost" onClick={() => setStepIndex((prev) => Math.max(0, prev - 1))}>
              Back
            </button>
          )}
          {isLastStep ? (
            <button type="button" className="onboarding-btn primary" onClick={() => onClose(doNotShowAgain)}>Got It</button>
          ) : (
            <button type="button" className="onboarding-btn primary" onClick={() => setStepIndex((prev) => Math.min(steps.length - 1, prev + 1))}>
              Next
            </button>
          )}
        </div>
      </div>
    </div>
  );
}
