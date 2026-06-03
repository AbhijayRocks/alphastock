// Auth client — talks to the FastAPI backend (/api/auth, /api/user) and falls
// back to a secure local account store when the backend is unreachable. This
// mirrors the app's offline-first philosophy: the login gate and per-user
// personalization keep working for demos even without the ML backend running.
//
// Remote sessions use the backend's JWT. Local sessions use a token prefixed
// with "local." and are validated against an encrypted-at-rest account store
// in localStorage (passwords hashed with Web Crypto PBKDF2-SHA256, never kept
// in plaintext).

import { config } from './client.js';

const SESSION_KEY = 'alphastock.session.v1';
const LOCAL_USERS_KEY = 'alphastock.local_users.v1';
const PBKDF2_ROUNDS = 240_000;

const DEFAULT_WATCHLIST = ['RELIANCE.NS', 'TCS.NS', 'HDFCBANK.NS', 'INFY.NS', 'BHARTIARTL.NS'];
const DEFAULT_PREFERENCES = { horizon: '5d', model: 'ensemble_clf' };

// ── Session persistence ─────────────────────────────────────────────────────────
export const loadSession = () => {
  try { return JSON.parse(localStorage.getItem(SESSION_KEY) || 'null'); } catch { return null; }
};
const saveSession = (session) => {
  try { localStorage.setItem(SESSION_KEY, JSON.stringify(session)); } catch {}
  return session;
};
export const clearSession = () => { try { localStorage.removeItem(SESSION_KEY); } catch {} };

// ── HTTP helpers ─────────────────────────────────────────────────────────────────
const base = () => config.baseURL.replace(/\/$/, '');

const request = async (path, { method = 'GET', body, token } = {}) => {
  const headers = { 'Content-Type': 'application/json' };
  if (token) headers.Authorization = `Bearer ${token}`;
  const res = await fetch(base() + path, {
    method,
    headers,
    body: body ? JSON.stringify(body) : undefined,
    signal: AbortSignal.timeout?.(8000),
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    const err = new Error(data?.detail || `Request failed (${res.status})`);
    err.status = res.status;
    throw err;
  }
  return data;
};

// Distinguish "backend is down" (fall back to local) from "backend rejected us"
// (surface the error — e.g. wrong password, email taken).
const isNetworkError = (err) =>
  err?.status === undefined || err?.name === 'TimeoutError' || err?.name === 'AbortError';

// ── Web Crypto password hashing (local fallback only) ────────────────────────────
const enc = new TextEncoder();
const toHex = (buf) => [...new Uint8Array(buf)].map((b) => b.toString(16).padStart(2, '0')).join('');
const fromHex = (hex) => new Uint8Array(hex.match(/.{1,2}/g).map((h) => parseInt(h, 16)));

const pbkdf2 = async (password, salt) => {
  const key = await crypto.subtle.importKey('raw', enc.encode(password), 'PBKDF2', false, ['deriveBits']);
  const bits = await crypto.subtle.deriveBits(
    { name: 'PBKDF2', salt, iterations: PBKDF2_ROUNDS, hash: 'SHA-256' },
    key, 256,
  );
  return toHex(bits);
};

const hashPassword = async (password) => {
  const salt = crypto.getRandomValues(new Uint8Array(16));
  const hash = await pbkdf2(password, salt);
  return { salt: toHex(salt), hash };
};
const verifyPassword = async (password, saltHex, expectedHash) => {
  const hash = await pbkdf2(password, fromHex(saltHex));
  return hash === expectedHash;
};

// ── Local account store ──────────────────────────────────────────────────────────
const loadLocalUsers = () => {
  try { return JSON.parse(localStorage.getItem(LOCAL_USERS_KEY) || '{}'); } catch { return {}; }
};
const saveLocalUsers = (users) => {
  try { localStorage.setItem(LOCAL_USERS_KEY, JSON.stringify(users)); } catch {}
};
const localPublic = (u) => ({
  id: u.id, email: u.email, display_name: u.display_name,
  watchlist: u.watchlist, preferences: u.preferences, portfolios: u.portfolios,
  created_at: u.created_at, last_login_at: u.last_login_at,
});

const normEmail = (e) => String(e || '').trim().toLowerCase();
const EMAIL_RE = /^[^@\s]+@[^@\s]+\.[^@\s]+$/;

// ── Public API ───────────────────────────────────────────────────────────────────
export const register = async ({ email, password, displayName }) => {
  email = normEmail(email);
  if (!EMAIL_RE.test(email)) throw new Error('Enter a valid email address');
  if ((password || '').length < 8) throw new Error('Password must be at least 8 characters');

  try {
    const data = await request('/auth/register', {
      method: 'POST',
      body: { email, password, display_name: displayName || undefined },
    });
    return saveSession({ mode: 'remote', token: data.token, user: data.user });
  } catch (err) {
    if (!isNetworkError(err)) throw err;
    // Offline: create a local account.
    const users = loadLocalUsers();
    if (users[email]) throw new Error('An account with this email already exists');
    const { salt, hash } = await hashPassword(password);
    const now = new Date().toISOString();
    users[email] = {
      id: Date.now(), email, display_name: (displayName || '').trim() || email.split('@')[0],
      salt, hash,
      watchlist: [...DEFAULT_WATCHLIST], preferences: { ...DEFAULT_PREFERENCES }, portfolios: [],
      created_at: now, last_login_at: now,
    };
    saveLocalUsers(users);
    return saveSession({ mode: 'local', token: `local.${email}`, user: localPublic(users[email]) });
  }
};

export const login = async ({ email, password }) => {
  email = normEmail(email);
  try {
    const data = await request('/auth/login', { method: 'POST', body: { email, password } });
    return saveSession({ mode: 'remote', token: data.token, user: data.user });
  } catch (err) {
    if (!isNetworkError(err)) throw err;
    const users = loadLocalUsers();
    const u = users[email];
    if (!u || !(await verifyPassword(password, u.salt, u.hash))) {
      throw new Error('Incorrect email or password');
    }
    u.last_login_at = new Date().toISOString();
    saveLocalUsers(users);
    return saveSession({ mode: 'local', token: `local.${email}`, user: localPublic(u) });
  }
};

export const logout = () => clearSession();

// Re-validate a stored session on app boot. Returns the (possibly refreshed)
// user, or null if the session is gone/invalid.
export const restore = async () => {
  const session = loadSession();
  if (!session) return null;
  if (session.mode === 'local') {
    const email = session.token.replace(/^local\./, '');
    const u = loadLocalUsers()[email];
    if (!u) { clearSession(); return null; }
    return saveSession({ ...session, user: localPublic(u) });
  }
  // Remote: confirm token still valid with the backend; on network error, trust
  // the cached user so offline reloads don't kick people out.
  try {
    const user = await request('/auth/me', { token: session.token });
    return saveSession({ ...session, user });
  } catch (err) {
    if (isNetworkError(err)) return session;
    clearSession();
    return null;
  }
};

export const updateProfile = async (session, patch) => {
  if (session.mode === 'local') {
    const email = session.token.replace(/^local\./, '');
    const users = loadLocalUsers();
    if (users[email]) {
      if (patch.display_name) users[email].display_name = patch.display_name;
      saveLocalUsers(users);
      return saveSession({ ...session, user: localPublic(users[email]) });
    }
    return session;
  }
  const user = await request('/auth/me', { method: 'PATCH', body: patch, token: session.token });
  return saveSession({ ...session, user });
};

// Persist per-user personalization (watchlist / preferences / portfolios).
export const saveUserData = async (session, patch) => {
  if (!session) return null;
  if (session.mode === 'local') {
    const email = session.token.replace(/^local\./, '');
    const users = loadLocalUsers();
    const u = users[email];
    if (!u) return session;
    if (patch.watchlist !== undefined) u.watchlist = patch.watchlist;
    if (patch.preferences !== undefined) u.preferences = { ...u.preferences, ...patch.preferences };
    if (patch.portfolios !== undefined) u.portfolios = patch.portfolios;
    saveLocalUsers(users);
    return saveSession({ ...session, user: localPublic(u) });
  }
  const user = await request('/user/data', { method: 'PUT', body: patch, token: session.token });
  return saveSession({ ...session, user });
};
