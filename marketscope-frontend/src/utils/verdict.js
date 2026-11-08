import { getScoreTone } from './scoreTone';

// The backend decides the verdict (services/verdict.py), so every page uses the same
// words. A scan saved before engine 2.0 has none, and its score isn't comparable.
export const isOlderEngineResult = (result) => !result?.engine_version;

export const getVerdict = (result) => {
  if (result?.verdict?.label) return result.verdict;
  return {
    key: 'older',
    label: 'Older scan',
    tone: getScoreTone(result?.viability_score),
    reason: 'Scored by an older version of the engine. Re-scan to update it.'
  };
};

// The result fields beyond the score, for pages that rebuild a report from a saved row.
export const pickResultMeta = (result) => ({
  engine_version: result?.engine_version,
  verdict: result?.verdict,
  market_potential_score: result?.market_potential_score,
  score_explanation: result?.score_explanation,
  data_quality: result?.data_quality
});

// Wording for how the AHP weights behind a score were set.
export const describeWeights = (provenance) => {
  const value = String(provenance || '');

  return '';
};

// Factor scores are 0-25. A factor with no data has a null score, which is not a low score.
export const getFactorColor = (score) => {
  if (score === null || score === undefined) return 'var(--text-muted)';
  if (score >= 20) return 'var(--trend-up)';
  if (score >= 10) return 'var(--trend-neutral)';
  return 'var(--trend-down)';
};

const FACTOR_LABELS = {
  zoning: 'Zoning Fit',
  hazard: 'Hazard Exposure',
  competition_density: 'Competition Density',
  road_access: 'Road Access',
  anchor_proximity: 'Nearby Anchors',
  building_density: 'Building Density',
  saturation: 'Market Potential',
  demand: 'Infrastructure Proxies'
};

export const formatFactorLabel = (key) => FACTOR_LABELS[key] || String(key || '').replace(/_/g, ' ');

// A factor's explanation as one string ('' when the scan didn't store one).
export const factorDetailText = (factor) => {
  const details = factor?.details;
  if (typeof details === 'string') return details.trim();
  if (Array.isArray(details)) return details.filter(Boolean).join(' ').trim();
  if (details && typeof details === 'object') return Object.values(details).filter(Boolean).join(' ').trim();
  return '';
};

export const formatFactorScore = (factor) => {
  if (factor?.constraint) {
    if (factor.state === 'permitted') return 'Allowed';
    if (factor.state === 'not_permitted') return 'Not allowed';
    return 'Not verified';
  }
  if (factor?.score === null || factor?.score === undefined) return 'Not checked';
  return `${factor.score}/25`;
};
