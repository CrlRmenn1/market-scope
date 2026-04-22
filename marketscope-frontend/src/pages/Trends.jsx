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

export default function Trends({ user, onOpenReport }) {
  const userId = user?.user_id || user?.id;
  const [loading, setLoading] = useState(Boolean(userId));
  const [error, setError] = useState('');
  const [summary, setSummary] = useState(null);
  const [recommendations, setRecommendations] = useState([]);

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
              const preScannedLocation = item?.pre_scanned_location || null;
              const locationSource = preScannedLocation?.source || 'Panabo pre-scan engine';
              const spaceContext = preScannedLocation?.space_context || null;
              const upsides = Array.isArray(item?.upsides) ? item.upsides : [];
              const downsides = Array.isArray(item?.downsides) ? item.downsides : [];
              const hasFullReport = Boolean(item?.full_report && typeof onOpenReport === 'function');

              return (
                <article key={item.business_key} className="data-card trends-card rounded-2xl border border-white/10 bg-slate-900/60 p-4 shadow-sm">
                  <div className="trends-card-top">
                    <div>
                      <h3 className="history-title text-lg font-semibold text-slate-50">{item.business_name}</h3>
                      <p className="history-meta mt-1 text-sm text-slate-400">
                        Local competitors: {item.local_competitor_estimate} | Market scans: {item.market_scan_count}
                      </p>
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
                      <li key={`${item.business_key}-reason-${index}`}>{reason}</li>
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
