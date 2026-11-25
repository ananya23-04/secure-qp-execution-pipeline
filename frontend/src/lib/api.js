// Thin fetch wrapper. The token lives in sessionStorage so each browser tab can be a different user
// (handy for the multi-custodian exam demo).
const KEY = 'safeexam.token';
export const getToken = () => sessionStorage.getItem(KEY);
export const setToken = (t) => (t ? sessionStorage.setItem(KEY, t) : sessionStorage.removeItem(KEY));

function describe(detail) {
  if (detail == null) return 'Request failed';
  if (typeof detail === 'string') return detail;
  if (Array.isArray(detail)) return detail.map((e) => e.msg || JSON.stringify(e)).join('; ');
  if (typeof detail === 'object') {
    if (detail.issues) return `Problems found: ${detail.issues.join(', ')}`;
    if (detail.errors) return detail.errors.join('; ');
    if (detail.reason) return detail.reason;
    if (detail.error) {
      const extra = detail.shortfall_marks_by_unit ? ` (missing marks by unit: ${JSON.stringify(detail.shortfall_marks_by_unit)})` : '';
      return detail.error + extra;
    }
    return JSON.stringify(detail);
  }
  return String(detail);
}

export class ApiError extends Error {
  constructor(status, detail) {
    super(describe(detail));
    this.status = status;
    this.detail = detail;
  }
}

export async function api(path, { method = 'GET', body, raw = false } = {}) {
  const headers = {};
  const token = getToken();
  if (token) headers.Authorization = `Bearer ${token}`;
  if (body !== undefined) headers['Content-Type'] = 'application/json';
  const res = await fetch(path, { method, headers, body: body !== undefined ? JSON.stringify(body) : undefined });
  if (raw) {
    if (!res.ok) throw new ApiError(res.status, await res.text().catch(() => 'Request failed'));
    return res;
  }
  const text = await res.text();
  let data = null;
  try { data = text ? JSON.parse(text) : null; } catch { data = text; }
  if (!res.ok) throw new ApiError(res.status, data && typeof data === 'object' && 'detail' in data ? data.detail : data);
  return data;
}

export async function sha256Hex(text) {
  if (!globalThis.crypto?.subtle) throw new Error('This browser blocks crypto here - open the portal via http://localhost:8000/app/');
  const buf = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(text));
  return [...new Uint8Array(buf)].map((b) => b.toString(16).padStart(2, '0')).join('');
}

export function randomHex(bytes = 16) {
  const a = new Uint8Array(bytes);
  crypto.getRandomValues(a);
  return [...a].map((b) => b.toString(16).padStart(2, '0')).join('');
}
