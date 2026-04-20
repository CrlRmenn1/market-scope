import React, { useEffect, useMemo, useState } from 'react';
import { createPortal } from 'react-dom';
import { apiUrl } from '../api';

const formatDate = (value) => {
  if (!value) return 'Unknown date';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return 'Unknown date';
  return date.toLocaleString();
};

export default function History({ user, onOpenReport }) {
  const userId = user?.user_id || user?.id;
  const [history, setHistory] = useState([]);
  const [historySearchTerm, setHistorySearchTerm] = useState('');
  const [historyScoreFilter, setHistoryScoreFilter] = useState('all');
  const [loading, setLoading] = useState(Boolean(userId));
  const [expandedHistoryId, setExpandedHistoryId] = useState(null);
  const [expandedFactorKeyByHistoryId, setExpandedFactorKeyByHistoryId] = useState({});
  const [deletingHistoryId, setDeletingHistoryId] = useState(null);
  const [openingHistoryId, setOpeningHistoryId] = useState(null);
  const [deleteCandidate, setDeleteCandidate] = useState(null);
  const [deleteError, setDeleteError] = useState('');

  const getCompetitorCount = (item) => {
    if (typeof item?.competitors_found === 'number') return item.competitors_found;
    if (Array.isArray(item?.competitor_locations)) return item.competitor_locations.length;
    return 0;
  };

  useEffect(() => {
    if (!userId) return;

    let active = true;
    setLoading(true);

    fetch(apiUrl(`/users/${userId}/history`), { cache: 'no-store' })
      .then((response) => response.json())
      .then((data) => {
        if (!active) return;
        setHistory(Array.isArray(data?.history) ? data.history : []);
      })
      .catch(() => {
        if (active) setHistory([]);
      })
      .finally(() => {
        if (active) setLoading(false);
      });

    return () => {
      active = false;
    };
  }, [userId]);

  const filteredHistory = useMemo(() => {
    const term = historySearchTerm.trim().toLowerCase();
    return history.filter((item) => {
      const score = Number(item?.viability_score || 0);
      const passesScoreFilter =
        historyScoreFilter === 'all'
          ? true
          : historyScoreFilter === '50-up'
            ? score >= 50
            : score < 50;

      if (!passesScoreFilter) return false;

      if (!term) return true;

      const businessType = String(item?.business_type || '').toLowerCase();
      const insight = String(item?.insight || '').toLowerCase();
      return businessType.includes(term) || insight.includes(term);
    });
  }, [history, historySearchTerm, historyScoreFilter]);

  const hasHistory = useMemo(() => history.length > 0, [history]);
  const hasFilteredHistory = useMemo(() => filteredHistory.length > 0, [filteredHistory]);

  const buildReportPayload = (item) => ({
    viability_score: item.viability_score,
    business_type: item.business_type || 'Saved Analysis',
    competitors_found: getCompetitorCount(item),
    competitor_locations: item.competitor_locations || [],
    target_coords: {
      lat: item.target_lat,
      lng: item.target_lng ?? item.target_lon
    },
    radius_meters: item.radius_meters || 340,
    insight: item.insight || 'No strategic insight saved for this record.',
    breakdown: getBreakdownForItem(item)
  });

  const openSavedReport = async (item) => {
    if (!userId || !item?.history_id) {
      onOpenReport?.(buildReportPayload(item));
      return;
    }

    setOpeningHistoryId(item.history_id);
    try {
      const response = await fetch(apiUrl(`/users/${userId}/history/${item.history_id}`), { cache: 'no-store' });
      const data = await response.json();

      if (response.ok && data?.history) {
        onOpenReport?.(buildReportPayload(data.history));
      } else {
        onOpenReport?.(buildReportPayload(item));
      }
    } catch {
      onOpenReport?.(buildReportPayload(item));
    } finally {
      setOpeningHistoryId(null);
    }
  };

  const getFallbackBreakdown = (item) => {
    const competitorCount = getCompetitorCount(item);
    const saturationScore = competitorCount <= 0 ? 25 : competitorCount === 1 ? 20 : competitorCount <= 3 ? 15 : competitorCount <= 5 ? 10 : 5;
    const total = item?.viability_score || 0;
    const split = Math.max(0, Math.min(25, Math.round((total - saturationScore) / 3)));
    const legacyNote = 'Legacy record estimate. Run this location again for exact saved factor values.';

    return {
      zoning: { score: split, status: 'Legacy Estimate', description: legacyNote, details: legacyNote, estimated: true },
      hazard: { score: split, status: 'Legacy Estimate', description: legacyNote, details: legacyNote, estimated: true },
      demand: { score: split, status: 'Legacy Estimate', description: legacyNote, details: legacyNote, estimated: true },
      saturation: {
        score: saturationScore,
        status: 'Derived from competitors',
        description: `${competitorCount} nearby competitor${competitorCount === 1 ? '' : 's'} in saved record.`,
        details: 'Mapped from saved competitor density to a 0-25 scale.',
        estimated: true
      }
    };
  };

  const getBreakdownForItem = (item) => {
    if (item?.breakdown && typeof item.breakdown === 'object' && Object.keys(item.breakdown).length > 0) {
      return item.breakdown;
    }
    return getFallbackBreakdown(item);
  };

  const getFactorLabel = (key) => {
    if (key === 'demand') return 'Infrastructure Demand';
    if (key === 'hazard') return 'Hazard Exposure';
    if (key === 'zoning') return 'Zoning Fit';
    if (key === 'saturation') return 'Market Saturation';
    return key;
  };

  const getFactorTone = (score) => {
    if (score >= 20) return '#4ade80';
    if (score >= 10) return '#facc15';
    return '#f87171';
  };

  const getFactorSummary = (factor) => {
    const description = factor?.description || '';
    const details = factor?.details || '';
    return [description, details].filter(Boolean).join(' ');
  };

  const toggleFactor = (historyId, factorKey) => {
    setExpandedFactorKeyByHistoryId((current) => ({
      ...current,
      [historyId]: current[historyId] === factorKey ? null : factorKey
    }));
  };

  const handleDeleteHistory = async (item) => {
    if (!userId || !item?.history_id) return;

    setDeletingHistoryId(item.history_id);
    setDeleteError('');
    try {
      const response = await fetch(apiUrl(`/users/${userId}/history/${item.history_id}`), {
        method: 'DELETE'
      });
      const data = await response.json();
      if (!response.ok && response.status !== 404) {
        throw new Error(data.detail || 'Unable to delete history item');
      }

      setHistory((current) => current.filter((entry) => entry.history_id !== item.history_id));
      setExpandedHistoryId((current) => (current === item.history_id ? null : current));
      setExpandedFactorKeyByHistoryId((current) => {
        const next = { ...current };
        delete next[item.history_id];
        return next;
      });
      setDeleteCandidate(null);
    } catch (error) {
      setDeleteError(error.message || 'Unable to delete history item');
    } finally {
      setDeletingHistoryId(null);
    }
  };

  const getFactorContext = (key, factor, item) => {
    if (key === 'saturation') {
      return `${item.competitors_found ?? 0} nearby competitor${(item.competitors_found ?? 0) === 1 ? '' : 's'}`;
    }

    if (key === 'demand') {
      return factor?.description || 'Derived from nearby anchor strength.';
    }

    if (key === 'hazard') {
      return factor?.description || 'Evaluates flood and landslide proxies.';
    }

    return factor?.description || 'Score derived from the report algorithm.';
  };

  const deleteConfirmDialog = deleteCandidate ? (
    <div className="history-confirm-overlay" role="presentation" onClick={() => setDeleteCandidate(null)}>
      <div className="history-confirm-modal" role="dialog" aria-modal="true" aria-labelledby="history-delete-title" onClick={(event) => event.stopPropagation()}>
        <p className="history-confirm-eyebrow text-[0.72rem] font-semibold uppercase tracking-[0.18em] text-rose-300">Confirm deletion</p>
        <h3 id="history-delete-title" className="history-confirm-title mt-2 text-xl font-semibold text-slate-50">Delete {deleteCandidate.business_type}?</h3>
        <p className="history-confirm-text mt-3 text-sm leading-6 text-slate-300">
          This removes the saved analysis from your history. You can run the same site again later, but this saved copy will be gone.
        </p>
        {deleteError && <p className="history-confirm-error mt-3 rounded-lg border border-rose-400/20 bg-rose-500/10 p-3 text-sm text-rose-200">{deleteError}</p>}
        <div className="history-confirm-actions mt-5 flex flex-col gap-3 sm:flex-row">
          <button type="button" className="edit-btn inline-flex items-center justify-center rounded-lg border border-white/10 bg-white/5 px-4 py-2.5 text-sm font-medium text-slate-100 transition hover:border-violet-400/40 hover:bg-violet-500/10" onClick={() => setDeleteCandidate(null)}>
            Cancel
          </button>
          <button type="button" className="history-delete-btn history-delete-btn-solid inline-flex items-center justify-center rounded-lg border border-rose-400/20 bg-rose-500/10 px-4 py-2.5 text-sm font-medium text-rose-200 transition hover:border-rose-300/40 hover:bg-rose-500/20 disabled:cursor-not-allowed disabled:opacity-60" onClick={() => handleDeleteHistory(deleteCandidate)} disabled={deletingHistoryId === deleteCandidate.history_id}>
            {deletingHistoryId === deleteCandidate.history_id ? 'Deleting...' : 'Delete'}
          </button>
        </div>
      </div>
    </div>
  ) : null;

  return (
    <div className="profile-page page-enter min-h-full">
      <div className="mx-auto flex w-full max-w-4xl flex-col gap-4 px-4 pb-28 pt-4 sm:px-6">
        <div className="profile-card fade-in rounded-2xl border border-white/10 bg-slate-900/70 p-5 text-left shadow-sm">
          <h2 className="profile-name mb-2 text-2xl font-semibold tracking-tight text-slate-50 sm:text-3xl">Analysis History</h2>
          <p className="profile-email text-sm text-slate-300">Previous site analyses for your account.</p>
        </div>

      {loading && <div className="data-card rounded-2xl border border-white/10 bg-slate-900/60 p-4 text-sm text-slate-300 shadow-sm">Loading history...</div>}

      {!loading && !hasHistory && (
        <div className="history-empty-state flex items-center gap-4 rounded-2xl border border-white/10 bg-slate-900/60 p-4 shadow-sm">
          <div className="history-empty-icon flex h-10 w-10 items-center justify-center rounded-lg bg-violet-500/10 text-violet-200" aria-hidden="true">
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <path d="M9 11l3 3L22 4"></path>
              <path d="M21 12v7a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11"></path>
            </svg>
          </div>
          <div>
            <p className="history-empty-title text-lg font-semibold text-slate-50">No saved analyses yet</p>
            <p className="history-empty-subtitle mt-1 text-sm leading-6 text-slate-300">Run a site analysis from the map and your results will appear here automatically.</p>
          </div>
        </div>
      )}

      {!loading && hasHistory && (
        <>
          <div className="data-card mt-4 rounded-2xl border border-white/10 bg-slate-900/60 p-4 shadow-sm">
            <div className="history-tools-grid grid gap-4 lg:grid-cols-2">
              <div className="input-group" style={{ marginBottom: 0 }}>
                <label>Search Business</label>
                <input
                  value={historySearchTerm}
                  onChange={(e) => setHistorySearchTerm(e.target.value)}
                  placeholder="Search by business type..."
                  className="history-search-input w-full rounded-lg border border-white/10 bg-slate-950/80 px-3 py-2.5 text-sm text-white outline-none placeholder:text-slate-500 focus:border-violet-400 focus:ring-2 focus:ring-violet-400/20"
                />
              </div>
              <div className="input-group" style={{ marginBottom: 0 }}>
                <label>Type</label>
                <select
                  value={historyScoreFilter}
                  onChange={(e) => setHistoryScoreFilter(e.target.value)}
                  className="app-select w-full rounded-lg border border-white/10 bg-slate-950/80 px-3 py-2.5 text-sm text-white outline-none focus:border-violet-400 focus:ring-2 focus:ring-violet-400/20"
                >
                  <option value="all">All</option>
                  <option value="50-up">50 points and up</option>
                  <option value="below-50">Below 50 points</option>
                </select>
              </div>
            </div>
          </div>

          <div className="history-list mt-6 flex flex-col gap-4">
          {filteredHistory.map((item) => (
            <div className="data-card history-card rounded-2xl border border-white/10 bg-slate-900/60 p-4 shadow-sm" key={item.history_id}>
              <button
                type="button"
                className="history-card-top history-card-button flex w-full items-start justify-between gap-4 rounded-lg border border-white/10 bg-white/5 px-4 py-3 text-left transition hover:border-violet-400/30 hover:bg-violet-500/10"
                onClick={() => openSavedReport(item)}
              >
                <div>
                  <h3 className="history-title text-lg font-semibold text-slate-50">{item.business_type}</h3>
                  <p className="history-meta mt-1 text-sm text-slate-400">{formatDate(item.created_at)}</p>
                </div>
                <span className="profile-badge inline-flex rounded-full border border-violet-400/20 bg-violet-500/10 px-3 py-1 text-xs font-medium text-violet-200">Score {item.viability_score}</span>
              </button>

              <div className="history-summary mt-3 rounded-lg border border-white/10 bg-black/10 px-4 py-2.5 text-sm text-slate-300">
                <span>Radius: {item.radius_meters ?? '—'}m</span>
              </div>

              <p className="factor-desc mt-3 text-sm leading-6 text-slate-300">
                {item.insight}
              </p>

              <div className="history-actions-row mt-3 flex flex-col gap-3 sm:flex-row">
                <button
                  type="button"
                  className="edit-btn history-open-btn inline-flex items-center justify-center rounded-lg border border-white/10 bg-white/5 px-4 py-2.5 text-sm font-medium text-slate-100 transition hover:border-violet-400/40 hover:bg-violet-500/10"
                  onClick={() => openSavedReport(item)}
                >
                  {openingHistoryId === item.history_id ? 'Opening...' : 'Open report'}
                </button>
                <button
                  type="button"
                  className="history-delete-btn inline-flex items-center justify-center rounded-lg border border-rose-400/20 bg-rose-500/10 px-4 py-2.5 text-sm font-medium text-rose-200 transition hover:border-rose-300/40 hover:bg-rose-500/20"
                  onClick={() => setDeleteCandidate(item)}
                  disabled={deletingHistoryId === item.history_id}
                >
                  {deletingHistoryId === item.history_id ? 'Deleting...' : 'Delete history'}
                </button>
              </div>

              <button
                type="button"
                className="history-breakdown-toggle mt-3 inline-flex w-full items-center justify-center rounded-lg border border-white/10 bg-white/5 px-4 py-2.5 text-sm font-medium text-slate-100 transition hover:border-violet-400/40 hover:bg-violet-500/10"
                onClick={() => setExpandedHistoryId((current) => (current === item.history_id ? null : item.history_id))}
              >
                {expandedHistoryId === item.history_id ? 'Hide metric breakdown' : 'Show metric breakdown'}
              </button>

              {expandedHistoryId === item.history_id && (
                <div className="history-breakdown mt-3 rounded-xl border border-white/10 bg-black/20 p-3">
                  <p className="settings-label mb-2 text-[0.72rem] font-semibold uppercase tracking-[0.18em] text-slate-400">Metric Breakdown</p>
                  <div className="history-breakdown-grid grid gap-3 sm:grid-cols-2">
                    {Object.entries(getBreakdownForItem(item)).map(([key, factor]) => {
                      const isOpen = expandedFactorKeyByHistoryId[item.history_id] === key;
                      const score = factor?.score || 0;
                      const fillWidth = `${Math.max(0, Math.min(100, (score / 25) * 100))}%`;
                      const factorContext = getFactorContext(key, factor, item);

                      return (
                        <button
                          type="button"
                          className={`history-breakdown-item ${isOpen ? 'is-open' : ''} history-breakdown-item-${key} flex flex-col gap-3 rounded-lg border border-white/10 bg-white/5 p-3 text-left transition hover:border-violet-400/30 hover:bg-violet-500/10`}
                          key={key}
                          onClick={() => toggleFactor(item.history_id, key)}
                          aria-expanded={isOpen}
                        >
                          <div className="history-mini-header flex items-center justify-between gap-3">
                            <span className="settings-value capitalize text-sm font-semibold text-slate-100">{getFactorLabel(key)}</span>
                            <span className="history-mini-score text-sm font-bold" style={{ color: getFactorTone(score) }}>
                              {score}/25
                            </span>
                          </div>
                          <div className="history-mini-track h-2 rounded-full bg-white/10" aria-hidden="true">
                            <div className="history-mini-fill h-2 rounded-full" style={{ width: fillWidth, background: getFactorTone(score) }} />
                          </div>
                          <div className="history-mini-meta text-xs leading-5 text-slate-300">
                            <strong className="block text-[0.72rem] uppercase tracking-[0.16em] text-slate-400">{factor?.status || 'Factor detail'}</strong>
                            <span className="block mt-1">{factorContext}</span>
                            {isOpen && <span className="block mt-1">{getFactorSummary(factor)}</span>}
                          </div>
                        </button>
                      );
                    })}
                  </div>
                </div>
              )}
            </div>
          ))}
          {!hasFilteredHistory && (
            <div className="data-card rounded-2xl border border-white/10 bg-slate-900/60 p-4 text-sm text-slate-300 shadow-sm">No history records match your search.</div>
          )}
        </div>
        </>
      )}

      {typeof document !== 'undefined' && deleteConfirmDialog && createPortal(deleteConfirmDialog, document.body)}
      </div>
    </div>
  );
}