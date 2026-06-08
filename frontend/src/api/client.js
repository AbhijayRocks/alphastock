// Typed API client + mock adapter.
// Endpoints mirror backend/api/routes.py exactly. When the backend is
// unreachable, mock data is returned automatically (offline-first dev).

import axios from 'axios';
import {
  mockHealth, mockRegime, mockModels, mockPrices, mockHistory,
  mockPredict, mockExplain, mockBacktest, mockOptimize, mockSimulate, mockSignals,
  mockNews, mockNewsSectors, mockPulse, mockFundamentals, mockScreen,
} from '../data/mock.js';

const STORAGE_KEY = 'alphastock.config.v1';

const loadConfig = () => {
  try { return JSON.parse(localStorage.getItem(STORAGE_KEY) || '{}'); } catch { return {}; }
};
const saveConfig = (cfg) => {
  try { localStorage.setItem(STORAGE_KEY, JSON.stringify(cfg)); } catch {}
};

const defaultConfig = {
  // API base is environment-driven: set VITE_API_BASE in a .env file or the
  // shell. Falls back to localhost:9000 so it works with zero config.
  baseURL: import.meta.env.VITE_API_BASE || 'http://localhost:9000/api',
  mockMode: 'auto',   // 'auto' | 'on' | 'off'
  timeoutMs: 6000,
};

export const config = { ...defaultConfig, ...loadConfig() };

export const setConfig = (next) => {
  Object.assign(config, next);
  saveConfig(config);
  http.defaults.baseURL = config.baseURL;
  http.defaults.timeout = config.timeoutMs;
};

const http = axios.create({ baseURL: config.baseURL, timeout: config.timeoutMs });

// ── Mock router ───────────────────────────────────────────────────────────────
const MOCK_LATENCY = [80, 240];
const wait = () => new Promise((r) => setTimeout(r, MOCK_LATENCY[0] + Math.random() * (MOCK_LATENCY[1] - MOCK_LATENCY[0])));

const mock = {
  '/health':            () => mockHealth(),
  '/regime':            () => mockRegime(),
  '/models':            () => mockModels(),
  '/prices':            () => mockPrices(),
  '/history':           ({ ticker, days }) => mockHistory(ticker, days),
  '/predict':           (body) => mockPredict(body),
  '/explain':           (body) => mockExplain(body),
  '/backtest':          (body) => mockBacktest(body),
  '/optimize_portfolio':(body) => mockOptimize(body),
  '/simulate':          (body) => mockSimulate(body),
  '/signals':           ({ horizon }) => mockSignals(horizon),
  '/pulse':             ({ horizon }) => mockPulse(horizon),
  '/screen':            ({ horizon }) => mockScreen(horizon),
  '/fundamentals':      () => mockFundamentals(),
  '/news':              ({ sector }) => mockNews(sector),
  '/news/sectors':      () => mockNewsSectors(),
};

const useMock = () => config.mockMode === 'on';
const isAuto  = () => config.mockMode === 'auto';

// Status tracker — UI can subscribe to it
const listeners = new Set();
const status = { backendOk: null, lastChecked: 0 };
export const subscribeStatus = (fn) => { listeners.add(fn); fn(status); return () => listeners.delete(fn); };
const emitStatus = () => listeners.forEach((fn) => fn({ ...status }));

const flagBackend = (ok) => {
  status.backendOk = ok;
  status.lastChecked = Date.now();
  emitStatus();
};

// Generic wrappers
const get = async (path, params, mockArgs = {}) => {
  if (useMock()) { await wait(); return mock[path](mockArgs); }
  try {
    const res = await http.get(path, { params });
    flagBackend(true);
    return res.data;
  } catch (err) {
    if (isAuto()) { flagBackend(false); await wait(); return mock[path](mockArgs); }
    flagBackend(false);
    throw err;
  }
};

const post = async (path, body) => {
  if (useMock()) { await wait(); return mock[path](body); }
  try {
    const res = await http.post(path, body);
    flagBackend(true);
    return res.data;
  } catch (err) {
    if (isAuto()) { flagBackend(false); await wait(); return mock[path](body); }
    flagBackend(false);
    throw err;
  }
};

// ── Public API surface — one function per endpoint ───────────────────────────
export const api = {
  health:    () => get('/health'),
  regime:    () => get('/regime'),
  models:    () => get('/models'),
  prices:    () => get('/prices'),
  history:   (ticker, days = 90) => get(`/history/${ticker}`, { days }, { ticker, days })
    .catch(async (err) => { if (isAuto()) { await wait(); return mockHistory(ticker, days); } throw err; }),

  predict:   ({ ticker, horizon = '1d', model = 'ensemble_clf' }) =>
    post('/predict', { ticker, horizon, model }),

  explain:   ({ ticker, horizon = '1d', top_n = 12 }) =>
    post('/explain', { ticker, horizon, top_n }),

  backtest:  ({ ticker, horizon = '1d', transaction_cost = 0.001 }) =>
    post('/backtest', { ticker, horizon, transaction_cost }),

  optimize:  ({ tickers, horizon = '20d', risk_tolerance = 1.0 }) =>
    post('/optimize_portfolio', { tickers, horizon, risk_tolerance }),

  simulate:  ({ ticker, horizon = '20d', n_sims = 2000 }) =>
    post('/simulate', { ticker, horizon, n_sims }),

  signals:   (horizon = '5d') => get('/signals', { horizon }, { horizon }),

  pulse:     (horizon = '5d') => get('/pulse', { horizon }, { horizon }),

  screen:    (horizon = '5d') => get('/screen', { horizon }, { horizon }),

  fundamentals: () => get('/fundamentals', undefined, {}),

  news:        (sector, limit = 24, range = 'all') => get('/news', { sector, limit, range }, { sector }),
  newsSectors: () => get('/news/sectors', undefined, {}),
};

// Background probe at startup so UI can show "live" vs "demo" badge
export const probeBackend = async () => {
  try {
    await axios.get(config.baseURL + '/health', { timeout: 1500 });
    flagBackend(true);
  } catch {
    flagBackend(false);
  }
};
