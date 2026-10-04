import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { apiUrl } from '../lib/api';
import TrendPreferencesGate from '../components/onboarding/TrendPreferencesGate';
import TrendSpotCard from '../components/trends/TrendSpotCard';
import { getMissingTrendPreferenceFields } from '../utils/trendPreferences';

// While any business type is queued or scanning, re-read the saved results this often.
const POLL_INTERVAL_MS = 5000;
const ACTIVE_SCAN_STATES = ['scanning', 'queued'];

const formatAge = (seconds) => {
  if (seconds === null || seconds === undefined) return null;
  if (seconds < 60) return 'just now';
  if (seconds < 3600) return `${Math.round(seconds / 60)} min ago`;
  if (seconds < 86400) return `${Math.round(seconds / 3600)} h ago`;
  return `${Math.round(seconds / 86400)} d ago`;
};

const readErrorMessage = (data, fallback) => {
  const detail = data?.detail;
  if (typeof detail === 'string') return detail;
  if (detail?.message && Array.isArray(detail?.missing_fields) && detail.missing_fields.length > 0) {
    return `${detail.message} Missing: ${detail.missing_fields.join(', ')}`;
  }
  return fallback;
};

function ScanStatus({ scan, minScore }) {
  const { state, progress } = scan;

  if (state === 'scanning') {
    const total = progress?.total || 0;
    const done = progress?.done || 0;
    return (
      <div className="mt-3">
        <p className="text-sm text-[var(--text-muted)]">
          {total > 0 ? `Scanning spots in the background... ${done} / ${total}` : 'Preparing the background scan...'}
        </p>
        <div className="trends-progress mt-2" role="progressbar" aria-valuemin={0} aria-valuemax={total} aria-valuenow={done}>
          <span style={{ width: `${total > 0 ? Math.round((done / total) * 100) : 4}%` }} />
        </div>
      </div>
    );
  }

  if (state === 'queued') {
    return <p className="mt-3 text-sm text-[var(--text-muted)]">Waiting in the scan queue...</p>;
  }

  if (state === 'failed') {
    return <p className="mt-3 text-sm text-[var(--trend-down)]">The last scan failed{scan.error ? `: ${scan.error}` : '.'} Try Rescan now.</p>;
  }

  if (state === 'missing') {
    return <p className="mt-3 text-sm text-[var(--text-muted)]">Not scanned yet.</p>;
  }

  return (
    <p className="mt-3 text-sm tabular-nums text-[var(--text-muted)]">
      {scan.scanned_spots} spots scanned · {scan.high_chance_spots} scored {minScore}+ · updated {formatAge(scan.scanned_seconds_ago)}
      {state === 'stale' && ' (older than the refresh window, a rescan will run soon)'}
    </p>
  );
}

// Only shown when the primary business isn't usually run in the preferred setup.
function SetupNote({ setupMatch }) {
  if (!setupMatch || setupMatch.matches) return null;
  return (
    <p className="mt-2 rounded-xl bg-[var(--trend-neutral-bg)] px-3 py-2 text-sm text-[var(--text-main)]">
      {setupMatch.detail}
    </p>
  );
}

export default function Trends({ user, onOpenReport, onRunAnalysis, missingTrendPreferences, onPreferencesSaved }) {
  const userId = user?.user_id || user?.id;
  const [loading, setLoading] = useState(Boolean(userId));
  const [rescanning, setRescanning] = useState(false);
  const [error, setError] = useState('');
  const [trends, setTrends] = useState(null);
  const [openingResultId, setOpeningResultId] = useState(null);
  const [showHowItWorks, setShowHowItWorks] = useState(false);
  const [showPreferenceGate, setShowPreferenceGate] = useState(false);

  const activeMissingPreferences = useMemo(() => {
    if (Array.isArray(missingTrendPreferences)) {
      return missingTrendPreferences;
    }
    return getMissingTrendPreferenceFields(user);
  }, [missingTrendPreferences, user]);

  const hasMissingPreferences = activeMissingPreferences.length > 0;
  const settings = trends?.settings || {};
  const minScore = settings.high_chance_min_score ?? 70;
  const primarySection = trends?.primary || null;
  const setupMatches = trends?.setup_matches || null;
  const setupSections = Array.isArray(setupMatches?.sections) ? setupMatches.sections : [];
  const setupName = String(setupMatches?.setup || '').replace('-', ' ');
  const isScanActive = ACTIVE_SCAN_STATES.includes(primarySection?.scan?.state) || Boolean(setupMatches?.is_scanning);

  // GET only reads saved scan results (it queues a scan when they are missing or old).
  const loadTrends = useCallback(async ({ silent = false } = {}) => {
    if (!userId) return;
    if (!silent) setLoading(true);

    try {
      const response = await fetch(apiUrl(`/users/${userId}/trends`), { cache: 'no-store' });
      const data = await response.json();
      if (!response.ok) throw new Error(readErrorMessage(data, 'Unable to load trend analysis.'));
      setTrends(data);
      setError('');
    } catch (fetchError) {
      if (!silent) setTrends(null);
      setError(fetchError.message || 'Unable to load trend analysis.');
    } finally {
      if (!silent) setLoading(false);
    }
  }, [userId]);

  const rescanNow = async () => {
    if (!userId) return;
    setRescanning(true);
    try {
      const response = await fetch(apiUrl(`/users/${userId}/trends/rescan`), { method: 'POST' });
      const data = await response.json();
      if (!response.ok) throw new Error(readErrorMessage(data, 'Unable to start a rescan.'));
      setTrends(data);
      setError('');
    } catch (rescanError) {
      setError(rescanError.message || 'Unable to start a rescan.');
    } finally {
      setRescanning(false);
    }
  };

  // The card list only carries a summary; the full saved report is fetched on demand.
  const viewSpotReport = async (spot) => {
    if (!onOpenReport) return;
    setOpeningResultId(spot.result_id);
    try {
      const response = await fetch(apiUrl(`/trends/results/${spot.result_id}`), { cache: 'no-store' });
      const data = await response.json();
      if (!response.ok) throw new Error(readErrorMessage(data, 'Unable to open this report.'));
      onOpenReport(data.report);
    } catch (openError) {
      setError(openError.message || 'Unable to open this report.');
    } finally {
      setOpeningResultId(null);
    }
  };

  const showSpotOnMap = (spot, businessKey) => {
    onRunAnalysis?.({ lat: Number(spot.lat), lng: Number(spot.lng) }, businessKey);
  };

  useEffect(() => {
    if (!userId) return;

    if (hasMissingPreferences) {
      setShowPreferenceGate(true);
      setLoading(false);
      setError('');
      setTrends(null);
      return;
    }

    setShowPreferenceGate(false);
    loadTrends();
  }, [userId, hasMissingPreferences, loadTrends]);

  useEffect(() => {
    if (!isScanActive) return undefined;
    const timer = setTimeout(() => loadTrends({ silent: true }), POLL_INTERVAL_MS);
    return () => clearTimeout(timer);
  }, [isScanActive, trends, loadTrends]);

  const renderSpots = (section) => {
    const spots = Array.isArray(section.spots) ? section.spots : [];
    if (spots.length === 0) return null;

    const hasHighChance = spots.some((spot) => spot.is_high_chance);
    return (
      <>
        {!hasHighChance && (
          <p className="mt-3 rounded-xl bg-[var(--trend-neutral-bg)] px-3 py-2.5 text-sm text-[var(--text-main)]">
            No spot reached the high-chance score of {minScore}. These are the closest matches.
          </p>
        )}
        <div className="mt-3 grid items-start gap-4 lg:grid-cols-2">
          {spots.map((spot) => (
            <TrendSpotCard
              key={spot.result_id}
              spot={spot}
              isOpening={openingResultId === spot.result_id}
              onViewReport={viewSpotReport}
              onShowOnMap={(item) => showSpotOnMap(item, section.business_key)}
            />
          ))}
        </div>
      </>
    );
  };

  return (
    <div className="profile-page page-enter min-h-full">
      <div className="mx-auto flex w-full max-w-8xl flex-col gap-4 px-6 pb-28 pt-4 sm:px-8">
        <div className="profile-card fade-in p-5 text-left">
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div>
              <p className="eyebrow-label mb-2">Market Radar</p>
              <h2 className="profile-name mb-2 text-2xl font-semibold tracking-tight text-[var(--text-main)] sm:text-3xl">Business Trends</h2>
              <p className="profile-email text-sm text-[var(--text-muted)]">
                High-chance spots found by background scans for your business preferences.
              </p>
            </div>
            <button
              type="button"
              className="inline-flex min-h-[44px] items-center justify-center gap-2 rounded-xl border border-[var(--border-color)] bg-[var(--bg-sheet)] px-4 py-2.5 text-sm font-medium text-[var(--text-main)] transition hover:border-[var(--border-strong)] hover:bg-[var(--accent-hover)] disabled:cursor-not-allowed disabled:opacity-60"
              onClick={rescanNow}
              disabled={loading || rescanning || isScanActive || hasMissingPreferences}
            >
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true" className={rescanning || isScanActive ? 'animate-spin' : ''}>
                <path d="M21 12a9 9 0 1 1-2.64-6.36" /><path d="M21 3v6h-6" />
              </svg>
              {isScanActive ? 'Scanning...' : 'Rescan now'}
            </button>
          </div>

          <button
            type="button"
            className="mt-3 inline-flex items-center gap-1.5 text-sm font-medium text-[var(--accent)]"
            onClick={() => setShowHowItWorks((open) => !open)}
            aria-expanded={showHowItWorks}
          >
            How this works
            <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" aria-hidden="true" style={{ transform: showHowItWorks ? 'rotate(180deg)' : 'none', transition: 'transform 200ms ease' }}>
              <path d="m6 9 6 6 6-6" />
            </svg>
          </button>
          {showHowItWorks && (
            <ol className="trends-reasons mt-2 list-decimal">
              <li>Your primary business is scanned, plus every other business usually run in your preferred setup.</li>
              <li>For each one, the system scans listed spaces for rent or sale, landmark areas and points across the commercial zone in the background, using the same engine as a manual scan ({settings.radius_meters ?? 340} m radius).</li>
              <li>Every result is saved in the database and reused for {settings.fresh_hours ?? 24} hours, so logging in again does not rescan.</li>
              <li>Spots scoring {minScore} or higher count as high chance and are ranked by their viability score. Of the other businesses, the two with the best-scoring spot are shown.</li>
            </ol>
          )}
        </div>

        {loading && <div className="data-card p-4 text-sm text-[var(--text-muted)]">Loading saved scan results...</div>}

        {!loading && error && (
          <div className="data-card border border-[var(--border-color)] bg-[var(--trend-down-bg)] p-4 text-sm text-[var(--trend-down)]">
            {error}
          </div>
        )}

        {!loading && hasMissingPreferences && (
          <div className="data-card border border-[var(--border-color)] bg-[var(--trend-neutral-bg)] p-4 text-sm text-[var(--text-main)]">
            <p className="font-semibold">Trend preferences are not complete yet.</p>
            <p className="mt-1 text-[var(--text-muted)]">Complete your preferences so the system knows which businesses to scan for.</p>
            <button
              type="button"
              className="mt-3 inline-flex items-center justify-center rounded-xl bg-[var(--btn-primary-bg)] px-4 py-2 text-sm font-semibold text-[var(--btn-primary-text)] transition hover:bg-[var(--btn-primary-hover)]"
              onClick={() => setShowPreferenceGate(true)}
            >
              Complete Preferences
            </button>
          </div>
        )}

        {!loading && trends && !primarySection && !setupMatches?.total && (
          <div className="history-empty-state">
            <div>
              <p className="history-empty-title">No business type to scan yet</p>
              <p className="history-empty-subtitle">Pick a primary business in your profile to start the background scan.</p>
            </div>
          </div>
        )}

        {!loading && primarySection && (
          <section className="text-left">
            <p className="eyebrow-label mb-1">Your business</p>
            <h3 className="text-xl font-semibold text-[var(--text-main)]">Best spots for {primarySection.business_name}</h3>
            <SetupNote setupMatch={primarySection.setup_match} />
            <ScanStatus scan={primarySection.scan} minScore={minScore} />
            {renderSpots(primarySection)}
          </section>
        )}

        {!loading && setupMatches && (
          <section className="mt-4 flex flex-col gap-6 text-left">
            <div>
              <p className="eyebrow-label mb-1">Also fits your setup</p>
              <h3 className="text-lg font-semibold text-[var(--text-main)]">Other {setupName} businesses</h3>
              {setupMatches.total === 0 ? (
                <p className="mt-1 text-sm text-[var(--text-muted)]">No other business in our list is usually run as a {setupName}.</p>
              ) : (
                <p className="mt-1 text-sm tabular-nums text-[var(--text-muted)]">
                  {setupMatches.is_scanning
                    ? `Checked ${setupMatches.scanned} of ${setupMatches.total} ${setupName} businesses...`
                    : `The ${setupSections.length} of ${setupMatches.total} ${setupName} businesses with the best-scoring spots.`}
                </p>
              )}
            </div>
            {setupSections.map((section) => (
              <div key={section.business_key}>
                <h4 className="text-base font-semibold text-[var(--text-main)]">{section.business_name}</h4>
                <ScanStatus scan={section.scan} minScore={minScore} />
                {renderSpots({ ...section, spots: (section.spots || []).slice(0, 2) })}
              </div>
            ))}
          </section>
        )}
      </div>

      <TrendPreferencesGate
        isOpen={Boolean(hasMissingPreferences && showPreferenceGate)}
        user={user}
        onSaved={(updatedUser) => {
          onPreferencesSaved?.(updatedUser);
          setShowPreferenceGate(false);
        }}
        onLater={() => setShowPreferenceGate(false)}
      />
    </div>
  );
}
