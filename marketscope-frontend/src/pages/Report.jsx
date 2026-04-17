import React, { useEffect, useRef, useState } from 'react';
import L from 'leaflet';
import 'leaflet/dist/leaflet.css';

export default function Report({ data, targetCoords, onClose }) {
  const mapRef = useRef(null);
  const reportExportRef = useRef(null);
  const mapInstance = useRef(null);
  const mapFeaturesRef = useRef(null);
  const [expandedDetail, setExpandedDetail] = useState(null);
  const [isExportingPdf, setIsExportingPdf] = useState(false);

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

    if (targetCoords?.lat && targetCoords?.lng) {
      mapInstance.current.setView([targetCoords.lat, targetCoords.lng], 15, { animate: false });
    }
  };

  useEffect(() => {
    if (data && targetCoords?.lat && targetCoords?.lng && mapRef.current && !mapInstance.current) {
      
      mapInstance.current = L.map(mapRef.current, {
        center: [targetCoords.lat, targetCoords.lng],
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
      L.circle([targetCoords.lat, targetCoords.lng], {
        color: '#a855f7', fillColor: '#a855f7', fillOpacity: 0.15, radius: data.radius_meters || 340
      }).addTo(elementsGroup);

      // Draw Target Pin
      const targetIcon = L.divIcon({
        className: 'custom-pin-wrapper',
        html: `<svg width="32" height="32" viewBox="0 0 24 24" fill="var(--accent)" stroke="white" stroke-width="2"><path d="M21 10c0 7-9 13-9 13s-9-6-9-13a9 9 0 0 1 18 0z"></path><circle cx="12" cy="10" r="3" fill="white"></circle></svg>`,
        iconSize: [32, 32], iconAnchor: [16, 32]
      });
      L.marker([targetCoords.lat, targetCoords.lng], { icon: targetIcon }).addTo(elementsGroup);

      // Draw Competitor Pins
      if (data.competitor_locations && data.competitor_locations.length > 0) {
        const compIcon = L.divIcon({
          className: 'competitor-pin',
          html: `<div style="width:14px; height:14px; background:#ef4444; border:2px solid white; border-radius:50%; box-shadow:0 2px 4px rgba(0,0,0,0.3);"></div>`,
          iconSize: [14, 14], iconAnchor: [7, 7]
        });

        data.competitor_locations.forEach((comp, index) => {
          const competitorName =
            (typeof comp?.name === 'string' && comp.name.trim())
              ? comp.name.trim()
              : `Competitor ${index + 1}`;

          const marker = L.marker([comp.lat, comp.lon], { icon: compIcon }).addTo(elementsGroup);
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
  }, [data, targetCoords]);

  useEffect(() => {
    if (!mapInstance.current || !targetCoords?.lat || !targetCoords?.lng) return;

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
  }, [targetCoords]);

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

      await html2pdf()
        .set({
          margin: [8, 8, 8, 8],
          filename: `MarketScope_${safeName}_Dossier.pdf`,
          image: { type: 'jpeg', quality: 0.96 },
          html2canvas: {
            scale: 2,
            useCORS: true,
            backgroundColor: '#ffffff',
            scrollX: 0,
            scrollY: 0,
            onclone: (doc) => {
              const style = doc.createElement('style');
              style.textContent = `
                .pdf-hide { display: none !important; }
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
                .progress-fill { transition: none !important; }
              `;
              doc.head.appendChild(style);
            }
          },
          jsPDF: {
            unit: 'mm',
            format: 'a4',
            orientation: 'portrait'
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
    }
  };

  return (
    <div ref={reportExportRef} className="report-page slide-up bg-[var(--bg-app)]">
      <div className="report-header sticky top-0 z-[1200] flex items-center justify-between border-b border-[var(--border-color)] bg-[var(--bg-glass)] px-4 py-4 backdrop-blur-md sm:px-5">
        <h2 className="report-title text-lg font-semibold text-[var(--text-main)]">Analysis Dossier</h2>

        <div className="pdf-hide flex items-center gap-2">
          
          <button className="icon-btn inline-flex h-10 w-10 items-center justify-center rounded-full border border-[var(--border-color)] bg-[var(--bg-sheet)] text-[var(--text-muted)] transition hover:border-[var(--accent)] hover:text-[var(--accent)]" onClick={handlePrint} title={isExportingPdf ? 'Generating PDF...' : 'Save as PDF'} disabled={isExportingPdf}>
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
              {expandedDetail === key && (
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