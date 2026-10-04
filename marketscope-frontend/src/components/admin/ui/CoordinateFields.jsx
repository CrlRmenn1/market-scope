import React, { useState } from 'react';
import { MapPinIcon, ViewfinderCircleIcon } from '@heroicons/react/24/outline';
import MapPicker from '../../map/MapPicker';
import { parseCoordinatePairText } from '../../../utils/coordinates';
import { Field } from './AdminUi';
import { buttonClass, inputClass } from './adminStyles';

// Latitude/longitude inputs with three ways to fill them: type, paste a
// "lat, lng" pair into either box, use the device location, or pin on a map.
export default function CoordinateFields({ latitude, longitude, onChange, onError, required = true }) {
  const [showMapPicker, setShowMapPicker] = useState(false);
  const [locating, setLocating] = useState(false);

  const setPair = (lat, lng) => onChange({ latitude: String(lat), longitude: String(lng) });

  const handlePaste = (event) => {
    const parsed = parseCoordinatePairText(event.clipboardData?.getData('text'));
    if (!parsed) return;
    event.preventDefault();
    setPair(parsed.latitude, parsed.longitude);
  };

  const useMyLocation = () => {
    if (!navigator.geolocation) {
      onError?.('This browser cannot share its location. Pin the spot on the map instead.');
      setShowMapPicker(true);
      return;
    }
    setLocating(true);
    navigator.geolocation.getCurrentPosition(
      (position) => {
        setPair(position.coords.latitude, position.coords.longitude);
        setLocating(false);
      },
      () => {
        onError?.('Location access was blocked. Allow it in the browser, or pin the spot on the map.');
        setLocating(false);
        setShowMapPicker(true);
      },
      { enableHighAccuracy: true, timeout: 10000 }
    );
  };

  return (
    <fieldset className="min-w-0">
      <legend className="sr-only">Location</legend>
      <div className="grid gap-3 sm:grid-cols-2">
        <Field label="Latitude" required={required}>
          <input
            className={`${inputClass} tabular-nums`}
            inputMode="decimal"
            value={latitude}
            onChange={(event) => onChange({ latitude: event.target.value, longitude })}
            onPaste={handlePaste}
            placeholder="7.3110"
            required={required}
          />
        </Field>
        <Field label="Longitude" required={required}>
          <input
            className={`${inputClass} tabular-nums`}
            inputMode="decimal"
            value={longitude}
            onChange={(event) => onChange({ latitude, longitude: event.target.value })}
            onPaste={handlePaste}
            placeholder="125.6854"
            required={required}
          />
        </Field>
      </div>
      <p className="mt-1.5 text-xs text-[var(--text-muted)]">Tip: paste "7.3110, 125.6854" into either box to fill both.</p>
      <div className="mt-3 flex flex-wrap gap-2">
        <button type="button" className={buttonClass.secondary} onClick={useMyLocation} disabled={locating}>
          <ViewfinderCircleIcon className="h-4 w-4" aria-hidden="true" />
          {locating ? 'Locating...' : 'Use my location'}
        </button>
        <button type="button" className={buttonClass.secondary} onClick={() => setShowMapPicker(true)}>
          <MapPinIcon className="h-4 w-4" aria-hidden="true" />
          Pin on map
        </button>
      </div>
      {showMapPicker && (
        <MapPicker
          initialLat={Number(latitude) || undefined}
          initialLng={Number(longitude) || undefined}
          onSelect={({ latitude: lat, longitude: lng }) => {
            setPair(lat, lng);
            setShowMapPicker(false);
          }}
          onClose={() => setShowMapPicker(false)}
        />
      )}
    </fieldset>
  );
}
