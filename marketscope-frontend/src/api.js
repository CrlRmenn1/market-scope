const ENV_API_BASE_URL = (import.meta.env.VITE_API_BASE_URL || '').trim();
const LOCAL_API_BASE_URL = 'http://localhost:8000';
const RENDER_API_BASE_URL = 'https://market-scope-phcj.onrender.com';

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