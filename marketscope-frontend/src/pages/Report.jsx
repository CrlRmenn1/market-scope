import React, { useEffect, useRef, useState } from 'react';
import L from 'leaflet';
import 'leaflet/dist/leaflet.css';

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

export default function Report({ data, targetCoords, onClose }) {
  const mapRef = useRef(null);
  const reportExportRef = useRef(null);
  const mapInstance = useRef(null);
  const mapFeaturesRef = useRef(null);
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

  const fitMapToFeatures = () => {
    if (!mapInstance.current) return;

    const group = mapFeaturesRef.current;
    if (group && group.getLayers().length > 0) {
      const bounds = group.getBounds();
      if (bounds && bounds.isValid()) {
        mapInstance.current.fitBounds(bounds, {
          padding: [32, 32],
          maxZoom: 16,
          animate: false
        });
        return;
      }
    }

    if (resolvedTargetCoords) {
      mapInstance.current.setView([resolvedTargetCoords.lat, resolvedTargetCoords.lng], 15, { animate: false });
    }
  };

  useEffect(() => {
    if (data && resolvedTargetCoords && mapRef.current && !mapInstance.current) {
      
      mapInstance.current = L.map(mapRef.current, {
        center: [resolvedTargetCoords.lat, resolvedTargetCoords.lng],
        zoom: 15, 
        zoomControl: false,
        dragging: true,
        touchZoom: true,
        scrollWheelZoom: true,
        doubleClickZoom: true,
        boxZoom: true,
        keyboard: false,
        maxBoundsViscosity: 1.0
      });

      L.tileLayer('https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png', {
        keepBuffer: 8,
        updateWhenIdle: true,
        crossOrigin: true,
        // Use a dark 1x1 pixel fallback tile if a provider tile fails to load.
        errorTileUrl: 'data:image/gif;base64,R0lGODlhAQABAIAAAAAAACwAAAAAAQABAAACAUwAOw=='
      }).addTo(mapInstance.current);

      const elementsGroup = L.featureGroup().addTo(mapInstance.current);
      mapFeaturesRef.current = elementsGroup;

      // Draw Dynamic Radius
      L.circle([resolvedTargetCoords.lat, resolvedTargetCoords.lng], {
        color: '#a855f7', fillColor: '#a855f7', fillOpacity: 0.15, radius: data.radius_meters || 340
      }).addTo(elementsGroup);

      // Draw Target Pin
      const targetIcon = L.divIcon({
        className: 'custom-pin-wrapper',
        html: `
          <svg width="34" height="34" viewBox="0 0 34 34" fill="none" aria-hidden="true">
            <circle cx="17" cy="17" r="15" fill="rgba(168,85,247,0.18)" stroke="rgba(168,85,247,0.65)" stroke-width="2" />
            <circle cx="17" cy="17" r="6" fill="var(--accent)" stroke="white" stroke-width="2" />
            <circle cx="17" cy="17" r="1.5" fill="white" />
          </svg>
        `,
        iconSize: [34, 34],
        iconAnchor: [17, 17]
      });
      L.marker([resolvedTargetCoords.lat, resolvedTargetCoords.lng], { icon: targetIcon }).addTo(elementsGroup);

      // Draw Competitor Pins
      if (data.competitor_locations && data.competitor_locations.length > 0) {
        const compIcon = L.divIcon({
          className: 'competitor-pin',
          html: `<div style="width:14px; height:14px; background:#ef4444; border:2px solid white; border-radius:50%; box-shadow:0 2px 4px rgba(0,0,0,0.3);"></div>`,
          iconSize: [14, 14], iconAnchor: [7, 7]
        });

        data.competitor_locations.forEach((comp, index) => {
          const compCoords = normalizeCoords(comp);
          if (!compCoords) return;

          const competitorName =
            (typeof comp?.name === 'string' && comp.name.trim())
              ? comp.name.trim()
              : `Competitor ${index + 1}`;

          const marker = L.marker([compCoords.lat, compCoords.lng], { icon: compIcon }).addTo(elementsGroup);
          marker.bindTooltip(competitorName, {
            direction: 'top',
            offset: [0, -8],
            opacity: 0.92,
            className: 'competitor-name-tooltip',
            permanent: true,
            interactive: false
          });
        });
      }

      // Draw Hazard Zone Rectangles
      // Actual hazard zones from Davao del Norte NOAH shapefile (5-year return period)
      const HAZARD_ZONES = [
        { name: 'Very High Flood Hazard (5-Year)', bounds: [7.269, 125.636, 7.333, 125.742], score: 5 },
        { name: 'High Flood Hazard (5-Year)', bounds: [7.269, 125.636, 7.333, 125.73958735603416], score: 12 },
        { name: 'Moderate Flood Hazard (5-Year)', bounds: [7.269, 125.636, 7.333, 125.7389400572897], score: 18 }
      ];

      HAZARD_ZONES.forEach((zone) => {
        const [south, west, north, east] = zone.bounds;
        const rectangle = L.rectangle(
          [[south, west], [north, east]],
          {
            color: zone.score <= 5 ? '#dc2626' : zone.score <= 12 ? '#f97316' : '#f59e0b',
            weight: zone.score <= 5 ? 2.5 : 1.5,
            fillColor: zone.score <= 5 ? '#ef4444' : zone.score <= 12 ? '#fb7185' : '#fbbf24',
            fillOpacity: zone.score <= 5 ? 0.26 : zone.score <= 12 ? 0.18 : 0.12,
            opacity: zone.score <= 5 ? 0.95 : 0.82,
            dashArray: zone.score <= 5 ? null : '6 6'
          }
        );
        rectangle.bindTooltip(zone.name, {
          direction: 'center',
          permanent: false,
          className: 'hazard-zone-tooltip'
        });
        rectangle.addTo(elementsGroup);
      });

      // Keep map camera responsive to container changes and centered around features.
      mapInstance.current.whenReady(() => {
        mapInstance.current.invalidateSize(false);
        fitMapToFeatures();

        // Constrain panning near analyzed features to avoid dragging into blank tile regions.
        const bounds = elementsGroup.getBounds();
        if (bounds && bounds.isValid()) {
          mapInstance.current.setMaxBounds(bounds.pad(0.45));
        }
      });
    }

    return () => {
      mapFeaturesRef.current = null;
      if (mapInstance.current) {
        mapInstance.current.remove();
        mapInstance.current = null;
      }
    };
  }, [data, resolvedTargetCoords]);

  useEffect(() => {
    if (!mapInstance.current || !resolvedTargetCoords) return;

    const onResize = () => {
      if (!mapInstance.current) return;
      mapInstance.current.invalidateSize(false);
      fitMapToFeatures();
    };

    let resizeObserver = null;
    if (mapRef.current && window.ResizeObserver) {
      resizeObserver = new window.ResizeObserver(() => {
        onResize();
      });
      resizeObserver.observe(mapRef.current);
    }

    window.addEventListener('resize', onResize);

    return () => {
      window.removeEventListener('resize', onResize);
      if (resizeObserver) {
        resizeObserver.disconnect();
      }
    };
  }, [resolvedTargetCoords]);

  if (!data) return null;

  const { viability_score, competitors_found, breakdown, business_type, radius_meters, insight } = data;

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
        'Hazard is scored by comparing the location to official Davao del Norte 5-year flood return period zones from the NOAH hazard assessment layer. ' +
        'The lowest matched zone score becomes the factor result: Very High (score 5), High (score 12), or Moderate (score 18).'
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
              const clonedPage = doc.querySelector('.report-page');
              if (clonedPage) {
                clonedPage.classList.add('pdf-force-expand');
              }

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
                .report-map-container,
                .data-card,
                .disclaimer-card {
                  break-inside: avoid;
                  page-break-inside: avoid;
                }
                .report-map-legend {
                  background: #ffffff !important;
                  border-top: 1px solid #e5e7eb !important;
                  color: #374151 !important;
                }
                .legend-dot.target { border-color: #ffffff !important; }
                .legend-dot.competitor { border-color: #ffffff !important; }
                .progress-fill { transition: none !important; }
                /* PDF-only: hide map and expand all metric details */
                .pdf-force-expand .report-map-container {
                  display: none !important;
                }
                .pdf-force-expand .factor-details,
                .pdf-force-expand .factor-details.hidden {
                  display: block !important;
                }
                .pdf-force-expand .detail-chevron {
                  transform: rotate(180deg) !important;
                }
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
            avoid: ['.main-score-card', '.insight-box', '.report-map-container', '.data-card', '.disclaimer-card']
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

        {/* SPATIAL CONTEXT MAP */}
        <h3 className="section-heading mt-6 text-sm font-semibold uppercase tracking-[0.08em] text-[var(--text-main)]">Spatial Context ({radius_meters}m)</h3>
        <div className="report-map-container mt-3 overflow-hidden rounded-2xl border border-[var(--border-color)] bg-[var(--bg-sheet)] shadow-sm">
          <div ref={mapRef} style={{ width: '100%', height: '220px' }}></div>
          
          <div className="report-map-legend flex flex-wrap items-center gap-4 border-t border-[var(--border-color)] bg-[var(--bg-app)] px-4 py-3 text-sm font-medium text-[var(--text-muted)]">
            <span className="inline-flex items-center gap-2"><span className="legend-dot target"></span> Proposed Site</span>
            <span className="inline-flex items-center gap-2"><span className="legend-dot competitor"></span> Competitors ({competitors_found || 0})</span>
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
                aria-expanded={expandedDetail === key}
              >
                <span className="factor-name capitalize text-sm font-semibold text-[var(--text-main)]">{key === 'demand' ? 'Infrastructure Proxies' : key}</span>
                <div className="factor-metrics flex items-center gap-3">
                  <span className="metric-score rounded border border-[var(--border-color)] bg-[var(--bg-app)] px-2 py-1 text-xs font-semibold" style={{ color: getScoreColor(factor.score) }}>
                    {factor.score}/25
                  </span>
                  <span className="metric-status text-xs font-medium" style={{ color: getScoreColor(factor.score) }}>
                    {factor.status}
                  </span>
                  <span className={`detail-chevron ${expandedDetail === key ? 'open' : ''}`}>
                    ▾
                  </span>
                </div>
              </button>
              <div className="progress-track mt-2 h-2 overflow-hidden rounded-full border border-[var(--border-color)] bg-[var(--bg-app)]">
                <div className="progress-fill" style={{ width: `${(factor.score / 25) * 100}%`, backgroundColor: getScoreColor(factor.score) }}></div>
              </div>
              <p className="factor-desc mt-2 text-sm text-[var(--text-muted)]">{factor.description}</p>
              <div className={`factor-details mt-3 rounded-xl border border-[var(--border-color)] bg-[var(--bg-app)] p-4 text-sm leading-6 text-[var(--text-main)] ${expandedDetail === key ? '' : 'hidden'}`}>
                {getFactorDetailText(key, factor).split('. ').map((line, index) => (
                  <p key={index}>{line.trim()}{line.trim().endsWith('.') ? '' : '.'}</p>
                ))}
              </div>
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