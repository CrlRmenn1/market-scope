import React, { useEffect, useState } from 'react';
import { apiUrl } from '../api';
import { BUSINESS_TYPE_OPTIONS } from '../utils/businessTypes';

export default function BottomSheet({ onClose, coords, onPreviewCompetitors, onViewReport, userId, initialBusinessType = '', initialRadius = 500 }) {
  const [step, setStep] = useState(initialBusinessType ? 2 : 1);
  const [businessType, setBusinessType] = useState(initialBusinessType || '');
  const [selectedRadius, setSelectedRadius] = useState(initialRadius || 500);
  const [isRunningAnalysis, setIsRunningAnalysis] = useState(false);
  const [analysisModeIndex, setAnalysisModeIndex] = useState(0);
  const analysisModes = [
    'Zoning Validation',
    'Hazard Impact',
    'Market Saturation',
    'Demand Projection'
  ];

  const runFullAnalysis = async () => {
    if (!coords || !businessType) return;

    setStep(3);
    setIsRunningAnalysis(true);
    try {
      const response = await fetch(apiUrl('/analyze'), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          lat: coords.lat,
          lon: coords.lng,
          business_type: businessType,
          radius: selectedRadius,
          user_id: userId || null
        })
      });

      const data = await response.json();
      if (!response.ok) {
        throw new Error(data?.detail || 'Unable to run full analysis');
      }

      onViewReport?.(data);
    } catch (error) {
      alert(error?.message || 'Unable to run full analysis right now.');
    } finally {
      setIsRunningAnalysis(false);
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
    if (Number.isFinite(Number(initialRadius))) {
      setSelectedRadius(Number(initialRadius));
    }
  }, [initialRadius]);

  useEffect(() => {
    let intervalId;
    if (isRunningAnalysis) {
      intervalId = window.setInterval(() => {
        setAnalysisModeIndex((prev) => (prev + 1) % analysisModes.length);
      }, 1200);
    } else {
      setAnalysisModeIndex(0);
    }

    return () => {
      if (intervalId) window.clearInterval(intervalId);
    };
  }, [isRunningAnalysis]);

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
                  {BUSINESS_TYPE_OPTIONS.map((option) => (
                    <option key={option.value} value={option.value}>{option.label}</option>
                  ))}
                </select>
              </div>

              <div className="input-group">
                <label className="input-label">Scan Radius</label>
                <input
                  type="range"
                  min="100"
                  max="1500"
                  step="50"
                  value={selectedRadius}
                  onChange={(event) => setSelectedRadius(Number(event.target.value))}
                  className="radius-slider"
                />
                <div className="radius-slider-meta">
                  <span>100m</span>
                  <b>{selectedRadius}m</b>
                  <span>1500m</span>
                </div>
              </div>

              <button className="primary-btn mt-6" disabled={!businessType} onClick={() => setStep(2)}>Next Step</button>
            </div>
          )}

          {step === 2 && !isRunningAnalysis && (
            <div className="fade-in text-center">
              <h2 className="sheet-title mb-2">Confirm Target</h2>
              <p className="loc-label">📍 {coords.lat.toFixed(5)}, {coords.lng.toFixed(5)}</p>
              <div className="location-card">
                <p>Running full analysis for: <b className="capitalize">{businessType}</b></p>
                <p style={{ marginTop: '6px' }}>Radius: <b>{selectedRadius}m</b></p>
              </div>
              <div className="flex flex-col gap-3">
                <button
                  className="primary-btn"
                  disabled={isRunningAnalysis}
                  onClick={runFullAnalysis}
                >
                  {isRunningAnalysis ? 'Running Full Analysis...' : 'Run Full Analysis'}
                </button>
                <button className="secondary-btn" onClick={() => setStep(1)}>Go Back</button>
              </div>
            </div>
          )}

          {isRunningAnalysis && (
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
        </div>
      </div>
    </div>
  );
}