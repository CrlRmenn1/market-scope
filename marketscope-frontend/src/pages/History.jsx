import React, { useEffect, useMemo, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import { apiUrl } from '../api';
import { getBusinessTypeKey, getBusinessTypeLabel } from '../utils/businessTypes';
import useIsDesktop from '../utils/useIsDesktop';

// Floor so a very fast (e.g. cache-adjacent) fetch doesn't flash the loading
// modal open-and-closed; cache hits skip the modal entirely (see openSavedReport).
const MIN_OPENING_MODAL_MS = 300;

const formatDate = (value) => {
  if (!value) return 'Unknown date';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return 'Unknown date';
  return date.toLocaleString(undefined, { month: 'short', day: 'numeric', year: 'numeric', hour: 'numeric', minute: '2-digit' });
};

const getScoreTone = (score) => {
  const value = Number(score || 0);
  if (value >= 75) return 'high';
  if (value >= 55) return 'medium';
  return 'low';
};

const getScoreLabel = (score) => {
  const value = Number(score || 0);
  if (value >= 75) return 'High Opportunity';
  if (value >= 55) return 'Promising';
  return 'Watchlist';
};

const groupHistoryByDate = (items) => {
  const startOfDay = (d) => new Date(d.getFullYear(), d.getMonth(), d.getDate());
  const today = startOfDay(new Date());
  const yesterday = new Date(today);
  yesterday.setDate(today.getDate() - 1);
  const weekAgo = new Date(today);
  weekAgo.setDate(today.getDate() - 6);
  const monthAgo = new Date(today);
  monthAgo.setDate(today.getDate() - 29);

  const groups = [];
  const byLabel = new Map();

  items.forEach((item) => {
    const created = new Date(item.created_at);
    let label = 'Earlier';
    if (!Number.isNaN(created.getTime())) {
      const day = startOfDay(created);
      if (day.getTime() === today.getTime()) label = 'Today';
      else if (day.getTime() === yesterday.getTime()) label = 'Yesterday';
      else if (day >= weekAgo) label = 'This Week';
      else if (day >= monthAgo) label = 'This Month';
    }

    if (!byLabel.has(label)) {
      const group = { label, items: [] };
      byLabel.set(label, group);
      groups.push(group);
    }
    byLabel.get(label).items.push(item);
  });

  return groups;
};

export default function History({ user, onOpenReport, getCachedReport, onCacheReport, onEvictCachedReports }) {
  const userId = user?.user_id || user?.id;
  const [history, setHistory] = useState([]);
  const [historySearchTerm, setHistorySearchTerm] = useState('');
  const [historyScoreFilter, setHistoryScoreFilter] = useState('all');
  const [loading, setLoading] = useState(Boolean(userId));
  const [expandedHistoryId, setExpandedHistoryId] = useState(null);
  const [expandedFactorKeyByHistoryId, setExpandedFactorKeyByHistoryId] = useState({});
  const [deletingHistoryId, setDeletingHistoryId] = useState(null);
  const [openingHistoryId, setOpeningHistoryId] = useState(null);
  const [isOpeningModalVisible, setIsOpeningModalVisible] = useState(false);
  const openingStartedAtRef = useRef(0);
  const [deleteCandidate, setDeleteCandidate] = useState(null);
  const [deleteError, setDeleteError] = useState('');
  const [selectedHistoryIds, setSelectedHistoryIds] = useState([]);
  const [deleteMode, setDeleteMode] = useState(false);
  const [showBulkDeleteConfirm, setShowBulkDeleteConfirm] = useState(false);
  const [bulkDeleting, setBulkDeleting] = useState(false);

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
      const businessLabel = String(getBusinessTypeLabel(item?.business_type || '') || '').toLowerCase();
      const insight = String(item?.insight || '').toLowerCase();
      return businessType.includes(term) || businessLabel.includes(term) || insight.includes(term);
    });
  }, [history, historySearchTerm, historyScoreFilter]);

  const hasHistory = useMemo(() => history.length > 0, [history]);
  const isDesktop = useIsDesktop();
  const hasFilteredHistory = useMemo(() => filteredHistory.length > 0, [filteredHistory]);
  const visibleHistoryIds = useMemo(() => filteredHistory.map((item) => item.history_id).filter(Boolean), [filteredHistory]);
  const selectedVisibleHistoryIds = useMemo(
    () => selectedHistoryIds.filter((historyId) => visibleHistoryIds.includes(historyId)),
    [selectedHistoryIds, visibleHistoryIds]
  );
  const allVisibleSelected = hasFilteredHistory && selectedVisibleHistoryIds.length === visibleHistoryIds.length;
  const someVisibleSelected = selectedVisibleHistoryIds.length > 0 && !allVisibleSelected;

  useEffect(() => {
    setSelectedHistoryIds((current) => current.filter((historyId) => history.some((item) => item.history_id === historyId)));
  }, [history]);

  useEffect(() => {
    if (!deleteMode) {
      setSelectedHistoryIds([]);
      setShowBulkDeleteConfirm(false);
    }
  }, [deleteMode]);

  const buildReportPayload = (item) => ({
    viability_score: item.viability_score,
    business_type: getBusinessTypeKey(item.business_type || ''),
    business_label: getBusinessTypeLabel(item.business_type || '') || 'Saved Analysis',
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

    // Already fetched (and fully resolved) this session - skip the network
    // entirely, no loading modal needed since there's nothing to wait for.
    const cached = getCachedReport?.(item.history_id);
    if (cached) {
      onOpenReport?.(cached);
      return;
    }

    setOpeningHistoryId(item.history_id);
    setIsOpeningModalVisible(true);
    openingStartedAtRef.current = Date.now();
    try {
      const response = await fetch(apiUrl(`/users/${userId}/history/${item.history_id}`), { cache: 'no-store' });
      const data = await response.json();

      if (response.ok && data?.history) {
        const payload = buildReportPayload(data.history);

        // If the saved history entry looks legacy (missing current saturation subcomponents),
        // attempt to re-run the live analysis so the opened report matches the current Report view.
        const hasSaturationSubcomponents = payload.breakdown && (payload.breakdown.competition_density || payload.breakdown.road_access || payload.breakdown.anchor_proximity || payload.breakdown.building_density);

        if (!hasSaturationSubcomponents) {
          try {
            const analyzeResp = await fetch(apiUrl('/analyze'), {
              method: 'POST',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify({
                lat: payload.target_coords?.lat,
                lon: payload.target_coords?.lng,
                business_type: payload.business_type,
                radius: payload.radius_meters || 340,
                user_id: userId,
                history_id: item.history_id
              })
            });

            const analyzeData = await analyzeResp.json();
            if (analyzeResp.ok && analyzeData) {
              onCacheReport?.(item.history_id, analyzeData);
              onOpenReport?.(analyzeData);
              return;
            }
          } catch (err) {
            // Legacy re-scan failed - fall back to the saved (still-legacy) payload below,
            // and deliberately don't cache it, so the next open retries the self-heal.
          }
        } else {
          onCacheReport?.(item.history_id, payload);
        }

        onOpenReport?.(payload);
      } else {
        onOpenReport?.(buildReportPayload(item));
      }
    } catch {
      onOpenReport?.(buildReportPayload(item));
    } finally {
      setOpeningHistoryId(null);
      const elapsed = Date.now() - openingStartedAtRef.current;
      const remaining = MIN_OPENING_MODAL_MS - elapsed;
      if (remaining > 0) {
        setTimeout(() => setIsOpeningModalVisible(false), remaining);
      } else {
        setIsOpeningModalVisible(false);
      }
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
    if (key === 'competition_density') return 'Competition Density';
    if (key === 'road_access') return 'Road Access';
    if (key === 'anchor_proximity') return 'Traffic Generators';
    if (key === 'building_density') return 'Building Density';
    if (key === 'saturation') return 'Market Saturation';
    return key;
  };

  const getFactorTone = (score) => {
    if (score >= 20) return 'var(--trend-up)';
    if (score >= 10) return 'var(--trend-neutral)';
    return 'var(--trend-down)';
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
      onEvictCachedReports?.(item.history_id);
      setSelectedHistoryIds((current) => current.filter((historyId) => historyId !== item.history_id));
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

  const toggleHistorySelection = (historyId) => {
    if (!historyId) return;

    setSelectedHistoryIds((current) => (
      current.includes(historyId)
        ? current.filter((value) => value !== historyId)
        : [...current, historyId]
    ));
  };

  const toggleVisibleSelection = () => {
    if (allVisibleSelected) {
      setSelectedHistoryIds((current) => current.filter((historyId) => !visibleHistoryIds.includes(historyId)));
      return;
    }

    setSelectedHistoryIds((current) => {
      const next = new Set(current);
      visibleHistoryIds.forEach((historyId) => next.add(historyId));
      return Array.from(next);
    });
  };

  const handleBulkDelete = async () => {
    if (!userId || selectedVisibleHistoryIds.length === 0) return;

    setDeleteError('');
    setBulkDeleting(true);

    try {
      const results = await Promise.all(selectedVisibleHistoryIds.map(async (historyId) => {
        const response = await fetch(apiUrl(`/users/${userId}/history/${historyId}`), {
          method: 'DELETE'
        });
        const data = await response.json();
        return { historyId, response, data };
      }));

      const failedResult = results.find(({ response }) => !response.ok && response.status !== 404);
      if (failedResult) {
        throw new Error(failedResult.data?.detail || 'Unable to delete one or more history items');
      }

      setHistory((current) => current.filter((entry) => !selectedVisibleHistoryIds.includes(entry.history_id)));
      onEvictCachedReports?.(selectedVisibleHistoryIds);
      setExpandedHistoryId((current) => (selectedVisibleHistoryIds.includes(current) ? null : current));
      setExpandedFactorKeyByHistoryId((current) => {
        const next = { ...current };
        selectedVisibleHistoryIds.forEach((historyId) => {
          delete next[historyId];
        });
        return next;
      });
      setSelectedHistoryIds((current) => current.filter((historyId) => !selectedVisibleHistoryIds.includes(historyId)));
      setShowBulkDeleteConfirm(false);
      setDeleteMode(false);
    } catch (error) {
      setDeleteError(error.message || 'Unable to delete selected history items');
    } finally {
      setBulkDeleting(false);
    }
  };

  const handleDeleteModeAction = async () => {
    if (!deleteMode) {
      setDeleteMode(true);
      return;
    }

    setDeleteMode(false);
  };

  const getFactorContext = (key, factor, item) => {
    if (key === 'saturation') {
      return 'Composite score from competition, road access, traffic generators, and built-form density.';
    }

    if (key === 'demand') {
      return factor?.description || 'Derived from nearby anchor strength.';
    }

    if (key === 'competition_density') {
      return factor?.description || 'Weighted inverse-density competitor scan.';
    }

    if (key === 'road_access') {
      return factor?.description || 'Nearest road class accessibility fit.';
    }

    if (key === 'anchor_proximity') {
      return factor?.description || 'Traffic-generator proximity score.';
    }

    if (key === 'building_density') {
      return factor?.description || 'Built-form intensity around the site.';
    }

    if (key === 'hazard') {
      return factor?.description || 'Evaluates flood and landslide proxies.';
    }

    return factor?.description || 'Score derived from the report algorithm.';
  };

  const deleteConfirmDialog = deleteCandidate ? (
    <div className="history-confirm-overlay" role="presentation" onClick={() => setDeleteCandidate(null)}>
      <div className="history-confirm-modal" role="dialog" aria-modal="true" aria-labelledby="history-delete-title" onClick={(event) => event.stopPropagation()}>
        <p className="history-confirm-eyebrow text-[0.72rem] font-semibold uppercase tracking-[0.08em] text-[var(--trend-down)]">Confirm deletion</p>
        <h3 id="history-delete-title" className="history-confirm-title mt-2 text-xl font-semibold text-[var(--text-main)]">Delete {getBusinessTypeLabel(deleteCandidate.business_type)}?</h3>
        <p className="history-confirm-text mt-3 text-sm leading-6 text-[var(--text-muted)]">
          This removes the saved analysis from your history. You can run the same site again later, but this saved copy will be gone.
        </p>
        {deleteError && <p className="history-confirm-error mt-3 rounded-lg border border-[var(--border-color)] bg-[var(--trend-down-bg)] p-3 text-sm text-[var(--trend-down)]">{deleteError}</p>}
        <div className="history-confirm-actions mt-5 flex flex-col gap-3 sm:flex-row">
          <button type="button" className="edit-btn inline-flex items-center justify-center rounded-xl border border-[var(--border-color)] bg-[var(--bg-sheet)] px-4 py-2.5 text-sm font-medium text-[var(--text-main)] transition hover:border-[var(--border-strong)] hover:bg-[var(--accent-hover)]" onClick={() => setDeleteCandidate(null)}>
            Cancel
          </button>
          <button type="button" className="history-delete-btn history-delete-btn-solid inline-flex items-center justify-center rounded-xl bg-[var(--trend-down)] px-4 py-2.5 text-sm font-semibold text-white transition hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-60" onClick={() => handleDeleteHistory(deleteCandidate)} disabled={deletingHistoryId === deleteCandidate.history_id}>
            {deletingHistoryId === deleteCandidate.history_id ? 'Deleting...' : 'Delete'}
          </button>
        </div>
      </div>
    </div>
  ) : null;

  const bulkDeleteConfirmDialog = showBulkDeleteConfirm ? (
    <div className="history-confirm-overlay" role="presentation" onClick={() => { if (!bulkDeleting) setShowBulkDeleteConfirm(false); }}>
      <div className="history-confirm-modal" role="dialog" aria-modal="true" aria-labelledby="history-bulk-delete-title" onClick={(event) => event.stopPropagation()}>
        <p className="history-confirm-eyebrow text-[0.72rem] font-semibold uppercase tracking-[0.08em] text-[var(--trend-down)]">Confirm deletion</p>
        <h3 id="history-bulk-delete-title" className="history-confirm-title mt-2 text-xl font-semibold text-[var(--text-main)]">
          Delete {selectedVisibleHistoryIds.length} selected {selectedVisibleHistoryIds.length === 1 ? 'analysis' : 'analyses'}?
        </h3>
        <p className="history-confirm-text mt-3 text-sm leading-6 text-[var(--text-muted)]">
          This removes the selected saved analyses from your history. You can run the same sites again later, but these saved copies will be gone.
        </p>
        {deleteError && <p className="history-confirm-error mt-3 rounded-lg border border-[var(--border-color)] bg-[var(--trend-down-bg)] p-3 text-sm text-[var(--trend-down)]">{deleteError}</p>}
        <div className="history-confirm-actions mt-5 flex flex-col gap-3 sm:flex-row">
          <button type="button" className="edit-btn inline-flex items-center justify-center rounded-xl border border-[var(--border-color)] bg-[var(--bg-sheet)] px-4 py-2.5 text-sm font-medium text-[var(--text-main)] transition hover:border-[var(--border-strong)] hover:bg-[var(--accent-hover)] disabled:cursor-not-allowed disabled:opacity-60" onClick={() => setShowBulkDeleteConfirm(false)} disabled={bulkDeleting}>
            Cancel
          </button>
          <button type="button" className="history-delete-btn history-delete-btn-solid inline-flex items-center justify-center rounded-xl bg-[var(--trend-down)] px-4 py-2.5 text-sm font-semibold text-white transition hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-60" onClick={handleBulkDelete} disabled={bulkDeleting || selectedVisibleHistoryIds.length === 0}>
            {bulkDeleting ? 'Deleting...' : 'Delete'}
          </button>
        </div>
      </div>
    </div>
  ) : null;

  const openingReportDialog = isOpeningModalVisible ? (
    <div className="history-confirm-overlay" role="presentation">
      <div className="history-confirm-modal" role="dialog" aria-modal="true" aria-labelledby="history-opening-title">
        <div className="map-scan-loading">
          <p id="history-opening-title" className="map-scan-loading__title">Opening your saved analysis&hellip;</p>
          <div className="loading-taskbar">
            <div className="task-item delay-1">
              <span className="task-text">Fetching saved report</span>
              <span className="task-spinner" aria-hidden="true" />
            </div>
          </div>
        </div>
      </div>
    </div>
  ) : null;

  const renderHistoryCard = (item, index) => (
                  <div
                    className={`data-card history-card card-stagger-item p-4 ${selectedHistoryIds.includes(item.history_id) ? 'ring-2 ring-[var(--focus-ring)]' : ''} ${expandedHistoryId === item.history_id ? 'history-card-expanded' : ''}`}
                    style={{ '--stagger-index': index }}
                    key={item.history_id}
                  >
                    {deleteMode && (
                      <label className="history-select-row mb-3 flex items-center gap-3 text-sm text-[var(--text-muted)]">
                        <input
                          type="checkbox"
                          checked={selectedHistoryIds.includes(item.history_id)}
                          onChange={() => toggleHistorySelection(item.history_id)}
                          className="h-5 w-5 rounded border-[var(--border-strong)] bg-[var(--bg-sheet)] text-[var(--accent)] focus:ring-[var(--focus-ring)]"
                        />
                        <span>{selectedHistoryIds.includes(item.history_id) ? 'Selected for deletion' : 'Select this report'}</span>
                      </label>
                    )}

                    <div className="history-card-top flex w-full items-start justify-between gap-4">
                      <div className="min-w-0">
                        <h3 className="history-title text-lg font-semibold text-[var(--text-main)]">{getBusinessTypeLabel(item.business_type)}</h3>
                        <p className="history-meta mt-0.5 text-sm text-[var(--text-muted)]">{formatDate(item.created_at)}</p>
                      </div>
                      <div className="history-score-block flex flex-none flex-col items-end gap-1">
                        <span
                          className="text-2xl font-bold tabular-nums leading-none text-[var(--text-main)]"
                          aria-label={`Viability score ${item.viability_score} out of 100`}
                        >
                          {item.viability_score}
                        </span>
                        <span className={`trends-score-badge ${getScoreTone(item.viability_score)}`}>{getScoreLabel(item.viability_score)}</span>
                      </div>
                    </div>

                    <div className="mt-3 flex flex-wrap gap-2">
                      <span className="inline-flex items-center gap-1.5 rounded-full border border-[var(--border-color)] px-2.5 py-1 text-xs font-medium tabular-nums text-[var(--text-muted)]">
                        <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true">
                          <circle cx="12" cy="12" r="10" /><circle cx="12" cy="12" r="4" />
                        </svg>
                        Radius {item.radius_meters ?? '—'}m
                      </span>
                      <span className="inline-flex items-center gap-1.5 rounded-full border border-[var(--border-color)] px-2.5 py-1 text-xs font-medium tabular-nums text-[var(--text-muted)]">
                        <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true">
                          <path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2" /><circle cx="9" cy="7" r="4" /><path d="M23 21v-2a4 4 0 0 0-3-3.87" /><path d="M16 3.13a4 4 0 0 1 0 7.75" />
                        </svg>
                        {getCompetitorCount(item)} competitors
                      </span>
                    </div>

                    <p className="factor-desc mt-3 line-clamp-2 text-sm leading-6 text-[var(--text-muted)]">
                      {item.insight}
                    </p>

                    <div className="history-actions-row mt-4 flex items-center gap-2 border-t border-[var(--border-color)] pt-3">
                      <button
                        type="button"
                        className="history-open-btn inline-flex min-h-[44px] items-center justify-center gap-2 rounded-xl bg-[var(--btn-primary-bg)] px-4 py-2.5 text-sm font-semibold text-[var(--btn-primary-text)] transition hover:bg-[var(--btn-primary-hover)] disabled:cursor-not-allowed disabled:opacity-60"
                        onClick={() => openSavedReport(item)}
                        disabled={openingHistoryId === item.history_id}
                      >
                        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true">
                          <path d="M14 3h7v7" /><path d="M21 3 10 14" /><path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6" />
                        </svg>
                        {openingHistoryId === item.history_id ? 'Opening...' : 'Open report'}
                      </button>
                      <button
                        type="button"
                        className="history-breakdown-toggle inline-flex min-h-[44px] items-center gap-1.5 rounded-xl px-3 py-2.5 text-sm font-medium text-[var(--text-muted)] transition hover:bg-[var(--accent-hover)] hover:text-[var(--text-main)]"
                        onClick={() => setExpandedHistoryId((current) => (current === item.history_id ? null : item.history_id))}
                        aria-expanded={expandedHistoryId === item.history_id}
                      >
                        Breakdown
                        <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" aria-hidden="true" style={{ transform: expandedHistoryId === item.history_id ? 'rotate(180deg)' : 'none', transition: 'transform 200ms ease' }}>
                          <path d="m6 9 6 6 6-6" />
                        </svg>
                      </button>
                      {!deleteMode && (
                        <button
                          type="button"
                          className="history-delete-btn ml-auto inline-flex min-h-[44px] min-w-[44px] items-center justify-center rounded-xl border border-transparent text-[var(--trend-down)] transition hover:border-[var(--trend-down)] hover:bg-[var(--trend-down-bg)] disabled:cursor-not-allowed disabled:opacity-60"
                          onClick={() => setDeleteCandidate(item)}
                          disabled={deletingHistoryId === item.history_id}
                          aria-label={`Delete ${getBusinessTypeLabel(item.business_type)} analysis`}
                          title="Delete this analysis"
                        >
                          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true">
                            <path d="M3 6h18" /><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6" /><path d="M8 6V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2" />
                          </svg>
                        </button>
                      )}
                    </div>

                    {expandedHistoryId === item.history_id && (
                      <div className="history-breakdown mt-3 border-t border-[var(--border-color)] pt-3">
                        <p className="eyebrow-label mb-2">Metric Breakdown</p>
                        <div className="history-breakdown-grid grid gap-3 sm:grid-cols-2">
                          {Object.entries(getBreakdownForItem(item)).map(([key, factor]) => {
                            const isOpen = expandedFactorKeyByHistoryId[item.history_id] === key;
                            const score = factor?.score || 0;
                            const fillWidth = `${Math.max(0, Math.min(100, (score / 25) * 100))}%`;
                            const factorContext = getFactorContext(key, factor, item);

                            return (
                              <button
                                type="button"
                                className={`history-breakdown-item ${isOpen ? 'is-open' : ''} history-breakdown-item-${key} flex flex-col gap-3 rounded-xl border border-[var(--border-color)] p-3 text-left transition hover:border-[var(--border-strong)] hover:bg-[var(--accent-hover)]`}
                                key={key}
                                onClick={() => toggleFactor(item.history_id, key)}
                                aria-expanded={isOpen}
                              >
                                <div className="history-mini-header flex items-center justify-between gap-3">
                                  <span className="settings-value capitalize text-sm font-semibold text-[var(--text-main)]">{getFactorLabel(key)}</span>
                                  <span className="history-mini-score text-sm font-bold" style={{ color: getFactorTone(score) }}>
                                    {score}/25
                                  </span>
                                </div>
                                <div className="history-mini-track h-2 rounded-full bg-[var(--accent-hover)]" aria-hidden="true">
                                  <div className="history-mini-fill h-2 rounded-full" style={{ width: fillWidth, background: getFactorTone(score) }} />
                                </div>
                                <div className="history-mini-meta text-xs leading-5 text-[var(--text-muted)]">
                                  <strong className="block text-[0.72rem] uppercase tracking-[0.08em] text-[var(--text-muted)]">{factor?.status || 'Factor detail'}</strong>
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
  );

  return (
    <div className="profile-page page-enter min-h-full">
      <div className="mx-auto flex w-full max-w-8xl flex-col gap-4 px-6 pb-28 pt-4 sm:px-8">
        <div className="profile-card fade-in p-5 text-left">
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div>
              <p className="eyebrow-label mb-2">Your Archive</p>
              <h2 className="profile-name mb-2 text-2xl font-semibold tracking-tight text-[var(--text-main)] sm:text-3xl">Analysis History</h2>
              <p className="profile-email text-sm text-[var(--text-muted)]">Previous site analyses for your account.</p>
            </div>
            {!loading && hasHistory && (
              <span className="inline-flex items-center gap-2 rounded-full border border-[var(--border-color)] bg-[var(--accent-hover)] px-3 py-1.5 text-xs font-semibold tabular-nums text-[var(--accent)]">
                <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true">
                  <path d="M9 11l3 3L22 4" /><path d="M21 12v7a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11" />
                </svg>
                {history.length} saved
              </span>
            )}
          </div>

          {!loading && hasHistory && (
            <div className="history-tools-grid mt-5 grid gap-4 border-t border-[var(--border-color)] pt-4 lg:grid-cols-2">
              <div className="input-group" style={{ marginBottom: 0 }}>
                <label>Search Business</label>
                <div className="relative">
                  <svg className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-[var(--text-muted)]" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true">
                    <circle cx="11" cy="11" r="8" /><path d="m21 21-4.35-4.35" />
                  </svg>
                  <input
                    value={historySearchTerm}
                    onChange={(e) => setHistorySearchTerm(e.target.value)}
                    placeholder="Search by business type..."
                    className="history-search-input w-full rounded-xl border border-[var(--border-color)] bg-[var(--bg-sheet)] py-2.5 !pl-10 pr-3 text-sm text-[var(--text-main)] outline-none placeholder:text-[var(--text-muted)] focus:border-[var(--accent)] focus:ring-2 focus:ring-[var(--focus-ring)]"
                  />
                </div>
              </div>
              <div className="input-group" style={{ marginBottom: 0 }}>
                <div className="flex items-end gap-3">
                  <div className="flex-1">
                    <label>Score Filter</label>
                    <select
                      value={historyScoreFilter}
                      onChange={(e) => setHistoryScoreFilter(e.target.value)}
                      className="app-select w-full rounded-xl border border-[var(--border-color)] bg-[var(--bg-sheet)] px-3 py-2.5 text-sm text-[var(--text-main)] outline-none focus:border-[var(--accent)] focus:ring-2 focus:ring-[var(--focus-ring)]"
                    >
                      <option value="all">All scores</option>
                      <option value="50-up">50 points and up</option>
                      <option value="below-50">Below 50 points</option>
                    </select>
                  </div>
                  <button
                    type="button"
                    className={`history-delete-btn history-delete-btn-solid inline-flex min-h-[44px] items-center justify-center gap-2 rounded-xl border px-4 py-2.5 text-sm font-medium transition disabled:cursor-not-allowed disabled:opacity-60 ${deleteMode ? 'border-[var(--border-strong)] bg-[var(--accent-hover)] text-[var(--text-main)]' : 'border-[var(--border-color)] bg-[var(--trend-down-bg)] text-[var(--trend-down)] hover:border-[var(--trend-down)]'}`}
                    onClick={handleDeleteModeAction}
                  >
                    <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true">
                      <path d="M3 6h18" /><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6" /><path d="M8 6V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2" />
                    </svg>
                    {deleteMode ? 'Cancel' : 'Delete'}
                  </button>
                </div>
              </div>
            </div>
          )}
        </div>

        {hasHistory && deleteMode && (
          <div className="data-card p-4">
            <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
              <button
                type="button"
                className="inline-flex items-center justify-center rounded-xl border border-[var(--border-color)] bg-[var(--bg-sheet)] px-4 py-2.5 text-sm font-medium text-[var(--text-main)] transition hover:border-[var(--border-strong)] hover:bg-[var(--accent-hover)]"
                onClick={toggleVisibleSelection}
              >
                {allVisibleSelected ? 'Clear selection' : 'Select all visible reports'}
              </button>
              <div className="flex items-center gap-3">
                <span className="text-sm text-[var(--text-muted)]">{selectedVisibleHistoryIds.length} selected</span>
                <button
                  type="button"
                  className="history-delete-btn history-delete-btn-solid inline-flex items-center justify-center rounded-xl border border-[var(--border-color)] bg-[var(--trend-down-bg)] px-4 py-2.5 text-sm font-medium text-[var(--trend-down)] transition hover:border-[var(--trend-down)] disabled:cursor-not-allowed disabled:opacity-60"
                  onClick={() => { setDeleteError(''); setShowBulkDeleteConfirm(true); }}
                  disabled={selectedVisibleHistoryIds.length === 0}
                >
                  Delete selected
                </button>
              </div>
            </div>
          </div>
        )}

        {loading && <div className="data-card p-4 text-sm text-[var(--text-muted)]">Loading history...</div>}

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
        <div className="mt-2 flex flex-col gap-5">
          {!hasFilteredHistory && (
            <div className="data-card p-4 text-sm text-[var(--text-muted)]">No history records match your search.</div>
          )}
          {groupHistoryByDate(filteredHistory).map((group) => (
            <section key={group.label} aria-label={group.label}>
              <div className="mb-3 flex items-center gap-3">
                <p className="eyebrow-label">{group.label}</p>
                <span className="h-px flex-1 bg-[var(--border-color)]" aria-hidden="true" />
                <span className="text-xs tabular-nums text-[var(--text-muted)]">{group.items.length}</span>
              </div>
              {isDesktop ? (
                <div className="history-list grid grid-cols-2 items-start gap-4">
                  <div className="flex min-w-0 flex-col gap-4 [&>*]:mb-0">
                    {group.items.map((item, index) => (index % 2 === 0 ? renderHistoryCard(item, index) : null))}
                  </div>
                  <div className="flex min-w-0 flex-col gap-4 [&>*]:mb-0">
                    {group.items.map((item, index) => (index % 2 === 1 ? renderHistoryCard(item, index) : null))}
                  </div>
                </div>
              ) : (
                <div className="history-list flex flex-col gap-4 [&>*]:mb-0">
                  {group.items.map((item, index) => renderHistoryCard(item, index))}
                </div>
              )}
            </section>
          ))}
        </div>
      )}

      {typeof document !== 'undefined' && deleteConfirmDialog && createPortal(deleteConfirmDialog, document.body)}
      {typeof document !== 'undefined' && bulkDeleteConfirmDialog && createPortal(bulkDeleteConfirmDialog, document.body)}
      {typeof document !== 'undefined' && openingReportDialog && createPortal(openingReportDialog, document.body)}
      </div>
    </div>
  );
}