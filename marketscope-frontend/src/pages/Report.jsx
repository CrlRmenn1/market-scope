import React, { useEffect, useRef } from 'react';
import L from 'leaflet';
import 'leaflet/dist/leaflet.css';

export default function Report({ data, targetCoords, onClose }) {
  const mapRef = useRef(null);
  const mapInstance = useRef(null);

  useEffect(() => {
    if (data && targetCoords?.lat && targetCoords?.lng && mapRef.current && !mapInstance.current) {
      
      mapInstance.current = L.map(mapRef.current, {
        center: [targetCoords.lat, targetCoords.lng],
        zoom: 15, 
        zoomControl: false,
        dragging: false,
        scrollWheelZoom: false,
        doubleClickZoom: false
      });

      L.tileLayer('https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png').addTo(mapInstance.current);

      const elementsGroup = L.featureGroup().addTo(mapInstance.current);

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

        data.competitor_locations.forEach(comp => {
          L.marker([comp.lat, comp.lon], { icon: compIcon }).addTo(elementsGroup);
        });
      }
    }

    return () => {
      if (mapInstance.current) {
        mapInstance.current.remove();
        mapInstance.current = null;
      }
    };
  }, [data, targetCoords]);

  if (!data) return null;

  const { viability_score, competitors_found, breakdown, business_type, radius_meters, insight } = data;

  const getScoreColor = (score) => {
    if (score >= 20) return '#4ade80'; 
    if (score >= 10) return '#facc15'; 
    return '#f87171'; 
  };

  
  // Trigger the browser's native print/PDF dialog with a custom filename
  const handlePrint = () => {
    // 1. Save the original tab title so we can restore it later
    const originalTitle = document.title;

    // 2. Clean up the business name for a file format (e.g., "Coffee Shops" -> "Coffee_Shops")
    const safeName = business_type.replace(/\s+/g, '_');

    // 3. Temporarily change the document title. 
    // The browser automatically uses this exact string as the default PDF file name!
    document.title = `MarketScope_${safeName}_Dossier`;

    // 4. Trigger the Print/Save As dialog
    window.print();

    // 5. Instantly change the title back so the user's browser tab goes back to normal
    document.title = originalTitle;
  };

  return (
    <div className="report-page slide-up">
      <div className="report-header">
        <h2 className="report-title">Analysis Dossier</h2>
        
        {/* NEW: Action Buttons Container */}
        <div style={{ display: 'flex', gap: '15px' }}>
          
          {/* Print/Download Button */}
          <button className="icon-btn" onClick={handlePrint} title="Save as PDF">
            <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <polyline points="6 9 6 2 18 2 18 9"></polyline>
              <path d="M6 18H4a2 2 0 0 1-2-2v-5a2 2 0 0 1 2-2h16a2 2 0 0 1 2 2v5a2 2 0 0 1-2 2h-2"></path>
              <rect x="6" y="14" width="12" height="8"></rect>
            </svg>
          </button>

          {/* Close Button */}
          <button className="icon-btn" onClick={onClose} title="Close Report">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <line x1="18" y1="6" x2="6" y2="18"></line>
              <line x1="6" y1="6" x2="18" y2="18"></line>
            </svg>
          </button>

        </div>
      </div>

      <div className="report-scroll-content">
        
        <div className="main-score-card fade-in">
          <p className="section-heading text-center mb-2" style={{ color: 'var(--accent)' }}>{business_type}</p>
          <div className="score-ring-large shadow-glow">
            <span className="big-score" style={{ color: 'var(--text-main)' }}>{viability_score}</span>
          </div>
          <p className="score-label">Suitability Score</p>
        </div>

        {/* STRATEGIC INSIGHT BOX */}
        <div className="insight-box">
          <h4 className="insight-title" style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M12 2v4M12 18v4M4.93 4.93l2.83 2.83M16.24 16.24l2.83 2.83M2 12h4M18 12h4M4.93 19.07l2.83-2.83M16.24 7.76l2.83-2.83"></path></svg>
            Strategic Recommendation
          </h4>
          <p className="insight-text">
            {insight ? insight : "Processing strategic recommendation based on geospatial parameters..."}
          </p>
        </div>

        {/* SPATIAL CONTEXT MAP */}
        <h3 className="section-heading">Spatial Context ({radius_meters}m)</h3>
        <div className="report-map-container" style={{ height: '220px' }}>
          <div ref={mapRef} style={{ width: '100%', height: '100%' }}></div>
          
          <div className="report-map-legend">
            <span className="legend-dot target"></span> Proposed Site
            <span className="legend-dot competitor"></span> Competitors ({competitors_found || 0})
          </div>
        </div>

        {/* METRIC BREAKDOWN PROGRESS BARS */}
        <h3 className="section-heading mt-6">Metric Breakdown</h3>
        <div className="data-card">
          {breakdown && Object.entries(breakdown).map(([key, factor]) => (
            <div className="progress-group" key={key}>
              <div className="progress-labels">
                <span className="capitalize">{key === 'demand' ? 'Infrastructure Proxies' : key}</span>
                <span style={{ color: getScoreColor(factor.score) }}>{factor.status}</span>
              </div>
              <div className="progress-track">
                <div className="progress-fill" style={{ width: `${(factor.score / 25) * 100}%`, backgroundColor: getScoreColor(factor.score) }}></div>
              </div>
              <p className="factor-desc">{factor.description}</p>
            </div>
          ))}
        </div>

        {/* DISCLAIMER */}
        <div className="data-card disclaimer-card mt-6 mb-10">
          <p><strong>Disclaimer:</strong> This dossier is generated via automated MCDA geospatial models. Please secure BPLO clearances from Panabo City Hall before investment.</p>
        </div>

      </div>
    </div>
  );
}