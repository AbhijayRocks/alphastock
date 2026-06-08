import React, { createContext, useContext, useEffect, useMemo, useState, useCallback, useRef } from 'react';
import { config as apiConfig, setConfig as setApiConfig, subscribeStatus, probeBackend } from '../api/client.js';
import { DEFAULT_HORIZON, isValidHorizon } from '../data/universe.js';
import { useAuth } from './AuthContext.jsx';

const Ctx = createContext(null);

const defaultPrefs = {
  horizon: DEFAULT_HORIZON,
  model:   'ensemble_clf',
  savedScreens: [],
};

const defaultWatchlist = ['RELIANCE.NS', 'TCS.NS', 'HDFCBANK.NS', 'INFY.NS', 'BHARTIARTL.NS'];

const sanitizePrefs = (p = {}) => ({
  horizon: isValidHorizon(p.horizon) ? p.horizon : DEFAULT_HORIZON,
  model:   typeof p.model === 'string' ? p.model : 'ensemble_clf',
  // Saved screener filter sets — kept as-is (array of {id,name,filters}).
  savedScreens: Array.isArray(p.savedScreens) ? p.savedScreens : [],
});

export const AppProvider = ({ children }) => {
  // Per-user personalization is the source of truth — seeded from the signed-in
  // account, then persisted back to it (backend or offline store) on change.
  const { user, persistUserData } = useAuth();

  const [prefs, setPrefs] = useState(() => sanitizePrefs(user?.preferences || defaultPrefs));
  const [watchlist, setWatchlistState] = useState(() =>
    Array.isArray(user?.watchlist) && user.watchlist.length ? user.watchlist : defaultWatchlist
  );
  const [backend, setBackend] = useState({ backendOk: null, lastChecked: 0 });
  const [paletteOpen, setPaletteOpen] = useState(false);
  const [sidebarOpen, setSidebarOpen] = useState(false); // mobile drawer

  useEffect(() => {
    const off = subscribeStatus(setBackend);
    probeBackend();
    return off;
  }, []);

  // Persist preferences to the user's account whenever they change. Each effect
  // skips its own first invocation so the initial hydration isn't echoed back.
  const prefsFirstRun = useRef(true);
  useEffect(() => {
    if (prefsFirstRun.current) { prefsFirstRun.current = false; return; }
    persistUserData?.({ preferences: prefs });
  }, [prefs, persistUserData]);

  const watchFirstRun = useRef(true);
  useEffect(() => {
    if (watchFirstRun.current) { watchFirstRun.current = false; return; }
    persistUserData?.({ watchlist });
  }, [watchlist, persistUserData]);

  const updatePrefs = useCallback((patch) => setPrefs((p) => sanitizePrefs({ ...p, ...patch })), []);

  const setWatchlist = useCallback((next) => setWatchlistState(next), []);
  const toggleWatchlist = useCallback((ticker) => {
    setWatchlistState((wl) => wl.includes(ticker) ? wl.filter((t) => t !== ticker) : [...wl, ticker]);
  }, []);
  const isWatched = useCallback((ticker) => watchlist.includes(ticker), [watchlist]);

  const setApiBase = useCallback((url) => setApiConfig({ baseURL: url }), []);
  const setMockMode = useCallback((mode) => setApiConfig({ mockMode: mode }), []);

  const value = useMemo(() => ({
    prefs, updatePrefs,
    watchlist, setWatchlist, toggleWatchlist, isWatched,
    backend,
    paletteOpen, setPaletteOpen,
    sidebarOpen, setSidebarOpen,
    api: { baseURL: apiConfig.baseURL, mockMode: apiConfig.mockMode },
    setApiBase, setMockMode,
  }), [prefs, watchlist, backend, paletteOpen, sidebarOpen, updatePrefs, setWatchlist, toggleWatchlist, isWatched, setApiBase, setMockMode]);

  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
};

export const useApp = () => {
  const v = useContext(Ctx);
  if (!v) throw new Error('useApp must be used inside <AppProvider>');
  return v;
};
