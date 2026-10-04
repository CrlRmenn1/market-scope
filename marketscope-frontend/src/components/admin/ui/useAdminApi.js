import { useCallback } from 'react';
import { apiUrl } from '../../../lib/api';

const readDetail = (data, fallback) => {
  const detail = data?.detail;
  if (typeof detail === 'string') return detail;
  if (detail?.message) return detail.message;
  return fallback;
};

// One place for the admin token header and the fetch -> JSON -> error handling
// every admin page needs. request() resolves with the parsed JSON body or throws
// an Error carrying the backend's "detail" message.
export default function useAdminApi(token) {
  return useCallback(async (path, { method = 'GET', body } = {}) => {
    const response = await fetch(apiUrl(path), {
      method,
      headers: {
        'Content-Type': 'application/json',
        'x-admin-token': token || ''
      },
      body: body === undefined ? undefined : JSON.stringify(body)
    });

    let data = null;
    try {
      data = await response.json();
    } catch {
      data = null;
    }

    if (!response.ok) {
      throw new Error(readDetail(data, `Request failed (${response.status})`));
    }
    return data;
  }, [token]);
}
