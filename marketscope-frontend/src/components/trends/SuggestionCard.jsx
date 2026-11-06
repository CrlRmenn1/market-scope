import React from 'react';
import { getVerdict } from '../../utils/verdict';

const plural = (count, word) => `${count} ${word}${count === 1 ? '' : 's'}`;

// One business in one area. The score is the average of its best spots there, and
// the buttons open the single best spot.
export default function SuggestionCard({ entry, title, rank, reachMeters, onViewReport, onShowOnMap, isOpening }) {
  const verdict = getVerdict({ verdict: entry.verdict, viability_score: entry.score });
  const factor = entry.strongest_factor;
  const hasThinData = entry.competitor_data === 'thin';

  return (
    <div className="data-card trends-card p-4">
      <div className="trends-card-top">
        <div className="flex min-w-0 items-start gap-3">
          <span
            className={`mt-0.5 inline-flex h-7 w-7 flex-none items-center justify-center rounded-full text-xs font-bold tabular-nums ${rank === 1 ? 'bg-[var(--btn-primary-bg)] text-[var(--btn-primary-text)]' : 'bg-[var(--accent-hover)] text-[var(--accent)]'}`}
            aria-label={`Rank ${rank}`}
          >
            {rank}
          </span>
          <div className="min-w-0">
            <h4 className="text-base font-semibold leading-snug text-[var(--text-main)]">{title}</h4>
            <p className="mt-0.5 text-xs tabular-nums text-[var(--text-muted)]">
              {plural(entry.spots_checked, 'spot')} checked · best spot scores {entry.best_spot.score}
              {entry.listed_spaces > 0 && ` · ${plural(entry.listed_spaces, 'listed space')}`}
            </p>
          </div>
        </div>
        <div className="trends-score-wrap flex-none">
          <span className="text-[0.68rem] font-medium uppercase tracking-[0.06em] text-[var(--text-muted)]" aria-hidden="true">Area score</span>
          <span className="trends-score text-2xl tabular-nums leading-none" aria-label={`Area score ${entry.score} out of 100`}>
            {entry.score}
          </span>
          <span className={`trends-score-badge ${verdict.tone}`}>{verdict.label}</span>
        </div>
      </div>

      {(entry.market_gap || entry.fits_setup) && (
        <div className="mt-3 flex flex-wrap gap-1.5">
          {entry.market_gap && <span className="trends-tag gap">Possible market gap</span>}
          {entry.fits_setup && <span className="trends-tag">Fits your setup</span>}
        </div>
      )}

      {hasThinData && (
        <p className="mt-3 rounded-xl bg-[var(--trend-neutral-bg)] px-3 py-2 text-sm leading-5 text-[var(--text-main)]">
          Few competitors on record ({entry.known_competitors} citywide), so low competition here may just mean missing data. Check in person.
        </p>
      )}

      <ul className="mt-3 space-y-1 text-sm leading-5 text-[var(--text-muted)]">
        {factor && (
          <li>
            Strongest factor: <span className="text-[var(--text-main)]">{factor.label}</span>
            {factor.status && ` (${factor.status})`}
          </li>
        )}
        {entry.competitor_count !== null && entry.competitor_count !== undefined && (
          <li>{plural(entry.competitor_count, 'competitor')} on record within {reachMeters} m of the best spot</li>
        )}
        {entry.verdict?.reason && <li>{entry.verdict.reason}</li>}
      </ul>

      <div className="mt-4 flex flex-wrap items-center gap-2 border-t border-[var(--border-color)] pt-3">
        <button
          type="button"
          className="inline-flex min-h-[44px] items-center justify-center gap-2 rounded-xl bg-[var(--btn-primary-bg)] px-4 py-2.5 text-sm font-semibold text-[var(--btn-primary-text)] transition hover:bg-[var(--btn-primary-hover)] disabled:cursor-not-allowed disabled:opacity-50"
          onClick={() => onViewReport(entry)}
          disabled={isOpening}
        >
          {isOpening ? 'Opening...' : 'View best spot report'}
        </button>
        <button
          type="button"
          className="inline-flex min-h-[44px] items-center justify-center gap-2 rounded-xl px-3 py-2.5 text-sm font-medium text-[var(--text-muted)] transition hover:bg-[var(--accent-hover)] hover:text-[var(--text-main)]"
          onClick={() => onShowOnMap(entry)}
        >
          Show on map
        </button>
      </div>
    </div>
  );
}
