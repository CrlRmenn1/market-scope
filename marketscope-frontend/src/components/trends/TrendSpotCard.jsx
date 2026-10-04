import React from 'react';
import { getScoreTone } from '../../utils/scoreTone';

const SOURCE_LABELS = {
  space: 'Available space',
  landmark: 'Near landmark',
  area: 'Zone area'
};

const formatListingMode = (value) => (String(value || '').toLowerCase() === 'buy' ? 'For Sale' : 'For Rent');

const formatPrice = (space) => {
  const min = Number(space?.price_min || 0);
  const max = Number(space?.price_max || 0);
  if (!min && !max) return null;
  if (min && max && min !== max) return `PHP ${min.toLocaleString()} - ${max.toLocaleString()}`;
  return `PHP ${(min || max).toLocaleString()}`;
};

// One scanned spot from the background trend scan. Score, insight and highlights
// come from the same /analyze engine as a manual scan.
export default function TrendSpotCard({ spot, onViewReport, onShowOnMap, isOpening }) {
  const tone = getScoreTone(spot.viability_score);
  const space = spot.space;
  const price = formatPrice(space);
  const sourceLabel = spot.is_listed_space ? SOURCE_LABELS.space : SOURCE_LABELS[spot.source] || 'Scanned spot';

  return (
    <div className="data-card trends-card p-4">
      <div className="trends-card-top">
        <div className="flex min-w-0 items-start gap-3">
          <span
            className={`mt-0.5 inline-flex h-7 w-7 flex-none items-center justify-center rounded-full text-xs font-bold tabular-nums ${spot.rank === 1 ? 'bg-[var(--btn-primary-bg)] text-[var(--btn-primary-text)]' : 'bg-[var(--accent-hover)] text-[var(--accent)]'}`}
            aria-label={`Rank ${spot.rank}`}
          >
            {spot.rank}
          </span>
          <div className="min-w-0">
            <h4 className="text-base font-semibold leading-snug text-[var(--text-main)]">{spot.label || 'Scanned spot'}</h4>
            <p className="mt-0.5 text-xs tabular-nums text-[var(--text-muted)]">
              {sourceLabel} · {Number(spot.lat).toFixed(4)}, {Number(spot.lng).toFixed(4)}
            </p>
          </div>
        </div>
        <div className="trends-score-wrap flex-none">
          <span className="trends-score text-2xl tabular-nums leading-none" aria-label={`Viability score ${spot.viability_score} out of 100`}>
            {spot.viability_score}
          </span>
          <span className={`trends-score-badge ${tone}`}>{spot.is_high_chance ? 'High chance' : 'Below cut-off'}</span>
        </div>
      </div>

      {space && (
        <div className="mt-3 rounded-xl bg-[var(--accent-hover)] px-3 py-2.5 text-sm leading-5 text-[var(--text-main)]">
          <span className="font-semibold text-[var(--accent)]">{formatListingMode(space.listing_mode)}: </span>
          {space.title || 'Listed property'}
          {price && ` · ${price}`}
          {space.distance_meters > 0 && ` · ${space.distance_meters} m away`}
        </div>
      )}

      {spot.insight && <p className="mt-3 text-sm leading-5 text-[var(--text-muted)]">{spot.insight}</p>}

      {Array.isArray(spot.highlights) && spot.highlights.length > 0 && (
        <ul className="signal-list mt-3">
          {spot.highlights.map((highlight) => (
            <li key={highlight} className="text-xs leading-4 text-[var(--text-main)]">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" className="text-[var(--accent)]" aria-hidden="true">
                <path d="M20 6 9 17l-5-5" />
              </svg>
              {highlight}
            </li>
          ))}
        </ul>
      )}

      <div className="mt-4 flex flex-wrap items-center gap-2 border-t border-[var(--border-color)] pt-3">
        <button
          type="button"
          className="inline-flex min-h-[44px] items-center justify-center gap-2 rounded-xl bg-[var(--btn-primary-bg)] px-4 py-2.5 text-sm font-semibold text-[var(--btn-primary-text)] transition hover:bg-[var(--btn-primary-hover)] disabled:cursor-not-allowed disabled:opacity-50"
          onClick={() => onViewReport(spot)}
          disabled={isOpening}
        >
          {isOpening ? 'Opening...' : 'View full report'}
        </button>
        <button
          type="button"
          className="inline-flex min-h-[44px] items-center justify-center gap-2 rounded-xl px-3 py-2.5 text-sm font-medium text-[var(--text-muted)] transition hover:bg-[var(--accent-hover)] hover:text-[var(--text-main)]"
          onClick={() => onShowOnMap(spot)}
        >
          Show on map
        </button>
      </div>
    </div>
  );
}
