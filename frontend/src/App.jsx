import React, { lazy, Suspense } from 'react';
import { Routes, Route, useLocation, useNavigate } from 'react-router-dom';
import { AnimatePresence, motion } from 'framer-motion';

import { Sidebar } from './components/shell/Sidebar.jsx';
import { Topbar } from './components/shell/Topbar.jsx';
import { TickerTape } from './components/shell/TickerTape.jsx';
import { CommandPalette } from './components/shell/CommandPalette.jsx';
import { Footer } from './components/shell/Footer.jsx';

import { useApp } from './context/AppContext.jsx';
import { useHotkey } from './hooks/useApi.js';
import { Skeleton } from './components/ui/Skeleton.jsx';

const Dashboard = lazy(() => import('./pages/Dashboard.jsx'));
const Screener  = lazy(() => import('./pages/Screener.jsx'));
const Analysis  = lazy(() => import('./pages/Analysis.jsx'));
const Portfolio = lazy(() => import('./pages/Portfolio.jsx'));
const Backtest  = lazy(() => import('./pages/Backtest.jsx'));
const Settings  = lazy(() => import('./pages/Settings.jsx'));
const NotFound  = lazy(() => import('./pages/NotFound.jsx'));

const PageFallback = () => (
  <div className="space-y-4 py-2">
    <Skeleton className="h-20 w-full" />
    <div className="grid grid-cols-1 md:grid-cols-4 gap-3">
      {Array.from({ length: 4 }).map((_, i) => <Skeleton key={i} className="h-24 w-full" />)}
    </div>
    <Skeleton className="h-64 w-full" />
  </div>
);

const RouteShell = ({ children }) => {
  const { pathname } = useLocation();
  return (
    <AnimatePresence mode="wait">
      <motion.div
        key={pathname}
        initial={{ opacity: 0, y: 6 }}
        animate={{ opacity: 1, y: 0 }}
        exit={{ opacity: 0, y: -4 }}
        transition={{ duration: 0.22, ease: [0.22, 0.61, 0.36, 1] }}
      >
        <Suspense fallback={<PageFallback />}>{children}</Suspense>
      </motion.div>
    </AnimatePresence>
  );
};

const App = () => {
  const { setPaletteOpen } = useApp();
  const navigate = useNavigate();

  // Global hotkeys
  useHotkey(['mod+k', '/'], (e) => { e.preventDefault?.(); setPaletteOpen(true); });
  useHotkey('g o', () => navigate('/'));
  useHotkey('g s', () => navigate('/screener'));
  useHotkey('g a', () => navigate('/analysis'));
  useHotkey('g p', () => navigate('/portfolio'));
  useHotkey('g b', () => navigate('/backtest'));
  useHotkey('g ,', () => navigate('/settings'));

  return (
    <div className="min-h-screen flex bg-bg-0 text-ink-1">
      <Sidebar />
      <main className="flex-1 min-w-0 flex flex-col">
        <Topbar />
        <TickerTape />
        <div className="flex-1 min-w-0">
          <div className="max-w-[1440px] mx-auto px-4 sm:px-6 py-5 sm:py-6">
            <RouteShell>
              <Routes>
                <Route path="/"          element={<Dashboard />} />
                <Route path="/screener"  element={<Screener />} />
                <Route path="/analysis"  element={<Analysis />} />
                <Route path="/portfolio" element={<Portfolio />} />
                <Route path="/backtest"  element={<Backtest />} />
                <Route path="/settings"  element={<Settings />} />
                <Route path="*"          element={<NotFound />} />
              </Routes>
            </RouteShell>
          </div>
        </div>
        <Footer />
      </main>
      <CommandPalette />
    </div>
  );
};

export default App;
