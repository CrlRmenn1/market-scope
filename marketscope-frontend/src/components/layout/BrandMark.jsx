import React from 'react';

// The MarketScope lens logo (styled in styles/app/04-header-branding.css).
// Shared by the user Header and the admin console sidebar.
export default function BrandMark() {
  return (
    <div className="brand-mark" aria-hidden="true">
      <div className="lens-left" />
      <div className="lens-center">
        <div className="lens-reflection" />
      </div>
      <div className="lens-right" />
    </div>
  );
}
