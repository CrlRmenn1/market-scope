import { apiUrl } from '../../lib/api';

export const MIN_PASSWORD_LENGTH = 6;

// Resolves with the parsed response even on an error status, so each form can
// decide what a failure means. Only a failed connection rejects.
export const postJson = async (path, body) => {
  let response;
  try {
    response = await fetch(apiUrl(path), {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    });
  } catch {
    throw new Error("Can't reach MarketScope. Check your connection and try again.");
  }

  let data = {};
  try {
    data = await response.json();
  } catch {
    data = {};
  }
  return { ok: response.ok, status: response.status, data };
};

// FastAPI's validation errors put a list in `detail`, which isn't fit to display.
export const errorDetail = (data, fallback) => (typeof data?.detail === 'string' ? data.detail : fallback);
