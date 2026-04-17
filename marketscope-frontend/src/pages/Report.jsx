import React, { useRef, useState } from 'react';

const toFiniteNumber = (value) => {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : null;
};

const normalizeCoords = (coords) => {
  if (!coords || typeof coords !== 'object') return null;
  const lat = toFiniteNumber(coords.lat ?? coords.latitude);
  const lng = toFiniteNumber(coords.lng ?? coords.lon ?? coords.longitude);
  if (lat === null || lng === null) return null;
  return { lat, lng };
};

const toRadians = (value) => (value * Math.PI) / 180;

const distanceMeters = (a, b) => {
  if (!a || !b) return null;
  const earthRadius = 6371000;
  const dLat = toRadians(b.lat - a.lat);
  const dLng = toRadians(b.lng - a.lng);
  const lat1 = toRadians(a.lat);
  const lat2 = toRadians(b.lat);

  const haversine =
    Math.sin(dLat / 2) ** 2 +
    Math.cos(lat1) * Math.cos(lat2) * Math.sin(dLng / 2) ** 2;

  return 2 * earthRadius * Math.atan2(Math.sqrt(haversine), Math.sqrt(1 - haversine));
};

const formatMeters = (value) => {
  if (!Number.isFinite(value)) return 'n/a';
  if (value >= 1000) return `${(value / 1000).toFixed(2)} km`;
  return `${Math.round(value)} m`;
};

const formatCoord = (value) => {
  if (!Number.isFinite(value)) return 'n/a';
  return value.toFixed(5);
};

export default function Report({ data, targetCoords, onClose }) {
  const reportExportRef = useRef(null);
  const [expandedDetail, setExpandedDetail] = useState(null);
  const [isExportingPdf, setIsExportingPdf] = useState(false);
  const [isPdfSettingsOpen, setIsPdfSettingsOpen] = useState(false);
  const [pdfOptions, setPdfOptions] = useState({
    format: 'a4',
    orientation: 'portrait',
    marginMm: 8,
    quality: 0.96,
    scale: 2
  });
  const resolvedTargetCoords = normalizeCoords(targetCoords) || normalizeCoords(data?.target_coords);

  if (!data) return null;

  const { viability_score, competitors_found, breakdown, business_type, radius_meters, insight } = data;
  const normalizedCompetitors = Array.isArray(data.competitor_locations)
    ? data.competitor_locations
      .map((entry, index) => {
        const coords = normalizeCoords(entry);
        if (!coords) return null;
        const name = typeof entry?.name === 'string' && entry.name.trim().length > 0
          ? entry.name.trim()
          : `Competitor ${index + 1}`;
        return { ...coords, name };
      })
      .filter(Boolean)
    : [];

  const activeRadiusMeters = Number.isFinite(Number(radius_meters)) ? Number(radius_meters) : 340;
  const nearestCompetitorMeters = resolvedTargetCoords && normalizedCompetitors.length > 0
    ? Math.min(...normalizedCompetitors.map((comp) => distanceMeters(resolvedTargetCoords, comp)).filter(Number.isFinite))
    : null;
  const innerRingCount = resolvedTargetCoords
    ? normalizedCompetitors.filter((comp) => {
      const d = distanceMeters(resolvedTargetCoords, comp);
      return Number.isFinite(d) && d <= activeRadiusMeters * 0.33;
    }).length
    : 0;
  const middleRingCount = resolvedTargetCoords
    ? normalizedCompetitors.filter((comp) => {
      const d = distanceMeters(resolvedTargetCoords, comp);
      return Number.isFinite(d) && d > activeRadiusMeters * 0.33 && d <= activeRadiusMeters * 0.66;
    }).length
    : 0;
  const outerRingCount = resolvedTargetCoords
    ? normalizedCompetitors.filter((comp) => {
      const d = distanceMeters(resolvedTargetCoords, comp);
      return Number.isFinite(d) && d > activeRadiusMeters * 0.66 && d <= activeRadiusMeters;
    }).length
    : 0;

  const computedCompetitorCount = normalizedCompetitors.length > 0
    ? normalizedCompetitors.length
    : (Number.isFinite(Number(competitors_found)) ? Number(competitors_found) : 0);

  const competitorPressureLabel =
    computedCompetitorCount >= 10 ? 'Very High' :
      computedCompetitorCount >= 6 ? 'High' :
        computedCompetitorCount >= 3 ? 'Moderate' :
          computedCompetitorCount >= 1 ? 'Low' : 'Minimal';

  const toggleDetail = (key) => {
    setExpandedDetail((prev) => (prev === key ? null : key));
  };

  const getScoreColor = (score) => {
    if (score >= 20) return '#4ade80'; 
    if (score >= 10) return '#facc15'; 
    return '#f87171'; 
  };

  const getFactorDetailText = (key, factor) => {
    const details = factor.details;
    if (typeof details === 'string' && details.trim().length > 0) {
      return details;
    }
    if (Array.isArray(details) && details.length > 0) {
      return details.join(' ');
    }
    if (details && typeof details === 'object') {
      const joined = Object.values(details).filter(Boolean).join(' ');
      if (joined.trim().length > 0) return joined;
    }

    if (key === 'zoning') {
      return (
        'Zoning is calculated by testing the target coordinates against Panabo commercial and industrial polygon boundaries. ' +
        'A full score means the point is inside a compliant zone for the chosen business type; lower scores mean it falls outside permitted land use areas.'
      );
    }

    if (key === 'hazard') {
      return (
        'Hazard is scored by comparing the location to temporary Panabo flood and landslide susceptibility zones. ' +
        'The lowest matched zone score becomes the factor result, so a moderate score indicates a mid-level risk proxy zone.'
      );
    }

    if (key === 'saturation') {
      return (
        'Saturation is derived from counting nearby competitors within the analysis radius. ' +
        'The algorithm maps competitor density to a 0-25 scale: fewer competitors produce a higher score.'
      );
    }

    if (key === 'demand') {
      return (
        'Demand is estimated by summing nearby anchor power within the radius and normalizing it against a business-specific benchmark. ' +
        'The raw anchor power is converted into a 0-25 visibility score.'
      );
    }

    return 'This factor explanation is based on the model scoring rules used by the analysis engine.';
  };

  
  const handlePrint = async () => {
    if (!reportExportRef.current || isExportingPdf) return;

    setIsExportingPdf(true);

    const safeName = (business_type || 'Report').replace(/\s+/g, '_');

    try {
      const html2pdfModule = await import('html2pdf.js');
      const html2pdf = html2pdfModule.default;
      await new Promise((resolve) => window.requestAnimationFrame(() => resolve()));

      await html2pdf()
        .set({
          margin: [pdfOptions.marginMm, pdfOptions.marginMm, pdfOptions.marginMm, pdfOptions.marginMm],
          filename: `MarketScope_${safeName}_Dossier.pdf`,
          image: { type: 'jpeg', quality: pdfOptions.quality },
          html2canvas: {
            scale: pdfOptions.scale,
            useCORS: true,
            backgroundColor: '#ffffff',
            scrollX: 0,
            scrollY: 0,
            onclone: (doc) => {
              const style = doc.createElement('style');
              style.textContent = `
                .pdf-hide { display: none !important; }
                :root,
                html,
                body {
                  --bg-app: #ffffff !important;
                  --bg-sheet: #ffffff !important;
                  --bg-glass: #ffffff !important;
                  --text-main: #111827 !important;
                  --text-muted: #4b5563 !important;
                  --border-color: #e5e7eb !important;
                  background: #ffffff !important;
                  color: #111827 !important;
                }
                .report-page {
                  position: static !important;
                  inset: auto !important;
                  height: auto !important;
                  overflow: visible !important;
                  background: #ffffff !important;
                  color: #111827 !important;
                  display: block !important;
                }
                .report-header {
                  position: static !important;
                  top: auto !important;
                  z-index: auto !important;
                  padding: 0 0 12px !important;
                  margin-bottom: 14px !important;
                  background: transparent !important;
                  border-bottom: 1px solid #e5e7eb !important;
                  backdrop-filter: none !important;
                }
                .report-scroll-content {
                  padding: 0 !important;
                  max-width: none !important;
                  width: 100% !important;
                }
                .main-score-card,
                .insight-box,
                .spatial-context-card,
                .data-card,
                .disclaimer-card {
                  break-inside: avoid;
                  page-break-inside: avoid;
                }
                .progress-fill { transition: none !important; }
              `;
              doc.head.appendChild(style);
            }
          },
          jsPDF: {
            unit: 'mm',
            format: pdfOptions.format,
            orientation: pdfOptions.orientation
          },
          pagebreak: {
            mode: ['css', 'legacy'],
            avoid: ['.main-score-card', '.insight-box', '.spatial-context-card', '.data-card', '.disclaimer-card']
          }
        })
        .from(reportExportRef.current)
        .save();
    } catch (error) {
      console.error('PDF export failed:', error);
      window.alert('Unable to generate PDF right now. Please try again.');
    } finally {
      setIsExportingPdf(false);
      setIsPdfSettingsOpen(false);
    }
  };

  return (
    <div ref={reportExportRef} className="report-page slide-up bg-[var(--bg-app)]">
      <div className="report-header sticky top-0 z-[1200] flex items-center justify-between border-b border-[var(--border-color)] bg-[var(--bg-glass)] px-4 py-4 backdrop-blur-md sm:px-5">
        <h2 className="report-title text-lg font-semibold text-[var(--text-main)]">Analysis Dossier</h2>

        <div className="pdf-hide flex items-center gap-2">
          
          <button
            className="icon-btn inline-flex h-10 w-10 items-center justify-center rounded-full border border-[var(--border-color)] bg-[var(--bg-sheet)] text-[var(--text-muted)] transition hover:border-[var(--accent)] hover:text-[var(--accent)]"
            onClick={() => setIsPdfSettingsOpen(true)}
            title={isExportingPdf ? 'Generating PDF...' : 'Save as PDF'}
            disabled={isExportingPdf}
          >
            <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <polyline points="6 9 6 2 18 2 18 9"></polyline>
              <path d="M6 18H4a2 2 0 0 1-2-2v-5a2 2 0 0 1 2-2h16a2 2 0 0 1 2 2v5a2 2 0 0 1-2 2h-2"></path>
              <rect x="6" y="14" width="12" height="8"></rect>
            </svg>
          </button>

          <button className="icon-btn inline-flex h-10 w-10 items-center justify-center rounded-full border border-[var(--border-color)] bg-[var(--bg-sheet)] text-[var(--text-muted)] transition hover:border-[var(--accent)] hover:text-[var(--accent)]" onClick={onClose} title="Close Report">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <line x1="18" y1="6" x2="6" y2="18"></line>
              <line x1="6" y1="6" x2="18" y2="18"></line>
            </svg>
          </button>

        </div>
      </div>

      {isPdfSettingsOpen && (
        <div className="pdf-hide fixed inset-0 z-[8000] flex items-center justify-center bg-black/70 px-4" role="dialog" aria-modal="true" aria-label="PDF export settings">
          <div className="w-full max-w-md rounded-2xl border border-[var(--border-color)] bg-[var(--bg-sheet)] p-5 shadow-2xl">
            <h3 className="text-base font-semibold text-[var(--text-main)]">Export PDF Settings</h3>
            <p className="mt-1 text-sm text-[var(--text-muted)]">The exported file always uses a white report theme.</p>

            <div className="mt-4 grid grid-cols-2 gap-3">
              <label className="text-xs font-medium text-[var(--text-muted)]">
                Paper
                <select
                  className="mt-1 w-full rounded-lg border border-[var(--border-color)] bg-[var(--bg-app)] px-2 py-2 text-sm text-[var(--text-main)]"
                  value={pdfOptions.format}
                  onChange={(e) => setPdfOptions((prev) => ({ ...prev, format: e.target.value }))}
                >
                  <option value="a4">A4</option>
                  <option value="letter">Letter</option>
                </select>
              </label>

              <label className="text-xs font-medium text-[var(--text-muted)]">
                Orientation
                <select
                  className="mt-1 w-full rounded-lg border border-[var(--border-color)] bg-[var(--bg-app)] px-2 py-2 text-sm text-[var(--text-main)]"
                  value={pdfOptions.orientation}
                  onChange={(e) => setPdfOptions((prev) => ({ ...prev, orientation: e.target.value }))}
                >
                  <option value="portrait">Portrait</option>
                  <option value="landscape">Landscape</option>
                </select>
              </label>

              <label className="text-xs font-medium text-[var(--text-muted)]">
                Margin (mm)
                <select
                  className="mt-1 w-full rounded-lg border border-[var(--border-color)] bg-[var(--bg-app)] px-2 py-2 text-sm text-[var(--text-main)]"
                  value={pdfOptions.marginMm}
                  onChange={(e) => setPdfOptions((prev) => ({ ...prev, marginMm: Number(e.target.value) }))}
                >
                  <option value={6}>6</option>
                  <option value={8}>8</option>
                  <option value={10}>10</option>
                  <option value={12}>12</option>
                </select>
              </label>

              <label className="text-xs font-medium text-[var(--text-muted)]">
                Scale
                <select
                  className="mt-1 w-full rounded-lg border border-[var(--border-color)] bg-[var(--bg-app)] px-2 py-2 text-sm text-[var(--text-main)]"
                  value={pdfOptions.scale}
                  onChange={(e) => setPdfOptions((prev) => ({ ...prev, scale: Number(e.target.value) }))}
                >
                  <option value={1.5}>1.5</option>
                  <option value={2}>2.0</option>
                  <option value={2.5}>2.5</option>
                </select>
              </label>

              <label className="col-span-2 text-xs font-medium text-[var(--text-muted)]">
                Image Quality
                <select
                  className="mt-1 w-full rounded-lg border border-[var(--border-color)] bg-[var(--bg-app)] px-2 py-2 text-sm text-[var(--text-main)]"
                  value={pdfOptions.quality}
                  onChange={(e) => setPdfOptions((prev) => ({ ...prev, quality: Number(e.target.value) }))}
                >
                  <option value={0.9}>Standard (0.90)</option>
                  <option value={0.96}>High (0.96)</option>
                  <option value={0.99}>Max (0.99)</option>
                </select>
              </label>
            </div>

            <div className="mt-5 flex items-center justify-end gap-2">
              <button
                type="button"
                className="rounded-lg border border-[var(--border-color)] px-3 py-2 text-sm font-medium text-[var(--text-muted)]"
                onClick={() => setIsPdfSettingsOpen(false)}
                disabled={isExportingPdf}
              >
                Cancel
              </button>
              <button
                type="button"
                className="rounded-lg bg-[var(--accent)] px-3 py-2 text-sm font-semibold text-white"
                onClick={handlePrint}
                disabled={isExportingPdf}
              >
                {isExportingPdf ? 'Generating...' : 'Generate PDF'}
              </button>
            </div>
          </div>
        </div>
      )}

      <div className="report-scroll-content mx-auto w-full max-w-4xl px-4 pb-28 pt-5 sm:px-6">
        
        <div className="main-score-card fade-in rounded-2xl border border-[var(--border-color)] bg-[var(--bg-sheet)] p-6 shadow-sm">
          <p className="section-heading mb-3 text-center text-sm font-semibold uppercase tracking-[0.08em] text-[var(--accent)]">{business_type}</p>
          <div className="score-ring-large flex h-32 w-32 items-center justify-center rounded-full border-4 border-[var(--border-color)] bg-[var(--bg-app)]">
            <span className="big-score text-4xl font-bold leading-none text-[var(--text-main)]">{viability_score}</span>
          </div>
          <p className="score-label mt-4 text-sm font-medium text-[var(--text-muted)]">Suitability Score</p>
        </div>

        {/* STRATEGIC INSIGHT BOX */}
        <div className="insight-box mt-5 rounded-2xl border border-[var(--border-color)] bg-[var(--bg-sheet)] p-5 shadow-sm">
          <h4 className="insight-title mb-3 flex items-center gap-2 text-sm font-semibold uppercase tracking-[0.08em] text-[var(--accent)]">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M12 2v4M12 18v4M4.93 4.93l2.83 2.83M16.24 16.24l2.83 2.83M2 12h4M18 12h4M4.93 19.07l2.83-2.83M16.24 7.76l2.83-2.83"></path></svg>
            Strategic Recommendation
          </h4>
          <p className="insight-text text-sm leading-6 text-[var(--text-main)]">
            {insight ? insight : "Processing strategic recommendation based on geospatial parameters..."}
          </p>
        </div>

        {/* SPATIAL CONTEXT SUMMARY */}
        <h3 className="section-heading mt-6 text-sm font-semibold uppercase tracking-[0.08em] text-[var(--text-main)]">Spatial Context ({Math.round(activeRadiusMeters)}m)</h3>
        <div className="spatial-context-card mt-3 rounded-2xl border border-[var(--border-color)] bg-[var(--bg-sheet)] p-5 shadow-sm">
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
            <div className="rounded-xl border border-[var(--border-color)] bg-[var(--bg-app)] p-3">
              <p className="text-xs font-semibold uppercase tracking-[0.06em] text-[var(--text-muted)]">Target Coordinates</p>
              <p className="mt-1 text-sm font-medium text-[var(--text-main)]">
                {formatCoord(resolvedTargetCoords?.lat)}, {formatCoord(resolvedTargetCoords?.lng)}
              </p>
            </div>

            <div className="rounded-xl border border-[var(--border-color)] bg-[var(--bg-app)] p-3">
              <p className="text-xs font-semibold uppercase tracking-[0.06em] text-[var(--text-muted)]">Scan Radius</p>
              <p className="mt-1 text-sm font-medium text-[var(--text-main)]">{formatMeters(activeRadiusMeters)}</p>
            </div>

            <div className="rounded-xl border border-[var(--border-color)] bg-[var(--bg-app)] p-3">
              <p className="text-xs font-semibold uppercase tracking-[0.06em] text-[var(--text-muted)]">Competitor Pressure</p>
              <p className="mt-1 text-sm font-medium text-[var(--text-main)]">{competitorPressureLabel} ({computedCompetitorCount})</p>
            </div>

            <div className="rounded-xl border border-[var(--border-color)] bg-[var(--bg-app)] p-3">
              <p className="text-xs font-semibold uppercase tracking-[0.06em] text-[var(--text-muted)]">Nearest Competitor</p>
              <p className="mt-1 text-sm font-medium text-[var(--text-main)]">{formatMeters(nearestCompetitorMeters)}</p>
            </div>
          </div>

          <div className="mt-4 rounded-xl border border-[var(--border-color)] bg-[var(--bg-app)] p-4">
            <p className="text-xs font-semibold uppercase tracking-[0.06em] text-[var(--text-muted)]">Competitor Distribution Within Radius</p>
            <div className="mt-2 grid grid-cols-1 gap-2 sm:grid-cols-3">
              <p className="text-sm text-[var(--text-main)]">Inner Ring (0-33%): <strong>{innerRingCount}</strong></p>
              <p className="text-sm text-[var(--text-main)]">Middle Ring (34-66%): <strong>{middleRingCount}</strong></p>
              <p className="text-sm text-[var(--text-main)]">Outer Ring (67-100%): <strong>{outerRingCount}</strong></p>
            </div>
          </div>

          <div className="mt-4 rounded-xl border border-[var(--border-color)] bg-[var(--bg-app)] p-4">
            <p className="text-sm leading-6 text-[var(--text-main)]">
              This report uses geospatial sampling within the configured radius and translates the observed spatial pattern into saturation and demand-related factors.
              Closer and denser competitor clusters generally increase market pressure, while wider spacing can indicate better positioning headroom.
            </p>
          </div>
        </div>

        {/* METRIC BREAKDOWN PROGRESS BARS */}
        <h3 className="section-heading mt-6 text-sm font-semibold uppercase tracking-[0.08em] text-[var(--text-main)]">Metric Breakdown</h3>
        <div className="data-card mt-3 rounded-2xl border border-[var(--border-color)] bg-[var(--bg-sheet)] p-5 shadow-sm">
          <p className="factor-desc mb-4 text-sm text-[var(--text-muted)]">Tap any factor header to expand an actionable explanation for that score.</p>
          {breakdown && Object.entries(breakdown).map(([key, factor]) => (
            <div className="progress-group mb-5 last:mb-0" key={key}>
              <button
                type="button"
                className="progress-labels detail-toggle flex w-full items-center justify-between gap-3 rounded-lg bg-transparent px-0 py-2 text-left transition hover:bg-[var(--accent-hover)]"
                onClick={() => toggleDetail(key)}
                aria-expanded={expandedDetail === key || isExportingPdf}
              >
                <span className="factor-name capitalize text-sm font-semibold text-[var(--text-main)]">{key === 'demand' ? 'Infrastructure Proxies' : key}</span>
                <div className="factor-metrics flex items-center gap-3">
                  <span className="metric-score rounded border border-[var(--border-color)] bg-[var(--bg-app)] px-2 py-1 text-xs font-semibold" style={{ color: getScoreColor(factor.score) }}>
                    {factor.score}/25
                  </span>
                  <span className="metric-status text-xs font-medium" style={{ color: getScoreColor(factor.score) }}>
                    {factor.status}
                  </span>
                  <span className={`detail-chevron ${expandedDetail === key || isExportingPdf ? 'open' : ''}`}>
                    ▾
                  </span>
                </div>
              </button>
              <div className="progress-track mt-2 h-2 overflow-hidden rounded-full border border-[var(--border-color)] bg-[var(--bg-app)]">
                <div className="progress-fill" style={{ width: `${(factor.score / 25) * 100}%`, backgroundColor: getScoreColor(factor.score) }}></div>
              </div>
              <p className="factor-desc mt-2 text-sm text-[var(--text-muted)]">{factor.description}</p>
              {(expandedDetail === key || isExportingPdf) && (
                <div className="factor-details mt-3 rounded-xl border border-[var(--border-color)] bg-[var(--bg-app)] p-4 text-sm leading-6 text-[var(--text-main)]">
                  {getFactorDetailText(key, factor).split('. ').map((line, index) => (
                    <p key={index}>{line.trim()}{line.trim().endsWith('.') ? '' : '.'}</p>
                  ))}
                </div>
              )}
            </div>
          ))}
        </div>

        {/* DISCLAIMER */}
        <div className="data-card disclaimer-card mt-6 mb-10 rounded-2xl border border-[var(--border-color)] bg-[var(--bg-sheet)] p-5 shadow-sm">
          <p><strong>Disclaimer:</strong> This dossier is generated via automated MCDA geospatial models. Please secure BPLO clearances from Panabo City Hall before investment.</p>
        </div>

      </div>
    </div>
  );
}