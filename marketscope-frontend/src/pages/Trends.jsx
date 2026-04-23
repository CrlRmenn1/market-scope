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

const formatListingMode = (mode) => {
  const normalized = String(mode || '').toLowerCase();
  if (normalized === 'buy') return 'For Sale';
  if (normalized === 'rent') return 'For Rent';
  return 'Not specified';
};

const formatScore = (value) => `${Math.max(0, Math.min(100, Number(value) || 0))}/100`;

const formatRelativeTime = (value) => {
  if (!value) return 'Not yet updated';

  const ts = Number(value);
  if (!Number.isFinite(ts)) return 'Not yet updated';

  const diffMs = Date.now() - ts;
  if (diffMs < 60 * 1000) return 'Updated just now';

  const diffMinutes = Math.floor(diffMs / (60 * 1000));
  if (diffMinutes < 60) return `Updated ${diffMinutes}m ago`;

  const diffHours = Math.floor(diffMinutes / 60);
  if (diffHours < 24) return `Updated ${diffHours}h ago`;

  const diffDays = Math.floor(diffHours / 24);
  return `Updated ${diffDays}d ago`;
};

export default function Trends({ user, onOpenReport }) {
  const userId = user?.user_id || user?.id;
  const trendsCacheKey = userId ? `marketscope_trends_cache_${userId}` : null;
  const [loading, setLoading] = useState(Boolean(userId));
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState('');
  const [summary, setSummary] = useState(null);
  const [recommendations, setRecommendations] = useState([]);
  const [lastUpdatedAt, setLastUpdatedAt] = useState(null);

  const fetchRecommendations = async ({ silent = false } = {}) => {
    if (!userId) return;
    if (silent) {
      setRefreshing(true);
    } else {
      setLoading(true);
    }
    setError('');

    try {
      const response = await fetch(apiUrl(`/users/${userId}/trend-recommendations?limit=6`), { cache: 'no-store' });
      const data = await response.json();

      if (!response.ok) {
        throw new Error(data?.detail || 'Unable to load trend recommendations.');
      }

      const nextSummary = data?.summary || null;
      const nextRecommendations = Array.isArray(data?.recommendations) ? data.recommendations : [];

      setSummary(nextSummary);
      setRecommendations(nextRecommendations);

      if (trendsCacheKey) {
        const cachedAt = Date.now();
        setLastUpdatedAt(cachedAt);
        localStorage.setItem(
          trendsCacheKey,
          JSON.stringify({
            cachedAt,
            summary: nextSummary,
            recommendations: nextRecommendations,
          })
        );
      }
    } catch (fetchError) {
      setRecommendations([]);
      setError(fetchError.message || 'Unable to load trend recommendations.');
    } finally {
      if (silent) {
        setRefreshing(false);
      } else {
        setLoading(false);
      }
    }
  };

  useEffect(() => {
    if (!userId) return;

    let hydratedFromCache = false;
    if (trendsCacheKey) {
      try {
        const raw = localStorage.getItem(trendsCacheKey);
        if (raw) {
          const parsed = JSON.parse(raw);
          if (Array.isArray(parsed?.recommendations)) {
            setSummary(parsed?.summary || null);
            setRecommendations(parsed.recommendations);
            setLastUpdatedAt(Number(parsed?.cachedAt) || null);
            setLoading(false);
            hydratedFromCache = true;
          }
        }
      } catch {
        // Ignore malformed cache data.
      }
    }

    fetchRecommendations({ silent: hydratedFromCache });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [userId, trendsCacheKey]);

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
              {loading || refreshing ? 'Refreshing...' : 'Refresh'}
            </button>
          </div>

          {summary && (
            <p className="trends-summary mt-3 text-sm text-slate-300">
              Based on your profile interest: <strong>{summary.profile_interest || 'Not set'}</strong>
            </p>
          )}

          <p className="trends-cache-meta mt-2 text-xs text-slate-400">
            {refreshing ? 'Refreshing latest trend data...' : formatRelativeTime(lastUpdatedAt)}
          </p>
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
            {recommendations.map((item, index) => {
              const opportunityScore = Number(item?.opportunity_score || 0);
              const projectedReportScore = Number(item?.pre_scanned_location?.viability_score ?? item?.full_report?.viability_score);
              const score = Number.isFinite(projectedReportScore) ? projectedReportScore : opportunityScore;
              const tone = getScoreTone(score);
              const scoreLabel = getScoreLabel(score);
              const preScannedLocation = item?.pre_scanned_location || null;
              const locationSource = preScannedLocation?.source || 'Panabo pre-scan engine';
              const spaceContext = preScannedLocation?.space_context || null;
              const upsides = Array.isArray(item?.upsides) ? item.upsides : [];
              const downsides = Array.isArray(item?.downsides) ? item.downsides : [];
              const hasFullReport = Boolean(item?.full_report && typeof onOpenReport === 'function');

              return (
                <article
                  key={item.business_key}
                  className="data-card trends-card trends-card-animate rounded-2xl border border-white/10 bg-slate-900/60 p-4 shadow-sm"
                  style={{ '--trend-index': index }}
                >
                  <div className="trends-chip-row">
                    <span className="trends-chip trends-chip-score">Projected viability: {score}/100</span>
                    <span className="trends-chip trends-chip-source">Pre-scanned insight</span>
                  </div>

                  <div className="trends-card-top">
                    <div>
                      <h3 className="history-title text-lg font-semibold text-slate-50">{item.business_name}</h3>
                      <p className="history-meta mt-1 text-sm text-slate-400">
                        Local competitors: {item.local_competitor_estimate} | Market scans: {item.market_scan_count}
                      </p>
                      {opportunityScore !== score && (
                        <p className="mt-1 text-xs text-slate-400">Opportunity score: {opportunityScore}/100</p>
                      )}
                      {item?.included_by_preference && (
                        <p className="mt-2 inline-flex rounded-full border border-amber-300/30 bg-amber-300/10 px-2.5 py-1 text-xs font-semibold text-amber-100">
                          Included by your profile preference
                        </p>
                      )}
                    </div>
                    <div className="trends-score-wrap">
                      <span className={`trends-score-badge ${tone}`}>{scoreLabel}</span>
                      <strong className="trends-score">{score}/100</strong>
                    </div>
                  </div>

                  <div className="trends-progress mt-3" role="presentation">
                    <span style={{ width: `${Math.max(0, Math.min(100, score))}%` }} />
                  </div>

                  <div className="trends-kpi-row mt-3">
                    <div className="trends-kpi-card">
                      <span className="trends-kpi-label">Viability</span>
                      <strong className="trends-kpi-value">{score}/100</strong>
                    </div>
                    <div className="trends-kpi-card">
                      <span className="trends-kpi-label">Competitors</span>
                      <strong className="trends-kpi-value">{item.local_competitor_estimate}</strong>
                    </div>
                    <div className="trends-kpi-card">
                      <span className="trends-kpi-label">Market Scans</span>
                      <strong className="trends-kpi-value">{item.market_scan_count}</strong>
                    </div>
                  </div>

                  {preScannedLocation && (
                    <div className="trends-prescan mt-3 rounded-xl border border-white/10 bg-slate-950/40 p-3">
                      <p className="text-xs font-semibold uppercase tracking-[0.08em] text-slate-400">Pre-scanned location in Panabo</p>
                      <p className="mt-1 text-sm text-slate-200">{locationSource}</p>
                      <p className="mt-1 text-xs text-slate-400">
                        Viability: {formatScore(preScannedLocation?.viability_score)} | Coordinates: {Number(preScannedLocation?.lat || 0).toFixed(5)}, {Number(preScannedLocation?.lng || 0).toFixed(5)}
                      </p>
                      {spaceContext && (
                        <p className="mt-2 text-xs text-emerald-200">
                          Nearby {formatListingMode(spaceContext.listing_mode)} space: {spaceContext.title || 'Unnamed listing'}
                        </p>
                      )}
                    </div>
                  )}

                  <div className="trends-swot-grid mt-3">
                    <div className="trends-swot-card trends-swot-upside">
                      <p className="trends-swot-title">Upside</p>
                      <ul>
                        {upsides.slice(0, 3).map((point, index) => (
                          <li key={`${item.business_key}-up-${index}`}>{point}</li>
                        ))}
                      </ul>
                    </div>
                    <div className="trends-swot-card trends-swot-downside">
                      <p className="trends-swot-title">Downside</p>
                      <ul>
                        {downsides.slice(0, 3).map((point, index) => (
                          <li key={`${item.business_key}-down-${index}`}>{point}</li>
                        ))}
                      </ul>
                    </div>
                  </div>

                  <ul className="trends-reasons mt-3">
                    {(item.reasons || []).slice(0, 4).map((reason, index) => (
                      <li key={`${item.business_key}-reason-${index}`} className="trends-reason-pill">{reason}</li>
                    ))}
                  </ul>

                  <div className="mt-4 flex justify-end">
                    <button
                      type="button"
                      className="history-open-btn"
                      disabled={!hasFullReport}
                      onClick={() => {
                        if (!hasFullReport) return;
                        onOpenReport(item.full_report);
                      }}
                    >
                      Open Full Report
                    </button>
                  </div>
                </article>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
}
