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

const formatCurrencyRange = (range) => {
  const minValue = Number(range?.min || 0);
  const maxValue = Number(range?.max || 0);

  if (minValue > 0 && maxValue > 0) {
    return `PHP ${minValue.toLocaleString()} - PHP ${maxValue.toLocaleString()}`;
  }

  if (minValue > 0) {
    return `From PHP ${minValue.toLocaleString()}`;
  }

  if (maxValue > 0) {
    return `Up to PHP ${maxValue.toLocaleString()}`;
  }

  return 'Not set';
};

const formatPercent = (value) => {
  const parsed = Number(value);
  if (!Number.isFinite(parsed)) return '0%';
  return `${Math.max(0, Math.min(100, Math.round(parsed)))}%`;
};

const formatOpportunityMetric = (score) => `${Math.max(0, Math.min(100, Math.round(Number(score) || 0)))} / 100`;

const formatCurrency = (value) => {
  const parsed = Number(value);
  if (!Number.isFinite(parsed) || parsed <= 0) return 'Not set';
  return `PHP ${parsed.toLocaleString()}`;
};

export default function Trends({ user }) {
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
  const topRecommendation = recommendations[0] || null;
  const comparisonSlice = recommendations.slice(0, 3);
  const summaryInterest = summary?.profile_interest || 'Not set';
  const summaryCapital = formatCurrency(summary?.startup_capital);
  const summarySetup = summary?.preferred_setup || 'Not set';
  const summaryRisk = summary?.risk_tolerance || 'Not set';
  const summaryPayback = summary?.target_payback_months ? `${summary.target_payback_months} months` : 'Not set';
  const totalOptions = summary?.total_options_evaluated || recommendations.length;
  const strongOptions = recommendations.filter((item) => Number(item?.opportunity_score || 0) >= 75).length;
  const bestScore = Number(topRecommendation?.opportunity_score || 0);
  const bestCompetition = Number(topRecommendation?.local_competitor_estimate || 0);
  const bestScanCount = Number(topRecommendation?.market_scan_count || 0);
  const bestMarketAverage = Number(topRecommendation?.market_average_viability || 0);

  return (
    <div className="profile-page trends-page page-enter min-h-full">
      <div className="mx-auto flex w-full max-w-5xl flex-col gap-4 px-4 pb-28 pt-4 sm:px-6">
        <div className="trends-hero profile-card fade-in rounded-2xl border border-white/10 bg-slate-900/80 p-5 text-left shadow-sm">
          <div className="trends-header-row trends-hero-header">
            <div className="trends-hero-copy">
              <span className="trends-eyebrow">Pitch-ready opportunity lens</span>
              <h2 className="profile-name mb-2 text-2xl font-semibold tracking-tight text-slate-50 sm:text-3xl">Business Trends</h2>
              <p className="profile-email max-w-2xl text-sm text-slate-300">
                This page turns market signals into an entrepreneur-facing case: where demand is localized, what is feasible to build, what the risks are, and why the timing matters now.
              </p>
            </div>
            <button type="button" className="edit-btn trends-refresh-btn" onClick={fetchRecommendations} disabled={loading}>
              {loading ? 'Refreshing...' : 'Refresh'}
            </button>
          </div>

          {summary && (
            <div className="trends-profile-snapshot mt-4">
              <div className="trends-snapshot-card">
                <span>Primary interest</span>
                <strong>{summaryInterest}</strong>
              </div>
              <div className="trends-snapshot-card">
                <span>Startup capital</span>
                <strong>{summaryCapital}</strong>
              </div>
              <div className="trends-snapshot-card">
                <span>Risk tolerance</span>
                <strong>{summaryRisk}</strong>
              </div>
              <div className="trends-snapshot-card">
                <span>Preferred setup</span>
                <strong>{summarySetup}</strong>
              </div>
              <div className="trends-snapshot-card">
                <span>Payback target</span>
                <strong>{summaryPayback}</strong>
              </div>
            </div>
          )}
        </div>

        {hasRecommendations && topRecommendation && (
          <div className="trends-highlights-grid">
            <article className="trends-highlight-card data-card rounded-2xl border border-white/10 bg-slate-900/60 p-4 shadow-sm">
              <p className="trends-highlight-label">Best current opportunity</p>
              <h3 className="trends-highlight-title">{topRecommendation.business_name}</h3>
              <p className="trends-highlight-copy">
                Opportunity score {formatOpportunityMetric(bestScore)} with {formatPercent(bestMarketAverage)} average viability across recent scans.
              </p>
            </article>
            <article className="trends-highlight-card data-card rounded-2xl border border-white/10 bg-slate-900/60 p-4 shadow-sm">
              <p className="trends-highlight-label">Localized signal</p>
              <h3 className="trends-highlight-title">{bestCompetition} local competitors</h3>
              <p className="trends-highlight-copy">
                The page is strongest when it shows where supply is thinner than demand in the same geography.
              </p>
            </article>
            <article className="trends-highlight-card data-card rounded-2xl border border-white/10 bg-slate-900/60 p-4 shadow-sm">
              <p className="trends-highlight-label">Why now</p>
              <h3 className="trends-highlight-title">{bestScanCount} market scans</h3>
              <p className="trends-highlight-copy">
                Recent activity gives the trend page a momentum signal instead of a static guess.
              </p>
            </article>
          </div>
        )}

        {summary && (
          <section className="trends-framework-grid">
            <article className="trends-framework-card data-card rounded-2xl border border-white/10 bg-slate-900/60 p-4 shadow-sm">
              <p className="trends-framework-kicker">1. Localized spatial analysis</p>
              <h3 className="history-title text-lg font-semibold text-slate-50">Where demand meets supply</h3>
              <p className="history-meta mt-1 text-sm text-slate-400">
                Use the strongest recommendation as the proof point, then show how its local competitor count and scan activity support a specific geography.
              </p>
              <ul className="trends-framework-points mt-3">
                <li>Show the business with the highest opportunity score.</li>
                <li>Pair it with local competitor estimates to reveal the market gap.</li>
                <li>Use recent scans as evidence that the signal is happening now, not in theory.</li>
              </ul>
            </article>

            <article className="trends-framework-card data-card rounded-2xl border border-white/10 bg-slate-900/60 p-4 shadow-sm">
              <p className="trends-framework-kicker">2. Technical feasibility check</p>
              <h3 className="history-title text-lg font-semibold text-slate-50">Can the idea actually be built?</h3>
              <p className="history-meta mt-1 text-sm text-slate-400">
                The reference framing is useful because the model can connect business fit to capital, setup type, and payback expectations.
              </p>
              <ul className="trends-framework-points mt-3">
                <li>Capital range: {summaryCapital}</li>
                <li>Startup capital: {summaryCapital}</li>
                <li>Preferred setup: {summarySetup}</li>
                <li>Expected payback target: {summaryPayback}</li>
              </ul>
            </article>

            <article className="trends-framework-card data-card rounded-2xl border border-white/10 bg-slate-900/60 p-4 shadow-sm">
              <p className="trends-framework-kicker">3. Risk and vulnerability profile</p>
              <h3 className="history-title text-lg font-semibold text-slate-50">What could go wrong?</h3>
              <p className="history-meta mt-1 text-sm text-slate-400">
                The trend should not only celebrate opportunity; it should also surface friction, mismatch, and saturation risk.
              </p>
              <ul className="trends-framework-points mt-3">
                <li>Risk tolerance alignment: {summaryRisk}</li>
                <li>Competition pressure: {bestCompetition > 0 ? `${bestCompetition} nearby competitors in the strongest idea` : 'No competitor signal yet'}</li>
                <li>Decision quality improves when the user can see the downside before they commit.</li>
              </ul>
            </article>

            <article className="trends-framework-card data-card rounded-2xl border border-white/10 bg-slate-900/60 p-4 shadow-sm">
              <p className="trends-framework-kicker">4. Why now metric</p>
              <h3 className="history-title text-lg font-semibold text-slate-50">Why this opportunity is timely</h3>
              <p className="history-meta mt-1 text-sm text-slate-400">
                The key proof is not just the score. It is whether the page can show recent activity, repeated scans, and a clear fit to the user profile.
              </p>
              <ul className="trends-framework-points mt-3">
                <li>Recent market scans: {bestScanCount}</li>
                <li>Total options evaluated: {totalOptions}</li>
                <li>Strong opportunities identified: {strongOptions}</li>
              </ul>
            </article>
          </section>
        )}

        {summary && (
          <section className="trends-decision-strip rounded-2xl border border-white/10 bg-slate-900/60 p-4 shadow-sm">
            <div>
              <p className="trends-framework-kicker">First metric to check</p>
              <h3 className="history-title text-lg font-semibold text-slate-50">Local demand versus current supply</h3>
              <p className="history-meta mt-1 text-sm text-slate-400">
                If the strongest option has a high score, few competitors, and recent scan activity, it is easier to pitch as a real opportunity instead of a generic trend.
              </p>
            </div>
            <div className="trends-decision-badge">
              <span>Opportunity score</span>
              <strong>{formatOpportunityMetric(bestScore)}</strong>
            </div>
          </section>
        )}

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
              const setupRange = item?.profile_match?.capital_range || null;
              const paybackMonths = item?.profile_match?.estimated_payback_months || null;
              return (
                <article key={item.business_key} className="data-card trends-card rounded-2xl border border-white/10 bg-slate-900/60 p-4 shadow-sm">
                  <div className="trends-card-top">
                    <div>
                      <h3 className="history-title text-lg font-semibold text-slate-50">{item.business_name}</h3>
                      <p className="history-meta mt-1 text-sm text-slate-400">
                        Competitors: {item.local_competitor_estimate} | Market scans: {item.market_scan_count}
                      </p>
                    </div>
                    <div className="trends-score-wrap">
                      <span className={`trends-score-badge ${tone}`}>{scoreLabel}</span>
                      <strong className="trends-score">{score}/100</strong>
                    </div>
                  </div>

                  <div className="trends-progress mt-3" role="presentation">
                    <span style={{ width: `${Math.max(0, Math.min(100, score))}%` }} />
                  </div>

                  <div className="trends-metric-row mt-3">
                    <div className="trends-metric-chip">
                      <span>Capital range</span>
                      <strong>{formatCurrencyRange(setupRange)}</strong>
                    </div>
                    <div className="trends-metric-chip">
                      <span>Setup</span>
                      <strong>{item?.profile_match?.business_setup || '-'}</strong>
                    </div>
                    <div className="trends-metric-chip">
                      <span>Payback</span>
                      <strong>{paybackMonths ? `${paybackMonths} months` : '-'}</strong>
                    </div>
                  </div>

                  <ul className="trends-reasons mt-3">
                    {(item.reasons || []).slice(0, 4).map((reason, index) => (
                      <li key={`${item.business_key}-reason-${index}`}>{reason}</li>
                    ))}
                  </ul>
                </article>
              );
            })}
          </div>
        )}

        {!loading && !error && hasRecommendations && comparisonSlice.length > 0 && (
          <section className="trends-comparison-card rounded-2xl border border-white/10 bg-slate-900/60 p-4 shadow-sm">
            <h3 className="history-title text-lg font-semibold text-slate-50">Quick compare</h3>
            <p className="history-meta mt-1 text-sm text-slate-400">
              This is the simplest pitch path: identify the strongest item, compare it with the next two, and show why it wins on local fit.
            </p>
            <div className="trends-comparison-list mt-4">
              {comparisonSlice.map((item, index) => (
                <div key={item.business_key} className="trends-comparison-item">
                  <div>
                    <span className="trends-comparison-rank">0{index + 1}</span>
                    <strong>{item.business_name}</strong>
                  </div>
                  <span>{item.opportunity_score}/100</span>
                </div>
              ))}
            </div>
          </section>
        )}
      </div>
    </div>
  );
}
