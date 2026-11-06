import React from 'react';

// A detail in the privacy policy that the people running MarketScope still need
// to supply. Highlighted so it can't be mistaken for finished text.
export default function PolicyBlank({ children }) {
  return <mark className="auth-policy-blank">[{children}]</mark>;
}
