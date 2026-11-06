const ENV_API_BASE_URL = (import.meta.env.VITE_API_BASE_URL || '').trim();
const LOCAL_API_BASE_URL = 'http://localhost:8000';
const RENDER_API_BASE_URL = 'https://marketscope-backend-vma8.onrender.com';

const inferApiBaseUrl = () => {
  if (ENV_API_BASE_URL) return ENV_API_BASE_URL;

  if (typeof window === 'undefined') {
    return LOCAL_API_BASE_URL;
  }

  const hostname = window.location.hostname || '';
  const isLocalHost = hostname === 'localhost' || hostname === '127.0.0.1';
  return isLocalHost ? LOCAL_API_BASE_URL : RENDER_API_BASE_URL;
};

export const API_BASE_URL = inferApiBaseUrl().replace(/\/$/, '');

export const apiUrl = (path) => {
  const normalizedPath = path.startsWith('/') ? path : `/${path}`;
  return `${API_BASE_URL}${normalizedPath}`;
};

const SESSION_KEY = 'marketscope_session';
export const SESSION_EXPIRED_EVENT = 'marketscope-session-expired';

const readSessionToken = () => {
  try {
    return JSON.parse(localStorage.getItem(SESSION_KEY))?.token || '';
  } catch {
    return '';
  }
};

const withSessionToken = (headers) => {
  const merged = new Headers(headers);
  const token = readSessionToken();
  if (token) merged.set('Authorization', `Bearer ${token}`);
  return merged;
};

// fetch for routes that need a logged-in user. If the server no longer accepts
// the session, the app returns to the login page (see App.jsx).
export const authFetch = async (path, options = {}) => {
  const response = await fetch(apiUrl(path), { ...options, headers: withSessionToken(options.headers) });
  if (response.status === 401) window.dispatchEvent(new Event(SESSION_EXPIRED_EVENT));
  return response;
};

// Ends the session on the server. Logging out still works locally if this fails.
export const revokeSession = () => fetch(apiUrl('/logout'), { method: 'POST', headers: withSessionToken() }).catch(() => {});