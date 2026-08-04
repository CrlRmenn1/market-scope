import React, { useEffect, useMemo, useState } from 'react';
import { apiUrl } from '../api';
import TrendPreferencesGate from '../components/TrendPreferencesGate';
import useIsDesktop from '../utils/useIsDesktop';

const REQUIRED_TREND_FIELDS = [
  'primary_business',
  'startup_capital',
  'preferred_setup',
  'target_payback_months'
];

const normalizePreferenceValue = (value) => {
  if (value === null || value === undefined) return null;
  if (typeof value === 'string') {
    const trimmed = value.trim();
    return trimmed ? trimmed : null;
  }
  return value;
};

const getMissingTrendPreferenceFields = (user) => REQUIRED_TREND_FIELDS.filter((field) => normalizePreferenceValue(user?.[field]) === null);

const getScoreTone = (score) => {
  if (score >= 75) return 'high';
  if (score >= 55) return 'medium';
  return 'low';
};

const getScoreLabel = (score) => {
  if (score >= 75) return 'High Opportunity';
  if (score >= 55) return 'Promising';
  return 'Watchlist';
};

const getScoringLabel = (key) => {
  const labels = {
    demand_points: 'Demand Analysis',
    market_gap_points: 'Market Gap',
    trend_points: 'Market Trends',
    momentum_points: 'Growth Momentum',
    user_experience_points: 'Your Experience',
    interest_points: 'Personal Interest',
    capital_fit_points: 'Capital Fit',
    risk_fit_points: 'Risk Fit',
    setup_fit_points: 'Setup Fit',
    payback_fit_points: 'Payback Period Fit'
  };
  return labels[key] || key.replace(/_/g, ' ');
};

export default function Trends({ user, onOpenReport, onRunAnalysis, missingTrendPreferences, onPreferencesSaved }) {
  const userId = user?.user_id || user?.id;
  const [loading, setLoading] = useState(Boolean(userId));
  const [error, setError] = useState('');
  const [summary, setSummary] = useState(null);
  const [recommendations, setRecommendations] = useState([]);
  const [expandedBusinessKey, setExpandedBusinessKey] = useState(null);
  const [expandedScoringKey, setExpandedScoringKey] = useState(null);
  const [analyzingBusinessKey, setAnalyzingBusinessKey] = useState(null);
  const [showPreferenceGate, setShowPreferenceGate] = useState(false);

  const activeMissingPreferences = useMemo(() => {
    if (Array.isArray(missingTrendPreferences)) {
      return missingTrendPreferences;
    }
    return getMissingTrendPreferenceFields(user);
  }, [missingTrendPreferences, user]);

  const hasMissingPreferences = activeMissingPreferences.length > 0;

  const fetchRecommendations = async () => {
    if (!userId) return;
    setLoading(true);
    setError('');

    try {
      const response = await fetch(apiUrl(`/users/${userId}/trend-recommendations?limit=6`), { cache: 'no-store' });
      const data = await response.json();

      if (!response.ok) {
        const detail = data?.detail;
        if (typeof detail === 'string') {
          throw new Error(detail);
        }
        if (detail?.message && Array.isArray(detail?.missing_fields) && detail.missing_fields.length > 0) {
          throw new Error(`${detail.message} Missing: ${detail.missing_fields.join(', ')}`);
        }
        throw new Error('Unable to load trend recommendations.');
      }

      setSummary(data?.summary || null);
      setRecommendations(Array.isArray(data?.recommendations) ? data.recommendations : []);
    } catch (fetchError) {
      setRecommendations([]);
      setError(fetchError.message || 'Unable to load trend recommendations.');
    } finally {
      setLoading(false);
    }
  };

  const openRecommendationReport = (item) => {
    if (!onRunAnalysis) return;

    const hotspot = Array.isArray(item.citywide_hotspots) && item.citywide_hotspots.length > 0 ? item.citywide_hotspots[0] : null;
    const fallbackCoords = item.pre_scanned_location || item.full_report?.target_coords || null;

    const coordsSource = hotspot?.coords || fallbackCoords;
    if (!coordsSource) return;

    setAnalyzingBusinessKey(item.business_key);
    
    const coords = {
      lat: Number(coordsSource.lat || coordsSource.latitude || 0),
      lng: Number(coordsSource.lng || coordsSource.lon || coordsSource.longitude || 0)
    };
    
    // Extract business keys from item.business_key (e.g., "coffee" or "coffee+bakery")
    const businessType = item.business_key || item.business_name;
    
    onRunAnalysis(coords, businessType);
    setTimeout(() => setAnalyzingBusinessKey(null), 500);
  };

  useEffect(() => {
    if (!userId) return;

    if (hasMissingPreferences) {
      setShowPreferenceGate(true);
      setLoading(false);
      setError('');
      setSummary(null);
      setRecommendations([]);
      return;
    }

    setShowPreferenceGate(false);
    fetchRecommendations();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [userId, hasMissingPreferences]);

  const hasRecommendations = useMemo(() => recommendations.length > 0, [recommendations]);
  const isDesktop = useIsDesktop();

  const renderRecommendationCard = (item, index) => {
              const score = Number(item?.opportunity_score || 0);
              const tone = getScoreTone(score);
              const scoreLabel = getScoreLabel(score);
              const isExpanded = expandedBusinessKey === item.business_key;
              const hasHotspots = Array.isArray(item?.citywide_hotspots) && item.citywide_hotspots.length > 0;
              const hasUpsides = Array.isArray(item?.upsides) && item.upsides.length > 0;
              const hasDownsides = Array.isArray(item?.downsides) && item.downsides.length > 0;
              const hasSpaceContext = hasHotspots && item.citywide_hotspots[0]?.space_context;
              const canRunAnalysis = Boolean(onRunAnalysis && (hasHotspots || item.pre_scanned_location || item.full_report?.target_coords));

              return (
                <div
                  key={item.business_key}
                  className="data-card trends-card card-stagger-item p-4"
                  style={{ '--stagger-index': index }}
                >
                  <button
                    type="button"
                    className="trends-card-top -m-1 flex w-full items-start justify-between gap-4 rounded-xl p-1 text-left transition hover:bg-[var(--accent-hover)]"
                    onClick={() => openRecommendationReport(item)}
                  >
                    <div className="flex min-w-0 items-start gap-3">
                      <span
                        className={`mt-0.5 inline-flex h-7 w-7 flex-none items-center justify-center rounded-full text-xs font-bold tabular-nums ${index === 0 ? 'bg-[var(--btn-primary-bg)] text-[var(--btn-primary-text)]' : 'bg-[var(--accent-hover)] text-[var(--accent)]'}`}
                        aria-label={`Rank ${index + 1}`}
                      >
                        {index + 1}
                      </span>
                      <h3 className="history-title min-w-0 text-lg font-semibold leading-snug text-[var(--text-main)]">{item.business_name}</h3>
                    </div>
                    <div className="trends-score-wrap flex flex-none flex-col items-end gap-1">
                      <span
                        className="trends-score text-2xl font-bold tabular-nums leading-none text-[var(--text-main)]"
                        aria-label={`Opportunity score ${score} out of 100`}
                      >
                        {score}
                      </span>
                      <span className={`trends-score-badge ${tone}`}>{scoreLabel}</span>
                    </div>
                  </button>

                  <div className="mt-3 flex flex-wrap gap-2">
                    <span className="inline-flex items-center gap-1.5 rounded-full border border-[var(--border-color)] px-2.5 py-1 text-xs font-medium tabular-nums text-[var(--text-muted)]">
                      <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true">
                        <path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2" /><circle cx="9" cy="7" r="4" /><path d="M23 21v-2a4 4 0 0 0-3-3.87" /><path d="M16 3.13a4 4 0 0 1 0 7.75" />
                      </svg>
                      {item.local_competitor_estimate} competitors
                    </span>
                    <span className="inline-flex items-center gap-1.5 rounded-full border border-[var(--border-color)] px-2.5 py-1 text-xs font-medium tabular-nums text-[var(--text-muted)]">
                      <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true">
                        <circle cx="11" cy="11" r="8" /><path d="m21 21-4.35-4.35" />
                      </svg>
                      {item.market_scan_count} scans
                    </span>
                    <span className="inline-flex items-center gap-1.5 rounded-full border border-[var(--border-color)] px-2.5 py-1 text-xs font-medium tabular-nums text-[var(--text-muted)]">
                      <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true">
                        <path d="M3 3v18h18" /><path d="m19 9-5 5-4-4-3 3" />
                      </svg>
                      Avg viability {item.market_average_viability || '—'}
                    </span>
                  </div>

                  {/* Key Reasons */}
                  <div className="mt-4">
                    <p className="eyebrow-label mb-2">Why this pick</p>
                    <ul className="trends-reasons flex flex-col gap-1.5">
                      {(item.reasons || []).slice(0, 3).map((reason, index) => (
                        <li key={`${item.business_key}-reason-${index}`} className="text-sm leading-5 text-[var(--text-muted)]">{reason}</li>
                      ))}
                    </ul>
                  </div>

                  {/* Upsides & Downsides */}
                  {(hasUpsides || hasDownsides) && (
                    <div className="mt-3 grid gap-3 sm:grid-cols-2">
                      {hasUpsides && (
                        <div className="rounded-xl bg-[var(--trend-up-bg)] p-3">
                          <p className="text-xs font-semibold uppercase tracking-[0.08em] text-[var(--trend-up)]">Upsides</p>
                          <ul className="signal-list mt-2">
                            {item.upsides.map((upside, idx) => (
                              <li key={idx} className="text-xs leading-4 text-[var(--text-main)]">
                                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" className="text-[var(--trend-up)]" aria-hidden="true">
                                  <path d="M20 6 9 17l-5-5" />
                                </svg>
                                {upside}
                              </li>
                            ))}
                          </ul>
                        </div>
                      )}
                      {hasDownsides && (
                        <div className="rounded-xl bg-[var(--trend-neutral-bg)] p-3">
                          <p className="text-xs font-semibold uppercase tracking-[0.08em] text-[var(--trend-neutral)]">Considerations</p>
                          <ul className="signal-list mt-2">
                            {item.downsides.map((downside, idx) => (
                              <li key={idx} className="text-xs leading-4 text-[var(--text-main)]">
                                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" className="text-[var(--trend-neutral)]" aria-hidden="true">
                                  <path d="m21.73 18-8-14a2 2 0 0 0-3.48 0l-8 14A2 2 0 0 0 4 21h16a2 2 0 0 0 1.73-3Z" /><path d="M12 9v4" /><path d="M12 17h.01" />
                                </svg>
                                {downside}
                              </li>
                            ))}
                          </ul>
                        </div>
                      )}
                    </div>
                  )}

                  {/* Space Context */}
                  {hasSpaceContext && (
                    <div className="mt-3 flex items-start gap-2.5 rounded-xl bg-[var(--accent-hover)] px-3 py-2.5">
                      <svg className="mt-0.5 flex-none text-[var(--accent)]" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true">
                        <path d="M6 22V4a2 2 0 0 1 2-2h8a2 2 0 0 1 2 2v18Z" /><path d="M6 12H4a2 2 0 0 0-2 2v6a2 2 0 0 0 2 2h2" /><path d="M18 9h2a2 2 0 0 1 2 2v9a2 2 0 0 1-2 2h-2" /><path d="M10 6h4" /><path d="M10 10h4" /><path d="M10 14h4" /><path d="M10 18h4" />
                      </svg>
                      <p className="text-sm leading-5 text-[var(--text-main)]">
                        <span className="font-semibold text-[var(--accent)]">Nearby space: </span>
                        {item.citywide_hotspots[0].space_context.title || 'Listed property nearby'}
                        {item.citywide_hotspots[0].space_context.price_min && ` • PHP ${item.citywide_hotspots[0].space_context.price_min.toLocaleString()}`}
                      </p>
                    </div>
                  )}

                  {/* Expandable Scoring Breakdown & Profile Match */}
                  <div className="mt-4 flex items-center gap-2 border-t border-[var(--border-color)] pt-3">
                    <button
                      type="button"
                      className="trends-analyze-btn inline-flex min-h-[44px] items-center justify-center gap-2 rounded-xl bg-[var(--btn-primary-bg)] px-4 py-2.5 text-sm font-semibold text-[var(--btn-primary-text)] transition hover:bg-[var(--btn-primary-hover)] disabled:cursor-not-allowed disabled:opacity-50"
                      onClick={() => openRecommendationReport(item)}
                      disabled={!canRunAnalysis || analyzingBusinessKey === item.business_key}
                    >
                      <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true">
                        <circle cx="12" cy="12" r="3" /><path d="M12 2v3M12 19v3M2 12h3M19 12h3" />
                      </svg>
                      {analyzingBusinessKey === item.business_key ? 'Running...' : 'Run Analysis'}
                    </button>
                    <button
                      type="button"
                      className="trends-breakdown-toggle ml-auto inline-flex min-h-[44px] items-center gap-1.5 rounded-xl px-3 py-2.5 text-sm font-medium text-[var(--text-muted)] transition hover:bg-[var(--accent-hover)] hover:text-[var(--text-main)]"
                      onClick={() => setExpandedBusinessKey(isExpanded ? null : item.business_key)}
                      aria-expanded={isExpanded}
                    >
                      Details
                      <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" aria-hidden="true" style={{ transform: isExpanded ? 'rotate(180deg)' : 'none', transition: 'transform 200ms ease' }}>
                        <path d="m6 9 6 6 6-6" />
                      </svg>
                    </button>
                  </div>

                  {isExpanded && (
                    <div className="trends-breakdown mt-3 border-t border-[var(--border-color)] pt-3">
                      {/* Scoring Breakdown */}
                      {item.scoring && Object.keys(item.scoring).length > 0 && (
                        <div className="mb-4">
                          <p className="eyebrow-label mb-2">Opportunity Scoring</p>
                          <div className="grid gap-2 sm:grid-cols-2">
                            {Object.entries(item.scoring).map(([key, value]) => (
                              <div key={key} className="rounded-lg border border-[var(--border-color)] p-2 text-xs">
                                <div className="flex items-center justify-between mb-1">
                                  <span className="font-medium text-[var(--text-main)]">{getScoringLabel(key)}</span>
                                  <span className="font-bold tabular-nums text-[var(--text-main)]">{value}</span>
                                </div>
                                <div className="h-1.5 rounded-full bg-[var(--accent-hover)]">
                                  <div className="h-1.5 rounded-full bg-[var(--accent)]" style={{ width: `${Math.max(0, Math.min(100, (value / 25) * 100))}%` }} />
                                </div>
                              </div>
                            ))}
                          </div>
                        </div>
                      )}

                      {/* Profile Match */}
                      {item.profile_match && Object.keys(item.profile_match).length > 0 && (
                        <div>
                          <p className="eyebrow-label mb-2">Your Profile Match</p>
                          <div className="grid gap-2 text-xs sm:grid-cols-2">
                            {item.profile_match.capital_range && (
                              <div className="rounded-lg border border-[var(--border-color)] p-2.5">
                                <p className="text-[0.68rem] font-semibold uppercase tracking-[0.08em] text-[var(--text-muted)]">Capital Range</p>
                                <p className="mt-1 font-semibold tabular-nums text-[var(--text-main)]">PHP {item.profile_match.capital_range.min?.toLocaleString()} - {item.profile_match.capital_range.max?.toLocaleString()}</p>
                              </div>
                            )}
                            {item.profile_match.business_risk && (
                              <div className="rounded-lg border border-[var(--border-color)] p-2.5">
                                <p className="text-[0.68rem] font-semibold uppercase tracking-[0.08em] text-[var(--text-muted)]">Business Risk</p>
                                <p className="mt-1 font-semibold capitalize text-[var(--text-main)]">{item.profile_match.business_risk}</p>
                              </div>
                            )}
                            {item.profile_match.business_setup && (
                              <div className="rounded-lg border border-[var(--border-color)] p-2.5">
                                <p className="text-[0.68rem] font-semibold uppercase tracking-[0.08em] text-[var(--text-muted)]">Typical Setup</p>
                                <p className="mt-1 font-semibold capitalize text-[var(--text-main)]">{item.profile_match.business_setup}</p>
                              </div>
                            )}
                            {item.profile_match.estimated_payback_months && (
                              <div className="rounded-lg border border-[var(--border-color)] p-2.5">
                                <p className="text-[0.68rem] font-semibold uppercase tracking-[0.08em] text-[var(--text-muted)]">Payback Period</p>
                                <p className="mt-1 font-semibold tabular-nums text-[var(--text-main)]">~{item.profile_match.estimated_payback_months} months</p>
                              </div>
                            )}
                          </div>
                        </div>
                      )}
                    </div>
                  )}

                </div>
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
              <p className="profile-email text-sm text-[var(--text-muted)]">MSME opportunities ranked for your profile.</p>
            </div>
            <div className="flex items-center gap-2">
              {!loading && hasRecommendations && (
                <span className="inline-flex items-center gap-2 rounded-full border border-[var(--border-color)] bg-[var(--accent-hover)] px-3 py-1.5 text-xs font-semibold tabular-nums text-[var(--accent)]">
                  <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true">
                    <path d="M3 3v18h18" /><path d="m19 9-5 5-4-4-3 3" />
                  </svg>
                  {recommendations.length} picks
                </span>
              )}
              <button
                type="button"
                className="inline-flex min-h-[44px] items-center justify-center gap-2 rounded-xl border border-[var(--border-color)] bg-[var(--bg-sheet)] px-4 py-2.5 text-sm font-medium text-[var(--text-main)] transition hover:border-[var(--border-strong)] hover:bg-[var(--accent-hover)] disabled:cursor-not-allowed disabled:opacity-60"
                onClick={fetchRecommendations}
                disabled={loading}
              >
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true" className={loading ? 'animate-spin' : ''}>
                  <path d="M21 12a9 9 0 1 1-2.64-6.36" /><path d="M21 3v6h-6" />
                </svg>
                {loading ? 'Refreshing...' : 'Refresh'}
              </button>
            </div>
          </div>

          {summary && (
            <span className="trends-summary mt-3 inline-flex items-center gap-2 rounded-full border border-[var(--border-color)] bg-[var(--accent-hover)] px-3 py-1.5 text-xs font-medium text-[var(--text-muted)]">
              <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className="text-[var(--accent)]" aria-hidden="true">
                <circle cx="12" cy="12" r="3" /><path d="M12 2v3M12 19v3M2 12h3M19 12h3" />
              </svg>
              Profile interest: <strong className="text-[var(--accent)]">{summary.profile_interest || 'Not set'}</strong>
            </span>
          )}
        </div>

        {loading && <div className="data-card p-4 text-sm text-[var(--text-muted)]">Generating recommendations...</div>}

        {!loading && error && (
          <div className="data-card border border-[var(--border-color)] bg-[var(--trend-down-bg)] p-4 text-sm text-[var(--trend-down)]">
            {error}
          </div>
        )}

        {!loading && !error && !hasRecommendations && (
          <div className="history-empty-state">
            <div className="history-empty-icon" aria-hidden="true">
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <path d="M3 12h18" />
                <path d="M12 3v18" />
              </svg>
            </div>
            <div>
              <p className="history-empty-title">No trend recommendations yet</p>
              <p className="history-empty-subtitle">Complete your profile and run more analyses to improve recommendation quality.</p>
            </div>
          </div>
        )}

        {!loading && hasMissingPreferences && (
          <div className="data-card border border-[var(--border-color)] bg-[var(--trend-neutral-bg)] p-4 text-sm text-[var(--text-main)]">
            <p className="font-semibold">Trend preferences are not complete yet.</p>
            <p className="mt-1 text-[var(--text-muted)]">Complete your preferences to generate trend recommendations for your profile.</p>
            <button
              type="button"
              className="mt-3 inline-flex items-center justify-center rounded-xl bg-[var(--btn-primary-bg)] px-4 py-2 text-sm font-semibold text-[var(--btn-primary-text)] transition hover:bg-[var(--btn-primary-hover)]"
              onClick={() => setShowPreferenceGate(true)}
            >
              Complete Preferences
            </button>
          </div>
        )}

        {!loading && !error && hasRecommendations && (
          isDesktop ? (
            <div className="trends-list mt-2 grid grid-cols-2 items-start gap-4">
              <div className="flex min-w-0 flex-col gap-4 [&>*]:mb-0">
                {recommendations.map((item, index) => (index % 2 === 0 ? renderRecommendationCard(item, index) : null))}
              </div>
              <div className="flex min-w-0 flex-col gap-4 [&>*]:mb-0">
                {recommendations.map((item, index) => (index % 2 === 1 ? renderRecommendationCard(item, index) : null))}
              </div>
            </div>
          ) : (
            <div className="trends-list mt-2 flex flex-col gap-4 [&>*]:mb-0">
              {recommendations.map((item, index) => renderRecommendationCard(item, index))}
            </div>
          )
        )}
      </div>

      {hasMissingPreferences && showPreferenceGate && (
        <TrendPreferencesGate
          user={user}
          missingFields={activeMissingPreferences}
          onSaved={(updatedUser) => {
            onPreferencesSaved?.(updatedUser);
            setShowPreferenceGate(false);
          }}
          onLater={() => setShowPreferenceGate(false)}
        />
      )}
    </div>
  );
}
