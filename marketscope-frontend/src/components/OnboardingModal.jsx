import React, { useEffect, useState } from 'react';

const highlights = [
  {
    title: 'Tap the map, get a verdict',
    description: 'Any spot in Panabo scored 0-100 for business viability in about ten seconds.',
    icon: (
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
        <path d="M20 10c0 6-8 12-8 12s-8-6-8-12a8 8 0 0 1 16 0Z" />
        <circle cx="12" cy="10" r="3" />
      </svg>
    )
  },
  {
    title: 'Know before you commit',
    description: 'Zoning rules, flood risk, nearby competitors, and demand signals — checked in one scan.',
    icon: (
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
        <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10Z" />
        <path d="m9 12 2 2 4-4" />
      </svg>
    )
  },
  {
    title: 'Compare your options',
    description: 'Every scan lands in History, so you can weigh spot A against spot B with real numbers.',
    icon: (
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
        <path d="M3 3v18h18" />
        <path d="m19 9-5 5-4-4-3 3" />
      </svg>
    )
  }
];

export default function OnboardingModal({ isOpen, onClose, onStartTour }) {
  const [isVisible, setIsVisible] = useState(false);

  useEffect(() => {
    if (isOpen) {
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
    <div className={`onboarding-overlay ${isVisible ? 'is-visible' : ''}`} role="presentation" onClick={() => onClose()}>
      <div className="onboarding-modal" role="dialog" aria-modal="true" aria-labelledby="onboarding-title" onClick={(event) => event.stopPropagation()}>
        <div className="onboarding-step-card">
          <div className="brand-mark mx-auto mb-4" aria-hidden="true">
            <div className="lens-left" />
            <div className="lens-center">
              <div className="lens-reflection" />
            </div>
            <div className="lens-right" />
          </div>

          <p className="eyebrow-label mb-2 text-center">Welcome to MarketScope</p>
          <h3 id="onboarding-title" className="onboarding-title text-center">
            Find your next business location — with proof, not guesswork.
          </h3>

          <div className="onboarding-highlights mt-5 flex flex-col gap-3 text-left">
            {highlights.map((item) => (
              <div key={item.title} className="flex items-start gap-3">
                <span className="onboarding-highlight-icon" aria-hidden="true">{item.icon}</span>
                <div>
                  <p className="text-sm font-semibold text-[var(--text-main)]">{item.title}</p>
                  <p className="mt-0.5 text-xs leading-5 text-[var(--text-muted)]">{item.description}</p>
                </div>
              </div>
            ))}
          </div>
        </div>

        <div className="onboarding-actions mt-5 flex flex-col gap-2">
          {onStartTour && (
            <button
              type="button"
              className="inline-flex min-h-[48px] w-full items-center justify-center gap-2 rounded-xl bg-[var(--btn-primary-bg)] px-4 py-3 text-sm font-semibold text-[var(--btn-primary-text)] transition hover:bg-[var(--btn-primary-hover)]"
              onClick={onStartTour}
            >
              <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true">
                <circle cx="12" cy="12" r="3" /><path d="M12 2v3M12 19v3M2 12h3M19 12h3" />
              </svg>
              Show me — run my first scan
            </button>
          )}
          <button
            type="button"
            className="inline-flex min-h-[44px] w-full items-center justify-center rounded-xl border border-[var(--border-color)] bg-[var(--bg-sheet)] px-4 py-2.5 text-sm font-medium text-[var(--text-muted)] transition hover:border-[var(--border-strong)] hover:bg-[var(--accent-hover)] hover:text-[var(--text-main)]"
            onClick={() => onClose()}
          >
            I'll explore on my own
          </button>
        </div>
      </div>
    </div>
  );
}
