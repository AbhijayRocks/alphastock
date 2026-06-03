import React, { createContext, useContext, useEffect, useMemo, useState, useCallback, useRef } from 'react';
import * as auth from '../api/auth.js';

const Ctx = createContext(null);

export const AuthProvider = ({ children }) => {
  const [session, setSession] = useState(null);   // { mode, token, user } | null
  const [booting, setBooting] = useState(true);    // restoring stored session
  const sessionRef = useRef(null);
  sessionRef.current = session;

  // Restore any persisted session on first mount.
  useEffect(() => {
    let alive = true;
    (async () => {
      try {
        const restored = await auth.restore();
        if (alive) setSession(restored);
      } finally {
        if (alive) setBooting(false);
      }
    })();
    return () => { alive = false; };
  }, []);

  const login = useCallback(async (creds) => {
    const next = await auth.login(creds);
    setSession(next);
    return next;
  }, []);

  const register = useCallback(async (creds) => {
    const next = await auth.register(creds);
    setSession(next);
    return next;
  }, []);

  const logout = useCallback(() => {
    auth.logout();
    setSession(null);
  }, []);

  const updateProfile = useCallback(async (patch) => {
    if (!sessionRef.current) return;
    const next = await auth.updateProfile(sessionRef.current, patch);
    setSession(next);
    return next;
  }, []);

  // Persist per-user personalization. Optimistically updates local session state
  // so the UI is snappy; the network write happens in the background.
  const persistUserData = useCallback(async (patch) => {
    const current = sessionRef.current;
    if (!current) return;
    // Optimistic local update
    setSession((s) => s ? { ...s, user: { ...s.user, ...patch } } : s);
    try {
      const next = await auth.saveUserData(current, patch);
      if (next) setSession(next);
    } catch {
      /* best-effort; localStorage cache already reflects the change */
    }
  }, []);

  const value = useMemo(() => ({
    session,
    user: session?.user || null,
    isAuthenticated: !!session,
    booting,
    login, register, logout, updateProfile, persistUserData,
  }), [session, booting, login, register, logout, updateProfile, persistUserData]);

  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
};

export const useAuth = () => {
  const v = useContext(Ctx);
  if (!v) throw new Error('useAuth must be used inside <AuthProvider>');
  return v;
};
