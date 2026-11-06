import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { authFetch } from '../lib/api';
import AreaMap from '../components/trends/AreaMap';
import SuggestionCard from '../components/trends/SuggestionCard';
import TrendPreferencesGate from '../components/onboarding/TrendPreferencesGate';
import { getMissingTrendPreferenceFields } from '../utils/trendPreferences';

// While any business type is queued or scanning, re-read the saved results this often.
const POLL_INTERVAL_MS = 5000;
const MAX_SUGGESTIONS = 5;
const CLOSEST_MATCHES = 3;

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

// The opening area: the strongest suggestion backed by enough competitor data, then
// the strongest suggestion of any kind, then the best score.
const pickDefaultArea = (areas) => {
  const rank = ({ headline }) => [
    headline?.is_suggestion && headline.competitor_data !== 'thin' ? 1 : 0,
    headline?.is_suggestion ? 1 : 0,
    headline?.score ?? -1
  ];
  return [...areas].sort((first, second) => {
    const [a, b] = [rank(first), rank(second)];
    return b[0] - a[0] || b[1] - a[1] || b[2] - a[2] || first.name.localeCompare(second.name);
  })[0];
};

function ScanStatus({ scan }) {
  if (!scan) return null;
  const { is_active: isActive, total_types: total, finished_types: finished, current, failed } = scan;

  return (
    <div className="mt-3 text-sm text-[var(--text-muted)]">
      {isActive ? (
        <>
          <p className="tabular-nums">
            {finished} of {total} business types ready.
            {current && current.total > 0 && ` Scanning ${current.business_name}: ${current.done} / ${current.total} spots.`}
          </p>
          <div className="trends-progress mt-2" role="progressbar" aria-label="Business types scanned" aria-valuemin={0} aria-valuemax={total} aria-valuenow={finished}>
            <span style={{ width: `${total > 0 ? Math.max(Math.round((finished / total) * 100), 4) : 4}%` }} />
          </div>
        </>
      ) : (
        <p className="tabular-nums">
          {finished} of {total} business types scanned
          {scan.oldest_seconds_ago !== null && ` · oldest result ${formatAge(scan.oldest_seconds_ago)}`}
        </p>
      )}
      {failed?.length > 0 && (
        <p className="mt-2 text-[var(--trend-down)]">
          The last scan failed for {failed.map((item) => item.business_name).join(', ')}
          {failed.some((item) => item.has_older_results) ? ', so older results are shown where they exist.' : '.'}
          {' '}It will try again later, or use Rescan now.
        </p>
      )}
    </div>
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
  const [pickedAreaName, setPickedAreaName] = useState(null);
  const [onlyMySetup, setOnlyMySetup] = useState(false);
  const [failedPolls, setFailedPolls] = useState(0);

  const activeMissingPreferences = useMemo(() => {
    if (Array.isArray(missingTrendPreferences)) {
      return missingTrendPreferences;
    }
    return getMissingTrendPreferenceFields(user);
  }, [missingTrendPreferences, user]);

  const hasMissingPreferences = activeMissingPreferences.length > 0;
  const settings = trends?.settings || {};
  const scan = trends?.scan || null;
  const primary = trends?.primary || null;
  const isScanActive = Boolean(scan?.is_active);
  const setupName = String(trends?.profile?.preferred_setup || '').replace('-', ' ');
  const reachMeters = settings.competition_reach_meters ?? 800;

  // The setup filter only hides businesses. The order stays the backend's.
  const areas = useMemo(() => (trends?.areas || []).map((area) => {
    const businesses = onlyMySetup ? area.businesses.filter((entry) => entry.fits_setup) : area.businesses;
    return { ...area, shown: businesses, headline: businesses[0] || null };
  }), [trends, onlyMySetup]);

  const selectedArea = useMemo(
    () => areas.find((area) => area.name === pickedAreaName) || (areas.length > 0 ? pickDefaultArea(areas) : null),
    [areas, pickedAreaName]
  );

  const suggestions = (selectedArea?.shown || []).filter((entry) => entry.is_suggestion).slice(0, MAX_SUGGESTIONS);
  const closestMatches = suggestions.length === 0 ? (selectedArea?.shown || []).slice(0, CLOSEST_MATCHES) : [];

  // GET only reads saved scan results (it queues a scan when they are missing or old).
  const loadTrends = useCallback(async ({ silent = false } = {}) => {
    if (!userId) return;
    if (!silent) setLoading(true);

    try {
      const response = await authFetch(`/users/${userId}/trends`, { cache: 'no-store' });
      const data = await response.json();
      if (!response.ok) throw new Error(readErrorMessage(data, 'Unable to load business suggestions.'));
      setTrends(data);
      setError('');
    } catch (fetchError) {
      if (!silent) setTrends(null);
      setError(fetchError.message || 'Unable to load business suggestions.');
      // Nothing else changes after a failed poll, so this is what schedules the next one.
      if (silent) setFailedPolls((count) => count + 1);
    } finally {
      if (!silent) setLoading(false);
    }
  }, [userId]);

  const rescanNow = async () => {
    if (!userId) return;
    setRescanning(true);
    try {
      const response = await authFetch(`/users/${userId}/trends/rescan`, { method: 'POST' });
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

  // Cards only carry a summary; the full saved report is fetched on demand.
  const viewSpotReport = async (entry) => {
    if (!onOpenReport) return;
    const resultId = entry.best_spot.result_id;
    setOpeningResultId(resultId);
    try {
      const response = await authFetch(`/trends/results/${resultId}`, { cache: 'no-store' });
      const data = await response.json();
      if (!response.ok) throw new Error(readErrorMessage(data, 'Unable to open this report.'));
      onOpenReport(data.report);
    } catch (openError) {
      setError(openError.message || 'Unable to open this report.');
    } finally {
      setOpeningResultId(null);
    }
  };

  const showSpotOnMap = (entry) => {
    onRunAnalysis?.({ lat: Number(entry.best_spot.lat), lng: Number(entry.best_spot.lng) }, entry.business_key);
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
  }, [isScanActive, trends, failedPolls, loadTrends]);

  const renderCards = (entries, titleOf, keyOf) => (
    <div className="mt-3 grid items-start gap-4 md:grid-cols-2">
      {entries.map((entry, index) => (
        <SuggestionCard
          key={keyOf(entry)}
          entry={entry}
          title={titleOf(entry)}
          rank={index + 1}
          reachMeters={reachMeters}
          isOpening={openingResultId === entry.best_spot.result_id}
          onViewReport={viewSpotReport}
          onShowOnMap={showSpotOnMap}
        />
      ))}
    </div>
  );

  return (
    <div className="profile-page page-enter min-h-full">
      <div className="mx-auto flex w-full max-w-8xl flex-col gap-4 px-6 pb-28 pt-4 sm:px-8">
        <div className="profile-card fade-in p-5 text-left">
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div>
              <p className="eyebrow-label mb-2">Market Radar</p>
              <h2 className="profile-name mb-2 text-2xl font-semibold tracking-tight text-[var(--text-main)] sm:text-3xl">Business Trend Suggestions</h2>
              <p className="profile-email text-sm text-[var(--text-muted)]">
                Pick an area of Panabo to see which businesses fit it best.
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

          <p className="mt-3 text-sm text-[var(--text-muted)]">
            Based on current map, zoning and competitor records. This is a snapshot, not growth over time, and doesn&apos;t guarantee success.
          </p>

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
              <li>Every business type is scanned in the background across listed spaces, landmarks and points in the zones where it is allowed, using the same engine as a manual scan.</li>
              <li>Each spot is grouped under its nearest named place, so an area is &quot;around Gredu&quot;, not an official barangay boundary.</li>
              <li>A business&apos;s area score is the average of its best {settings.area_top_spots ?? 3} spots there. It is a suggestion when that lands in the Highly Suitable class ({settings.high_chance_min_score ?? 68} or higher).</li>
              <li>A business with fewer than {settings.min_known_competitors ?? 6} competitors on record citywide ranks lower and carries a warning, because low competition may only mean missing data.</li>
              <li>&quot;Possible market gap&quot; means few recorded competitors where nearby demand looks strong. Confirm it in person.</li>
              <li>Results are saved and reused for {settings.fresh_hours ?? 24} hours. Your preferences only tag and filter businesses. They never change a score.</li>
            </ol>
          )}

          {!loading && <ScanStatus scan={scan} />}
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
            <p className="mt-1 text-[var(--text-muted)]">Complete your preferences so suggestions can be matched to you.</p>
            <button
              type="button"
              className="mt-3 inline-flex items-center justify-center rounded-xl bg-[var(--btn-primary-bg)] px-4 py-2 text-sm font-semibold text-[var(--btn-primary-text)] transition hover:bg-[var(--btn-primary-hover)]"
              onClick={() => setShowPreferenceGate(true)}
            >
              Complete Preferences
            </button>
          </div>
        )}

        {!loading && trends && areas.length === 0 && (
          <div className="history-empty-state">
            <div>
              <p className="history-empty-title">{isScanActive ? 'The first scan is running' : 'No suggestions yet'}</p>
              <p className="history-empty-subtitle">
                {isScanActive
                  ? 'Suggestions appear here as each business type finishes.'
                  : 'No scan results or area names could be loaded. Try Rescan now.'}
              </p>
            </div>
          </div>
        )}

        {!loading && selectedArea && (
          <section className="text-left">
            <div className="grid items-start gap-4 lg:grid-cols-5">
              <div className="data-card p-3 lg:sticky lg:top-4 lg:col-span-2">
                <AreaMap areas={areas} selectedName={selectedArea.name} onSelect={setPickedAreaName} />
                <p className="mt-2 text-xs leading-4 text-[var(--text-muted)]">
                  Each number is the area&apos;s top business score. Green is a suggestion, a dashed ring means thin competitor data, and gray means no suggestion.
                </p>
              </div>

              <div className="lg:col-span-3">
                <div className="flex flex-wrap items-end gap-3">
                  <label className="min-w-[200px] flex-1 text-sm text-[var(--text-main)]">
                    <span className="mb-1 block text-xs font-medium uppercase tracking-[0.08em] text-[var(--text-muted)]">Area</span>
                    <select
                      className="min-h-[44px] w-full rounded-xl border border-[var(--border-color)] bg-[var(--bg-sheet)] px-3 py-2.5 text-sm text-[var(--text-main)] outline-none focus:border-[var(--accent)] focus:ring-2 focus:ring-[var(--focus-ring)]"
                      value={selectedArea.name}
                      onChange={(event) => setPickedAreaName(event.target.value)}
                    >
                      {areas.map((area) => (
                        <option key={area.name} value={area.name}>Around {area.name}</option>
                      ))}
                    </select>
                  </label>
                  {setupName && (
                    <label className="inline-flex min-h-[44px] items-center gap-2 text-sm text-[var(--text-main)]">
                      <input type="checkbox" className="h-4 w-4 accent-[var(--accent)]" checked={onlyMySetup} onChange={(event) => setOnlyMySetup(event.target.checked)} />
                      Only {setupName} businesses
                    </label>
                  )}
                </div>

                <h3 className="mt-4 text-xl font-semibold text-[var(--text-main)]">What could open around {selectedArea.name}</h3>
                <p className="mt-1 text-sm tabular-nums text-[var(--text-muted)]">{selectedArea.spots} spots checked in this area</p>

                {selectedArea.shown.length === 0 && (
                  <p className="mt-3 rounded-xl bg-[var(--trend-neutral-bg)] px-3 py-2.5 text-sm text-[var(--text-main)]">
                    {onlyMySetup
                      ? `No ${setupName} business is allowed in the spots checked here. Clear the filter to see the others.`
                      : 'No business type is allowed in the spots checked here.'}
                  </p>
                )}
                {suggestions.length > 0 && renderCards(suggestions, (entry) => entry.business_name, (entry) => entry.business_key)}
                {closestMatches.length > 0 && (
                  <>
                    <p className="mt-3 rounded-xl bg-[var(--trend-neutral-bg)] px-3 py-2.5 text-sm text-[var(--text-main)]">
                      Nothing reaches Highly Suitable around {selectedArea.name}. These are the closest matches, not suggestions.
                    </p>
                    {renderCards(closestMatches, (entry) => entry.business_name, (entry) => entry.business_key)}
                  </>
                )}
              </div>
            </div>
          </section>
        )}

        {!loading && primary && (
          <section className="mt-4 text-left">
            <p className="eyebrow-label mb-1">Your business</p>
            <h3 className="text-xl font-semibold text-[var(--text-main)]">Best areas for {primary.business_name}</h3>
            <SetupNote setupMatch={primary.setup_match} />
            {primary.best_areas?.length > 0
              ? renderCards(primary.best_areas, (entry) => `Around ${entry.area_name}`, (entry) => entry.area_name)
              : <p className="mt-2 text-sm text-[var(--text-muted)]">{isScanActive ? 'Waiting for this business type to finish scanning.' : 'No permitted spots have been scanned for this business yet.'}</p>}
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
