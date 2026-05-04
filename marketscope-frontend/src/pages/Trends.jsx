import React, { useEffect, useMemo, useState } from 'react';
import { apiUrl } from '../api';

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

export default function Trends({ user, onOpenReport, onRunAnalysis }) {
  const userId = user?.user_id || user?.id;
  const [loading, setLoading] = useState(Boolean(userId));
  const [error, setError] = useState('');
  const [summary, setSummary] = useState(null);
  const [recommendations, setRecommendations] = useState([]);
  const [expandedBusinessKey, setExpandedBusinessKey] = useState(null);
  const [expandedScoringKey, setExpandedScoringKey] = useState(null);
  const [analyzingBusinessKey, setAnalyzingBusinessKey] = useState(null);

  const fetchRecommendations = async () => {
    if (!userId) return;
    setLoading(true);
    setError('');

    try {
      const response = await fetch(apiUrl(`/users/${userId}/trend-recommendations?limit=6`), { cache: 'no-store' });
      const data = await response.json();

      if (!response.ok) {
        throw new Error(data?.detail || 'Unable to load trend recommendations.');
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
    if (!onRunAnalysis || !item.citywide_hotspots?.length) return;
    setAnalyzingBusinessKey(item.business_key);
    
    const coords = {
      lat: item.citywide_hotspots[0].coords?.lat || 0,
      lng: item.citywide_hotspots[0].coords?.lng || item.citywide_hotspots[0].coords?.lon || 0
    };
    
    // Extract business keys from item.business_key (e.g., "coffee" or "coffee+bakery")
    const businessType = item.business_key || item.business_name;
    
    onRunAnalysis(coords, businessType);
    setTimeout(() => setAnalyzingBusinessKey(null), 500);
  };

  useEffect(() => {
    fetchRecommendations();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [userId]);

  const hasRecommendations = useMemo(() => recommendations.length > 0, [recommendations]);

  return (
    <div className="profile-page page-enter min-h-full">
      <div className="mx-auto flex w-full max-w-4xl flex-col gap-4 px-4 pb-28 pt-4 sm:px-6">
        <div className="profile-card fade-in rounded-2xl border border-white/10 bg-slate-900/70 p-5 text-left shadow-sm">
          <div className="trends-header-row">
            <div>
              <h2 className="profile-name mb-2 text-2xl font-semibold tracking-tight text-slate-50 sm:text-3xl">Business Trends</h2>
              <p className="profile-email text-sm text-slate-300">Recommendations where market opportunities can find you.</p>
            </div>
            <button type="button" className="edit-btn trends-refresh-btn" onClick={fetchRecommendations} disabled={loading}>
              {loading ? 'Refreshing...' : 'Refresh'}
            </button>
          </div>

          {summary && (
            <p className="trends-summary mt-3 text-sm text-slate-300">
              Based on your profile interest: <strong>{summary.profile_interest || 'Not set'}</strong>
            </p>
          )}
        </div>

        {loading && <div className="data-card rounded-2xl border border-white/10 bg-slate-900/60 p-4 text-sm text-slate-300 shadow-sm">Generating recommendations...</div>}

        {!loading && error && (
          <div className="data-card rounded-2xl border border-rose-400/20 bg-rose-500/10 p-4 text-sm text-rose-200 shadow-sm">
            {error}
          </div>
        )}

        {!loading && !error && !hasRecommendations && (
          <div className="history-empty-state flex items-center gap-4 rounded-2xl border border-white/10 bg-slate-900/60 p-4 shadow-sm">
            <div className="history-empty-icon" aria-hidden="true">
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <path d="M3 12h18" />
                <path d="M12 3v18" />
              </svg>
            </div>
            <div>
              <p className="history-empty-title">No trend recommendations yet</p>
              <p className="history-empty-subtitle mt-1">Complete your profile and run more analyses to improve recommendation quality.</p>
            </div>
          </div>
        )}

        {!loading && !error && hasRecommendations && (
          <div className="trends-list mt-2 flex flex-col gap-4">
            {recommendations.map((item) => {
              const score = Number(item?.opportunity_score || 0);
              const tone = getScoreTone(score);
              const scoreLabel = getScoreLabel(score);
              const isExpanded = expandedBusinessKey === item.business_key;
              const hasHotspots = Array.isArray(item?.citywide_hotspots) && item.citywide_hotspots.length > 0;
              const hasUpsides = Array.isArray(item?.upsides) && item.upsides.length > 0;
              const hasDownsides = Array.isArray(item?.downsides) && item.downsides.length > 0;
              const hasSpaceContext = hasHotspots && item.citywide_hotspots[0]?.space_context;

              return (
                <div key={item.business_key} className="data-card trends-card rounded-2xl border border-white/10 bg-slate-900/60 p-4 shadow-sm">
                  <button
                    type="button"
                    className="trends-card-top flex w-full items-start justify-between gap-4 rounded-lg border border-white/10 bg-white/5 px-4 py-3 text-left transition hover:border-violet-400/30 hover:bg-violet-500/10"
                    onClick={() => openRecommendationReport(item)}
                  >
                    <div>
                      <h3 className="history-title text-lg font-semibold text-slate-50">{item.business_name}</h3>
                      <p className="history-meta mt-1 text-sm text-slate-400">
                        Local competitors: {item.local_competitor_estimate} | Market scans: {item.market_scan_count} | Avg score: {item.market_average_viability || '—'}
                      </p>
                    </div>
                    <div className="trends-score-wrap flex flex-col items-end gap-2">
                      <span className={`trends-score-badge ${tone}`}>{scoreLabel}</span>
                      <strong className="trends-score text-xl">{score}/100</strong>
                    </div>
                  </button>

                  <div className="trends-progress mt-3" role="presentation">
                    <span style={{ width: `${Math.max(0, Math.min(100, score))}%` }} />
                  </div>

                  {/* Key Reasons */}
                  <div className="mt-3 rounded-lg border border-white/10 bg-black/10 p-3">
                    <p className="settings-label mb-2 text-[0.72rem] font-semibold uppercase tracking-[0.18em] text-slate-400">Key Reasons</p>
                    <ul className="trends-reasons flex flex-col gap-1.5">
                      {(item.reasons || []).slice(0, 3).map((reason, index) => (
                        <li key={`${item.business_key}-reason-${index}`} className="text-sm leading-5 text-slate-300">• {reason}</li>
                      ))}
                    </ul>
                  </div>

                  {/* Upsides & Downsides */}
                  {(hasUpsides || hasDownsides) && (
                    <div className="mt-3 grid gap-3 sm:grid-cols-2">
                      {hasUpsides && (
                        <div className="rounded-lg border border-violet-500/30 bg-violet-500/10 p-3">
                          <p className="text-xs font-semibold uppercase tracking-[0.16em] text-violet-300">Upsides</p>
                          <ul className="mt-2 flex flex-col gap-1">
                            {item.upsides.map((upside, idx) => (
                              <li key={idx} className="text-xs leading-4 text-violet-200">✓ {upside}</li>
                            ))}
                          </ul>
                        </div>
                      )}
                      {hasDownsides && (
                        <div className="rounded-lg border border-amber-500/30 bg-amber-500/10 p-3">
                          <p className="text-xs font-semibold uppercase tracking-[0.16em] text-amber-300">Considerations</p>
                          <ul className="mt-2 flex flex-col gap-1">
                            {item.downsides.map((downside, idx) => (
                              <li key={idx} className="text-xs leading-4 text-amber-200">⚠ {downside}</li>
                            ))}
                          </ul>
                        </div>
                      )}
                    </div>
                  )}

                  {/* Space Context */}
                  {hasSpaceContext && (
                    <div className="mt-3 rounded-lg border border-violet-500/20 bg-violet-500/5 p-3">
                      <p className="text-xs font-semibold uppercase tracking-[0.16em] text-violet-300">Nearby Space Listing</p>
                      <p className="mt-2 text-sm leading-5 text-slate-200">
                        {item.citywide_hotspots[0].space_context.title || 'Listed property nearby'}
                        {item.citywide_hotspots[0].space_context.price_min && ` • PHP ${item.citywide_hotspots[0].space_context.price_min.toLocaleString()}`}
                      </p>
                    </div>
                  )}

                  {/* Expandable Scoring Breakdown & Profile Match */}
                  <button
                    type="button"
                    className="trends-breakdown-toggle mt-3 inline-flex w-full items-center justify-center rounded-lg border border-white/10 bg-white/5 px-4 py-2.5 text-sm font-medium text-slate-100 transition hover:border-violet-400/40 hover:bg-violet-500/10"
                    onClick={() => setExpandedBusinessKey(isExpanded ? null : item.business_key)}
                  >
                    {isExpanded ? 'Hide Details' : 'Show Scoring & Profile Match'}
                  </button>

                  {isExpanded && (
                    <div className="trends-breakdown mt-3 rounded-xl border border-white/10 bg-black/20 p-3">
                      {/* Scoring Breakdown */}
                      {item.scoring && Object.keys(item.scoring).length > 0 && (
                        <div className="mb-4">
                          <p className="settings-label mb-2 text-[0.72rem] font-semibold uppercase tracking-[0.18em] text-slate-400">Opportunity Scoring</p>
                          <div className="grid gap-2 sm:grid-cols-2">
                            {Object.entries(item.scoring).map(([key, value]) => (
                              <div key={key} className="rounded-lg border border-white/10 bg-white/5 p-2 text-xs">
                                <div className="flex items-center justify-between mb-1">
                                  <span className="font-medium text-slate-100">{getScoringLabel(key)}</span>
                                  <span className="font-bold text-violet-300">{value}</span>
                                </div>
                                <div className="h-1.5 rounded-full bg-white/10">
                                  <div className="h-1.5 rounded-full bg-violet-400" style={{ width: `${Math.max(0, Math.min(100, (value / 25) * 100))}%` }} />
                                </div>
                              </div>
                            ))}
                          </div>
                        </div>
                      )}

                      {/* Profile Match */}
                      {item.profile_match && Object.keys(item.profile_match).length > 0 && (
                        <div>
                          <p className="settings-label mb-2 text-[0.72rem] font-semibold uppercase tracking-[0.18em] text-slate-400">Your Profile Match</p>
                          <div className="flex flex-col gap-2 text-xs text-slate-300">
                            {item.profile_match.capital_range && (
                              <p><strong>Capital Range:</strong> PHP {item.profile_match.capital_range.min?.toLocaleString()} - PHP {item.profile_match.capital_range.max?.toLocaleString()}</p>
                            )}
                            {item.profile_match.business_risk && (
                              <p><strong>Business Risk:</strong> {item.profile_match.business_risk}</p>
                            )}
                            {item.profile_match.business_setup && (
                              <p><strong>Typical Setup:</strong> {item.profile_match.business_setup}</p>
                            )}
                            {item.profile_match.estimated_payback_months && (
                              <p><strong>Payback Period:</strong> ~{item.profile_match.estimated_payback_months} months</p>
                            )}
                          </div>
                        </div>
                      )}
                    </div>
                  )}

                  <button
                    type="button"
                    className="edit-btn trends-analyze-btn mt-3 inline-flex w-full items-center justify-center rounded-lg border border-violet-400/30 bg-violet-500/10 px-4 py-2.5 text-sm font-medium text-violet-200 transition hover:border-violet-400/50 hover:bg-violet-500/20 disabled:cursor-not-allowed disabled:opacity-60"
                    onClick={() => openRecommendationReport(item)}
                    disabled={analyzingBusinessKey === item.business_key}
                  >
                    {analyzingBusinessKey === item.business_key ? 'Running Analysis...' : 'Run Suitability Analysis'}
                  </button>
                </div>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
}
