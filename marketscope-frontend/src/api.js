const ENV_API_BASE_URL = (import.meta.env.VITE_API_BASE_URL || '').trim();
const API_MODE = (import.meta.env.VITE_API_MODE || 'auto').trim().toLowerCase();
const LOCAL_API_BASE_URL = (import.meta.env.VITE_LOCAL_API_BASE_URL || 'http://localhost:8000').trim();
const ONLINE_API_BASE_URL = (import.meta.env.VITE_ONLINE_API_BASE_URL || 'https://market-scope.onrender.com').trim();

const inferApiBaseUrl = () => {
  if (ENV_API_BASE_URL) return ENV_API_BASE_URL;

  if (API_MODE === 'local') return LOCAL_API_BASE_URL;
  if (API_MODE === 'online') return ONLINE_API_BASE_URL;

  if (typeof window === 'undefined') {
    return LOCAL_API_BASE_URL;
  }

  const hostname = window.location.hostname || '';
  const isLocalHost = hostname === 'localhost' || hostname === '127.0.0.1';
  return isLocalHost ? LOCAL_API_BASE_URL : ONLINE_API_BASE_URL;
};

export const API_BASE_URL = inferApiBaseUrl().replace(/\/$/, '');

export const apiUrl = (path) => {
  const normalizedPath = path.startsWith('/') ? path : `/${path}`;
  return `${API_BASE_URL}${normalizedPath}`;
};