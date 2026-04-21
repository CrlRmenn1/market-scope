import React, { useEffect, useState } from 'react';
import { apiUrl } from '../api';

export default function BottomSheet({ onClose, coords, onViewReport, userId, initialBusinessType = '' }) {
  const [step, setStep] = useState(initialBusinessType ? 2 : 1);
  const [businessType, setBusinessType] = useState(initialBusinessType || '');
  const [selectedRadius, setSelectedRadius] = useState(340);
  const [apiData, setApiData] = useState(null);
  const [analysisModeIndex, setAnalysisModeIndex] = useState(0);
  const radiusOptions = [340, 500, 750];
  const analysisModes = [
    'Zoning Validation',
    'Hazard Impact',
    'Market Saturation',
    'Demand Projection'
  ];

  const startAnalysis = async () => {
    setStep(3); 
    try {
      const response = await fetch(apiUrl('/analyze'), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          lat: coords.lat, lon: coords.lng,
          business_type: businessType, 
          radius: selectedRadius,
          user_id: userId 
        }),
      });

      // THE FIX: If the server throws an error (503 or 429), catch it BEFORE parsing the JSON
      if (!response.ok) {
        throw new Error(`Server responded with status ${response.status}`);
      }

      const data = await response.json();
      setApiData(data);
      setStep(4);

    } catch (e) {
      console.error("Backend Error:", e);
      setStep(1); // Kick them back to step 1
      alert("⚠️ The MarketScope Geospatial Engine is temporarily overwhelmed or offline. Please wait a few seconds and try again.");
    }
  };

  useEffect(() => {
    if (initialBusinessType) {
      setBusinessType(initialBusinessType);
      setStep(2);
      return;
    }

    setBusinessType('');
    setStep(1);
  }, [initialBusinessType]);

  useEffect(() => {
    let intervalId;
    if (step === 3) {
      intervalId = window.setInterval(() => {
        setAnalysisModeIndex((prev) => (prev + 1) % analysisModes.length);
      }, 1200);
    }
    return () => {
      if (intervalId) window.clearInterval(intervalId);
    };
  }, [step]);

  return (
    <div className="sheet-overlay" onClick={onClose}>
      <div className="bottom-sheet" onClick={e => e.stopPropagation()}>
        <div className="drag-handle"></div>
        <button className="close-btn" onClick={onClose}>
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><line x1="18" y1="6" x2="6" y2="18"></line><line x1="6" y1="6" x2="18" y2="18"></line></svg>
        </button>

        <div className="sheet-content">
          {/* STEP 1 & 2 REMAIN THE SAME... */}
          {step === 1 && (
            <div className="fade-in">
              <h2 className="sheet-title">MarketScope Analysis</h2>
              <p className="sheet-subtitle">Select a business category to begin evaluation.</p>
              
              <div className="input-group">
                <label className="input-label">Industry Category</label>
                <select className="styled-select" value={businessType} onChange={(e) => setBusinessType(e.target.value)}>
  <option value="" disabled>Choose a category...</option>
  <option value="coffee">Coffee Shops / Cafes</option>
  <option value="print">Print / Copy Centers</option>
  <option value="laundry">Laundry Shops</option>
  <option value="carwash">Car Washes</option>
  <option value="kiosk">Food Kiosks / Stalls</option>
  <option value="water">Water Refilling Stations</option>
  <option value="bakery">Bakeries</option>
  <option value="pharmacy">Small Pharmacies</option>
  <option value="barber">Barbershops / Salons</option>
  <option value="moto">Motorcycle Repair Shops</option>
  <option value="internet">Internet Cafes</option>
  <option value="meat">Meat Shops</option>
  <option value="hardware">Hardware / Construction Supplies</option>
</select>
              </div>

              <div className="input-group">
                <label className="input-label">Scan Radius</label>
                <div className="radius-option-grid">
                  {radiusOptions.map((radius) => (
                    <button
                      key={radius}
                      type="button"
                      className={`radius-option-btn ${selectedRadius === radius ? 'active' : ''}`}
                      onClick={() => setSelectedRadius(radius)}
                    >
                      {radius}m
                    </button>
                  ))}
                </div>
              </div>

              <button className="primary-btn mt-6" disabled={!businessType} onClick={() => setStep(2)}>Next Step</button>
            </div>
          )}

          {step === 2 && (
            <div className="fade-in text-center">
              <h2 className="sheet-title mb-2">Confirm Target</h2>
              <p className="loc-label">📍 {coords.lat.toFixed(5)}, {coords.lng.toFixed(5)}</p>
              <div className="location-card">
                <p>Deploying Engine for: <b className="capitalize">{businessType}</b></p>
                <p style={{ marginTop: '6px' }}>Radius: <b>{selectedRadius}m</b></p>
              </div>
              <button className="primary-btn" onClick={startAnalysis}>Run Suitability Engine</button>
              <button className="secondary-btn" onClick={() => setStep(1)}>Go Back</button>
            </div>
          )}

          {/* NEW STEP 3: STAGGERED TASKBAR LOADING */}
          {step === 3 && (
            <div className="fade-in py-10">
              <div className="engine-loader">
                <div className="spin-ring"></div>
                <svg className="loading-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M21.5 2v6h-6M21.34 15.57a10 10 0 1 1-.59-9.21l5.25 4.28"/></svg>
              </div>
              <div className="analysis-mode-wrapper">
                <div className="analysis-mode-pill">Analysis Mode • {analysisModes[analysisModeIndex]}</div>
              </div>
              <h3 className="loading-headline text-center mb-6">Evaluating Constraints</h3>
              
              <div className="loading-taskbar">
                <div className="task-item delay-1">
                  <span className="task-text">Verifying CLUP Zoning Regulations</span>
                  <div className="task-spinner"></div>
                </div>
                <div className="task-item delay-2">
                  <span className="task-text">Cross-referencing Hazard Risk Overlays</span>
                  <div className="task-spinner"></div>
                </div>
                <div className="task-item delay-3">
                  <span className="task-text">Querying Live Market Saturation</span>
                  <div className="task-spinner"></div>
                </div>
                <div className="task-item delay-4">
                  <span className="task-text">Calculating Demand Infrastructure</span>
                  <div className="task-spinner"></div>
                </div>
              </div>
            </div>
          )}

          {/* STEP 4 */}
          {step === 4 && apiData && (
            <div className="fade-in text-center">
              <div className="score-container">
                <h2 className="big-score">{apiData.viability_score}</h2>
                <p className="score-label">Suitability Score</p>
              </div>
              <div className="data-card">
                <p>Identified <b>{apiData.competitors_found}</b> competitors in catchment area.</p>
              </div>
              <button className="primary-btn mt-6" onClick={() => onViewReport(apiData)}>View Full Report</button>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}