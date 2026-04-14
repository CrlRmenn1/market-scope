import React, { useEffect, useMemo, useState } from 'react';
import { apiUrl } from '../lib/api';

const formatDate = (value) => {
  if (!value) return 'Unknown date';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return 'Unknown date';
  return date.toLocaleString();
};

export default function History({ user, onOpenReport }) {
  const userId = user?.user_id || user?.id;
  const [history, setHistory] = useState([]);
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

  const hasHistory = useMemo(() => history.length > 0, [history]);

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

  return (
    <div className="profile-page page-enter">
      <div className="profile-card fade-in" style={{ textAlign: 'left' }}>
        <h2 className="profile-name" style={{ marginBottom: '6px' }}>Analysis History</h2>
        <p className="profile-email">Previous site analyses for your account.</p>
      </div>

      {loading && <div className="data-card">Loading history...</div>}

      {!loading && !hasHistory && (
        <div className="history-empty-state">
          <div className="history-empty-icon" aria-hidden="true">
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <path d="M9 11l3 3L22 4"></path>
              <path d="M21 12v7a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11"></path>
            </svg>
          </div>
          <div>
            <p className="history-empty-title">No saved analyses yet</p>
            <p className="history-empty-subtitle">Run a site analysis from the map and your results will appear here automatically.</p>
          </div>
        </div>
      )}

      {!loading && hasHistory && (
        <div className="history-list mt-6">
          {history.map((item) => (
            <div className="data-card history-card" key={item.history_id}>
              <button
                type="button"
                className="history-card-top history-card-button"
                onClick={() => openSavedReport(item)}
              >
                <div>
                  <h3 className="history-title">{item.business_type}</h3>
                  <p className="history-meta">{formatDate(item.created_at)}</p>
                </div>
                <span className="profile-badge">Score {item.viability_score}</span>
              </button>

              <div className="history-summary">
                <span>Radius: {item.radius_meters ?? '—'}m</span>
              </div>

              <p className="factor-desc" style={{ marginTop: '10px' }}>
                {item.insight}
              </p>

              <div className="history-actions-row">
                <button
                  type="button"
                  className="edit-btn history-open-btn"
                  onClick={() => openSavedReport(item)}
                >
                  {openingHistoryId === item.history_id ? 'Opening...' : 'Open report'}
                </button>
                <button
                  type="button"
                  className="history-delete-btn"
                  onClick={() => setDeleteCandidate(item)}
                  disabled={deletingHistoryId === item.history_id}
                >
                  {deletingHistoryId === item.history_id ? 'Deleting...' : 'Delete history'}
                </button>
              </div>

              <button
                type="button"
                className="history-breakdown-toggle"
                onClick={() => setExpandedHistoryId((current) => (current === item.history_id ? null : item.history_id))}
              >
                {expandedHistoryId === item.history_id ? 'Hide metric breakdown' : 'Show metric breakdown'}
              </button>

              {expandedHistoryId === item.history_id && (
                <div className="history-breakdown">
                  <p className="settings-label" style={{ marginBottom: '8px' }}>Metric Breakdown</p>
                  <div className="history-breakdown-grid">
                    {Object.entries(getBreakdownForItem(item)).map(([key, factor]) => {
                      const isOpen = expandedFactorKeyByHistoryId[item.history_id] === key;
                      const score = factor?.score || 0;
                      const fillWidth = `${Math.max(0, Math.min(100, (score / 25) * 100))}%`;
                      const factorContext = getFactorContext(key, factor, item);

                      return (
                        <button
                          type="button"
                          className={`history-breakdown-item ${isOpen ? 'is-open' : ''} history-breakdown-item-${key}`}
                          key={key}
                          onClick={() => toggleFactor(item.history_id, key)}
                          aria-expanded={isOpen}
                        >
                          <div className="history-mini-header">
                            <span className="settings-value capitalize">{getFactorLabel(key)}</span>
                            <span className="history-mini-score" style={{ color: getFactorTone(score) }}>
                              {score}/25
                            </span>
                          </div>
                          <div className="history-mini-track" aria-hidden="true">
                            <div className="history-mini-fill" style={{ width: fillWidth, background: getFactorTone(score) }} />
                          </div>
                          <div className="history-mini-meta">
                            <strong>{factor?.status || 'Factor detail'}</strong>
                            <span> {factorContext}</span>
                            {isOpen && <span> {getFactorSummary(factor)}</span>}
                          </div>
                        </button>
                      );
                    })}
                  </div>
                </div>
              )}
            </div>
          ))}
        </div>
      )}

      {deleteCandidate && (
        <div className="history-confirm-overlay" role="presentation" onClick={() => setDeleteCandidate(null)}>
          <div className="history-confirm-modal" role="dialog" aria-modal="true" aria-labelledby="history-delete-title" onClick={(event) => event.stopPropagation()}>
            <p className="history-confirm-eyebrow">Confirm deletion</p>
            <h3 id="history-delete-title" className="history-confirm-title">Delete {deleteCandidate.business_type}?</h3>
            <p className="history-confirm-text">
              This removes the saved analysis from your history. You can run the same site again later, but this saved copy will be gone.
            </p>
            {deleteError && <p className="history-confirm-error">{deleteError}</p>}
            <div className="history-confirm-actions">
              <button type="button" className="edit-btn" onClick={() => setDeleteCandidate(null)}>
                Cancel
              </button>
              <button type="button" className="history-delete-btn history-delete-btn-solid" onClick={() => handleDeleteHistory(deleteCandidate)} disabled={deletingHistoryId === deleteCandidate.history_id}>
                {deletingHistoryId === deleteCandidate.history_id ? 'Deleting...' : 'Delete'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}