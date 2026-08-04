import React, { useEffect, useMemo, useState } from 'react';
import { apiUrl } from '../api';

const LEVEL_DEFS = {
  criteria: {
    n: 3,
    labels: ['zoning', 'hazard', 'saturation'],
    displayLabels: ['Zoning', 'Hazard', 'Saturation'],
  },
  saturation: {
    n: 4,
    labels: ['competition', 'road', 'anchor', 'building'],
    displayLabels: ['Competition', 'Road Access', 'Anchor Proximity', 'Building Density'],
  },
};

const SAATY_SCALE = [
  { value: 1 / 9, label: '1/9' },
  { value: 1 / 8, label: '1/8' },
  { value: 1 / 7, label: '1/7' },
  { value: 1 / 6, label: '1/6' },
  { value: 1 / 5, label: '1/5' },
  { value: 1 / 4, label: '1/4' },
  { value: 1 / 3, label: '1/3' },
  { value: 1 / 2, label: '1/2' },
  { value: 1, label: '1 — Equal importance' },
  { value: 2, label: '2' },
  { value: 3, label: '3 — Moderate importance' },
  { value: 4, label: '4' },
  { value: 5, label: '5 — Strong importance' },
  { value: 6, label: '6' },
  { value: 7, label: '7 — Very strong importance' },
  { value: 8, label: '8' },
  { value: 9, label: '9 — Extreme importance' },
];

const SAATY_RI_TABLE = { 1: 0, 2: 0, 3: 0.58, 4: 0.9, 5: 1.12, 6: 1.24, 7: 1.32, 8: 1.41, 9: 1.45, 10: 1.49 };
const CONSISTENCY_RATIO_THRESHOLD = 0.1;

const judgmentKey = (i, j) => `${i},${j}`;

const defaultJudgments = (n) => {
  const next = {};
  for (let i = 0; i < n; i += 1) {
    for (let j = i + 1; j < n; j += 1) {
      next[judgmentKey(i, j)] = 1;
    }
  }
  return next;
};

const buildMatrixFromJudgments = (judgments, n) => {
  const matrix = Array.from({ length: n }, () => Array(n).fill(1));
  for (let i = 0; i < n; i += 1) {
    for (let j = i + 1; j < n; j += 1) {
      const value = Number(judgments[judgmentKey(i, j)]) || 1;
      matrix[i][j] = value;
      matrix[j][i] = 1 / value;
    }
  }
  return matrix;
};

const computePriorityVector = (matrix) => {
  const n = matrix.length;
  const columnSums = Array.from({ length: n }, (_, j) => matrix.reduce((sum, row) => sum + row[j], 0));
  const normalized = matrix.map((row) => row.map((value, j) => value / columnSums[j]));
  return normalized.map((row) => row.reduce((sum, value) => sum + value, 0) / n);
};

const computeConsistency = (matrix, priorityVector) => {
  const n = matrix.length;
  const weightedSums = matrix.map((row) => row.reduce((sum, value, j) => sum + value * priorityVector[j], 0));
  const ratios = weightedSums.map((sum, i) => sum / priorityVector[i]);
  const lambdaMax = ratios.reduce((sum, value) => sum + value, 0) / n;
  const ri = SAATY_RI_TABLE[n] || 0;
  if (n <= 2) return { lambdaMax, ci: 0, ri, cr: 0 };
  const ci = (lambdaMax - n) / (n - 1);
  const cr = ri ? ci / ri : 0;
  return { lambdaMax, ci, ri, cr };
};

const ConsistencyBadge = ({ cr, isConsistent }) => (
  <span
    style={{
      display: 'inline-flex',
      alignItems: 'center',
      gap: 6,
      padding: '4px 10px',
      borderRadius: 999,
      fontSize: '0.8rem',
      fontWeight: 600,
      border: `1px solid ${isConsistent ? 'rgba(34,197,94,0.4)' : 'rgba(239,68,68,0.4)'}`,
      background: isConsistent ? 'rgba(34,197,94,0.12)' : 'rgba(239,68,68,0.12)',
      color: isConsistent ? 'var(--trend-up)' : 'var(--trend-down)',
    }}
  >
    {isConsistent ? 'Consistent' : 'Inconsistent'} (CR = {Number(cr ?? 0).toFixed(3)})
  </span>
);

export default function AhpWeightsManager({ token, businessTypeOptions = [] }) {
  const [level, setLevel] = useState('criteria');
  const [category, setCategory] = useState(businessTypeOptions[0]?.value || '');
  const [overview, setOverview] = useState([]);
  const [overviewLoading, setOverviewLoading] = useState(true);
  const [configMeta, setConfigMeta] = useState(null);
  const [configLoading, setConfigLoading] = useState(false);
  const [judgments, setJudgments] = useState(() => defaultJudgments(LEVEL_DEFS.criteria.n));
  const [errorMessage, setErrorMessage] = useState('');
  const [successMessage, setSuccessMessage] = useState('');
  const [saving, setSaving] = useState(false);

  const headers = useMemo(() => ({
    'Content-Type': 'application/json',
    'x-admin-token': token || '',
  }), [token]);

  const levelDef = LEVEL_DEFS[level];

  const resetMessages = () => {
    setErrorMessage('');
    setSuccessMessage('');
  };

  const loadOverview = async () => {
    if (!token) return;
    setOverviewLoading(true);
    try {
      const response = await fetch(apiUrl('/admin/ahp/matrices'), { headers });
      const data = await response.json();
      if (!response.ok) throw new Error(data.detail || 'Failed to load AHP overview');
      setOverview(Array.isArray(data.configs) ? data.configs : []);
    } catch (error) {
      setErrorMessage(error.message || 'Failed to load AHP overview');
    } finally {
      setOverviewLoading(false);
    }
  };

  const loadCurrentConfig = async () => {
    if (!token) return;
    setConfigLoading(true);
    resetMessages();
    try {
      const query = level === 'saturation' ? `?level=saturation&category=${category}` : '?level=criteria';
      const response = await fetch(apiUrl(`/admin/ahp/matrix${query}`), { headers });

      if (response.status === 404) {
        setConfigMeta(null);
        setJudgments(defaultJudgments(levelDef.n));
        return;
      }

      const data = await response.json();
      if (!response.ok) throw new Error(data.detail || 'Failed to load AHP matrix');

      const config = data.config;
      setConfigMeta(config);

      const next = {};
      for (let i = 0; i < levelDef.n; i += 1) {
        for (let j = i + 1; j < levelDef.n; j += 1) {
          next[judgmentKey(i, j)] = config.pairwise_matrix[i][j];
        }
      }
      setJudgments(next);
    } catch (error) {
      setErrorMessage(error.message || 'Failed to load AHP matrix');
    } finally {
      setConfigLoading(false);
    }
  };

  useEffect(() => { loadOverview(); }, [token]);
  useEffect(() => { loadCurrentConfig(); }, [token, level, category]);

  const previewMatrix = useMemo(() => buildMatrixFromJudgments(judgments, levelDef.n), [judgments, levelDef.n]);
  const previewPriorityVector = useMemo(() => computePriorityVector(previewMatrix), [previewMatrix]);
  const previewConsistency = useMemo(
    () => computeConsistency(previewMatrix, previewPriorityVector),
    [previewMatrix, previewPriorityVector]
  );
  const previewIsConsistent = previewConsistency.cr < CONSISTENCY_RATIO_THRESHOLD;

  const handleJudgmentChange = (i, j, value) => {
    setJudgments((current) => ({ ...current, [judgmentKey(i, j)]: Number(value) }));
  };

  const handleSubmit = async () => {
    resetMessages();
    setSaving(true);
    try {
      const payload = {
        level,
        category: level === 'saturation' ? category : null,
        criteria_labels: levelDef.labels,
        judgments,
      };
      const response = await fetch(apiUrl('/admin/ahp/matrix'), {
        method: 'POST',
        headers,
        body: JSON.stringify(payload),
      });
      const data = await response.json();
      if (!response.ok) throw new Error(data.detail || 'Failed to save AHP matrix');

      setSuccessMessage('AHP matrix saved.');
      setConfigMeta(data.config);
      await loadOverview();
    } catch (error) {
      setErrorMessage(error.message || 'Failed to save AHP matrix');
    } finally {
      setSaving(false);
    }
  };

  const overviewKey = (entry) => `${entry.level}:${entry.category}`;
  const getCategoryLabel = (value) => businessTypeOptions.find((option) => option.value === value)?.label || value;

  return (
    <div>
      {errorMessage && <div className="error-alert mt-4">{errorMessage}</div>}
      {successMessage && <div className="admin-success-alert mt-4">{successMessage}</div>}

      <div className="data-card admin-card">
        <h3 className="section-heading" style={{ marginBottom: 12 }}>AHP Pairwise Comparisons</h3>
        <p className="history-meta" style={{ marginBottom: 16 }}>
          Enter Saaty 1-9 judgments comparing each pair of criteria. Only the upper triangle is editable; the
          reciprocal lower triangle and live priority-vector / consistency preview update automatically.
        </p>

        <div className="admin-tools-grid" style={{ marginBottom: 16 }}>
          <div className="input-group" style={{ marginBottom: 0 }}>
            <label>Hierarchy Level</label>
            <select className="app-select" value={level} onChange={(e) => setLevel(e.target.value)}>
              <option value="criteria">Top-Level Criteria (Zoning / Hazard / Saturation)</option>
              <option value="saturation">Saturation Sub-Criteria (per business category)</option>
            </select>
          </div>

          {level === 'saturation' && (
            <div className="input-group" style={{ marginBottom: 0 }}>
              <label>Business Category</label>
              <select className="app-select" value={category} onChange={(e) => setCategory(e.target.value)}>
                {businessTypeOptions.map((option) => (
                  <option key={option.value} value={option.value}>{option.label}</option>
                ))}
              </select>
            </div>
          )}
        </div>

        {configMeta?.updated_by_admin_email === 'system-seed-migration' && (
          <div className="form-hint" style={{ marginBottom: 12, color: 'var(--trend-neutral)' }}>
            This matrix was auto-generated from the legacy static weights to preserve existing scores. Review and
            replace with real Saaty judgments when ready.
          </div>
        )}

        {configLoading && <p className="history-meta">Loading matrix...</p>}

        {!configLoading && (
          <>
            <div style={{ overflowX: 'auto', marginBottom: 16 }}>
              <table style={{ borderCollapse: 'collapse', width: '100%', minWidth: 480 }}>
                <thead>
                  <tr>
                    <th style={{ padding: 8, textAlign: 'left' }} />
                    {levelDef.displayLabels.map((label) => (
                      <th key={label} style={{ padding: 8, textAlign: 'center', fontSize: '0.85rem' }}>{label}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {levelDef.displayLabels.map((rowLabel, i) => (
                    <tr key={rowLabel}>
                      <th style={{ padding: 8, textAlign: 'left', fontSize: '0.85rem' }}>{rowLabel}</th>
                      {levelDef.displayLabels.map((_, j) => {
                        if (i === j) {
                          return (
                            <td key={j} style={{ padding: 6, textAlign: 'center' }}>
                              <input value="1" disabled style={{ width: 64, textAlign: 'center' }} />
                            </td>
                          );
                        }
                        if (i < j) {
                          return (
                            <td key={j} style={{ padding: 6, textAlign: 'center' }}>
                              <select
                                className="app-select"
                                style={{ width: 150 }}
                                value={judgments[judgmentKey(i, j)] ?? 1}
                                onChange={(e) => handleJudgmentChange(i, j, e.target.value)}
                              >
                                {SAATY_SCALE.map((option) => (
                                  <option key={option.label} value={option.value}>{option.label}</option>
                                ))}
                              </select>
                            </td>
                          );
                        }
                        const reciprocalValue = Number(judgments[judgmentKey(j, i)]) || 1;
                        return (
                          <td key={j} style={{ padding: 6, textAlign: 'center' }}>
                            <input
                              value={(1 / reciprocalValue).toFixed(3)}
                              disabled
                              style={{ width: 64, textAlign: 'center', opacity: 0.7 }}
                            />
                          </td>
                        );
                      })}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            <div className="data-card" style={{ marginBottom: 16 }}>
              <h4 className="section-heading" style={{ marginBottom: 8, fontSize: '1rem' }}>Live Preview</h4>
              <div style={{ display: 'flex', flexWrap: 'wrap', gap: 16, alignItems: 'center', marginBottom: 10 }}>
                <ConsistencyBadge cr={previewConsistency.cr} isConsistent={previewIsConsistent} />
                <span className="history-meta">&lambda;max = {previewConsistency.lambdaMax.toFixed(4)}</span>
                <span className="history-meta">CI = {previewConsistency.ci.toFixed(4)}</span>
                <span className="history-meta">RI = {previewConsistency.ri.toFixed(2)}</span>
              </div>
              {!previewIsConsistent && (
                <p className="history-meta" style={{ color: 'var(--trend-down)', marginBottom: 10 }}>
                  Consistency Ratio is at or above the 0.10 textbook threshold. You can still save, but consider
                  revising judgments that contradict each other.
                </p>
              )}
              <div>
                {levelDef.displayLabels.map((label, idx) => (
                  <div key={label} style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 6 }}>
                    <span className="history-meta" style={{ width: 140 }}>{label}</span>
                    <div style={{ flex: 1, background: 'var(--accent-hover)', borderRadius: 6, overflow: 'hidden', height: 10 }}>
                      <div
                        style={{
                          width: `${Math.round((previewPriorityVector[idx] || 0) * 100)}%`,
                          height: '100%',
                          background: 'var(--accent)',
                        }}
                      />
                    </div>
                    <span className="history-meta" style={{ width: 60, textAlign: 'right' }}>
                      {((previewPriorityVector[idx] || 0) * 100).toFixed(1)}%
                    </span>
                  </div>
                ))}
              </div>
            </div>

            <button type="button" className="primary-btn" onClick={handleSubmit} disabled={saving}>
              {saving ? 'Saving...' : 'Save AHP Matrix'}
            </button>
          </>
        )}
      </div>

      <div className="data-card admin-card mt-6">
        <h3 className="section-heading" style={{ marginBottom: 12 }}>Configuration Overview</h3>
        {overviewLoading && <p className="history-meta">Loading overview...</p>}
        {!overviewLoading && (
          <div style={{ overflowX: 'auto' }}>
            <table style={{ borderCollapse: 'collapse', width: '100%' }}>
              <thead>
                <tr>
                  <th style={{ padding: 8, textAlign: 'left', fontSize: '0.85rem' }}>Level</th>
                  <th style={{ padding: 8, textAlign: 'left', fontSize: '0.85rem' }}>Category</th>
                  <th style={{ padding: 8, textAlign: 'left', fontSize: '0.85rem' }}>Status</th>
                  <th style={{ padding: 8, textAlign: 'left', fontSize: '0.85rem' }}>Consistency Ratio</th>
                </tr>
              </thead>
              <tbody>
                {overview.map((entry) => (
                  <tr key={overviewKey(entry)}>
                    <td style={{ padding: 8 }}>{entry.level === 'criteria' ? 'Top-Level Criteria' : 'Saturation'}</td>
                    <td style={{ padding: 8 }}>
                      {entry.level === 'criteria' ? 'Global' : getCategoryLabel(entry.category)}
                    </td>
                    <td style={{ padding: 8 }}>
                      {entry.is_configured ? (
                        <ConsistencyBadge cr={entry.consistency_ratio} isConsistent={entry.is_consistent} />
                      ) : (
                        <span className="history-meta">Not configured (using static fallback)</span>
                      )}
                    </td>
                    <td style={{ padding: 8 }}>
                      {entry.is_configured ? Number(entry.consistency_ratio).toFixed(3) : '—'}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}
