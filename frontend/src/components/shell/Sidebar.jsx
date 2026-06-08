import React, { useEffect } from 'react';
import { NavLink, useNavigate, useLocation } from 'react-router-dom';
import { motion, AnimatePresence } from 'framer-motion';
import { Wordmark } from './Logo.jsx';
import {
  IconHome, IconCompass, IconBeaker, IconBriefcase, IconBrain, IconSettings,
  IconCommand, IconStarFill, IconArrowUp, IconArrowDown, IconX, IconGlobe,
} from './Icons.jsx';
import { useApp } from '../../context/AppContext.jsx';
import { useApi } from '../../hooks/useApi.js';
import { api } from '../../api/client.js';
import { cn, tickerSymbol, toApiTicker, fmtPctRaw, signClass } from '../../lib/utils.js';
import { horizonLabel } from '../../data/universe.js';

const NAV = [
  { to: '/',           label: 'Overview',  icon: IconHome,      hotkey: 'G O' },
  { to: '/screener',   label: 'Screener',  icon: IconCompass,   hotkey: 'G S' },
  { to: '/analysis',   label: 'Analysis',  icon: IconBrain,     hotkey: 'G A' },
  { to: '/portfolio',  label: 'Portfolio', icon: IconBriefcase, hotkey: 'G P' },
  { to: '/backtest',   label: 'Backtest',  icon: IconBeaker,    hotkey: 'G B' },
  { to: '/news',       label: 'News',      icon: IconGlobe,     hotkey: 'G N' },
];

const NavItem = ({ to, label, icon: Icon, hotkey, onNavigate }) => (
  <NavLink
    to={to}
    end={to === '/'}
    onClick={onNavigate}
    className={({ isActive }) => cn(
      'group relative flex items-center gap-2.5 px-3 h-9 rounded-lg text-sm font-medium',
      'transition-all duration-180 ease-out',
      isActive
        ? 'text-ink-1 bg-bg-2 border border-line-muted shadow-soft'
        : 'text-ink-3 hover:text-ink-1 hover:bg-bg-2/50 border border-transparent',
    )}
  >
    {({ isActive }) => (
      <>
        {isActive && (
          <motion.span
            layoutId="nav-indicator"
            className="absolute -left-3 top-1/2 -translate-y-1/2 w-[3px] h-5 bg-alpha rounded-r-full"
            transition={{ type: 'spring', stiffness: 380, damping: 32 }}
          />
        )}
        <Icon className={cn('w-4 h-4 shrink-0', isActive ? 'text-alpha' : 'text-current')} />
        <span className="flex-1 truncate">{label}</span>
        {hotkey && (
          <span className="opacity-0 group-hover:opacity-100 transition-opacity text-2xs text-ink-4 font-mono tracking-wider">{hotkey}</span>
        )}
      </>
    )}
  </NavLink>
);

const WatchlistRow = ({ ticker, horizon, onOpen }) => {
  const { toggleWatchlist } = useApp();
  const apiTicker = toApiTicker(ticker);
  const { data, loading } = useApi(() => api.predict({ ticker: apiTicker, horizon }), [apiTicker, horizon]);

  return (
    <div
      onClick={() => onOpen(ticker)}
      role="button"
      tabIndex={0}
      onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); onOpen(ticker); } }}
      className="w-full group flex items-center gap-2 px-3 py-2 rounded-lg hover:bg-bg-2 transition-colors text-left cursor-pointer focus-visible:shadow-focus-iris"
    >
      <span className="w-1 h-6 rounded-full bg-bg-3 group-hover:bg-alpha transition-colors" />
      <div className="flex-1 min-w-0">
        <div className="text-xs font-semibold text-ink-1 truncate tabular">{tickerSymbol(ticker)}</div>
        <div className="text-2xs text-ink-4 truncate">{loading ? '…' : data?.company_name || ''}</div>
      </div>
      <div className="flex flex-col items-end shrink-0">
        {loading ? (
          <div className="skeleton h-3 w-12" />
        ) : data ? (
          <>
            <div className="text-2xs font-medium tabular text-ink-2">
              ₹{data.current_price?.toLocaleString('en-IN', { maximumFractionDigits: 0 })}
            </div>
            <div className={cn(
              'text-2xs font-medium tabular flex items-center gap-0.5',
              signClass(data.prediction.predicted_return),
            )}>
              {data.prediction.predicted_return > 0 ? <IconArrowUp className="w-2.5 h-2.5" /> : data.prediction.predicted_return < 0 ? <IconArrowDown className="w-2.5 h-2.5" /> : null}
              {fmtPctRaw(data.prediction.predicted_return * 100, { dp: 1, signed: false })}
            </div>
          </>
        ) : null}
      </div>
      <button
        onClick={(e) => { e.stopPropagation(); toggleWatchlist(ticker); }}
        className="opacity-0 group-hover:opacity-100 transition-opacity w-6 h-6 grid place-items-center rounded-md text-alpha hover:bg-bg-3"
        aria-label="Remove from watchlist"
      >
        <IconStarFill className="w-3 h-3" />
      </button>
    </div>
  );
};

// Inner content — shared between desktop static aside and mobile drawer
const SidebarBody = ({ onNavigate, onClose, embedded = false }) => {
  const { watchlist, setPaletteOpen, prefs } = useApp();
  const navigate = useNavigate();
  const handleOpen = (tk) => {
    navigate(`/analysis?ticker=${encodeURIComponent(tk)}`);
    onNavigate?.();
  };

  return (
    <>
      <div className="px-5 py-4 border-b border-line-faint flex items-center justify-between">
        <Wordmark />
        {!embedded && onClose && (
          <button
            onClick={onClose}
            className="w-8 h-8 grid place-items-center rounded-md text-ink-3 hover:text-ink-1 hover:bg-bg-2"
            aria-label="Close menu"
          >
            <IconX className="w-4 h-4" />
          </button>
        )}
      </div>

      <div className="px-3 pt-3">
        <button
          onClick={() => { setPaletteOpen(true); onNavigate?.(); }}
          className="w-full flex items-center gap-2 px-3 h-9 rounded-lg border border-line-muted bg-bg-1 hover:bg-bg-2 hover:border-line-strong transition-all duration-180 text-left"
        >
          <IconCommand className="w-3.5 h-3.5 text-ink-4" />
          <span className="text-sm text-ink-3 flex-1">Quick jump…</span>
          <span className="kbd">⌘K</span>
        </button>
      </div>

      <nav className="px-3 pt-3 flex flex-col gap-0.5" aria-label="Primary">
        {NAV.map((n) => <NavItem key={n.to} {...n} onNavigate={onNavigate} />)}
      </nav>

      <div className="hairline mx-3 my-3" />

      <div className="px-3 pb-3 flex items-center justify-between">
        <div className="eyebrow flex items-center gap-1.5">
          Watchlist
          <span className="text-ink-5">·</span>
          <span className="text-ink-3 normal-case tracking-normal text-2xs">{horizonLabel(prefs.horizon)}</span>
        </div>
        <span className="text-2xs text-ink-4 tabular">{watchlist.length}</span>
      </div>

      <div className="flex-1 min-h-0 overflow-y-auto px-2 pb-2 flex flex-col gap-0.5 no-scrollbar">
        {watchlist.length === 0 ? (
          <div className="px-3 py-4 text-2xs text-ink-4 italic">No watched tickers yet. Star one from the screener.</div>
        ) : watchlist.map((t) => (
          <WatchlistRow key={t} ticker={t} horizon={prefs.horizon} onOpen={handleOpen} />
        ))}
      </div>

      <div className="border-t border-line-faint px-3 py-3 flex items-center gap-2">
        <NavLink
          to="/settings"
          onClick={onNavigate}
          className={({ isActive }) => cn(
            'inline-flex items-center gap-2 px-2.5 h-8 rounded-md text-xs text-ink-3 hover:text-ink-1 hover:bg-bg-2 transition-colors',
            isActive && 'text-ink-1 bg-bg-2',
          )}
        >
          <IconSettings className="w-3.5 h-3.5" /> Settings
        </NavLink>
        <span className="text-2xs text-ink-5 ml-auto">v1.0</span>
      </div>
    </>
  );
};

export const Sidebar = () => {
  const { sidebarOpen, setSidebarOpen } = useApp();
  const location = useLocation();

  // Close mobile drawer on route change
  useEffect(() => { if (sidebarOpen) setSidebarOpen(false); }, [location.pathname]);  // eslint-disable-line

  // Close on Escape
  useEffect(() => {
    if (!sidebarOpen) return;
    const onKey = (e) => { if (e.key === 'Escape') setSidebarOpen(false); };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [sidebarOpen, setSidebarOpen]);

  return (
    <>
      {/* Desktop ≥ lg: static sidebar */}
      <aside
        className="hidden lg:flex w-64 shrink-0 h-screen sticky top-0 bg-bg-0 border-r border-line-faint flex-col"
        aria-label="Primary navigation"
      >
        <SidebarBody embedded />
      </aside>

      {/* Mobile < lg: animated drawer */}
      <AnimatePresence>
        {sidebarOpen && (
          <motion.div
            className="lg:hidden fixed inset-0 z-[60]"
            initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
            transition={{ duration: 0.18 }}
          >
            <div
              className="absolute inset-0 bg-bg-0/80 backdrop-blur-sm"
              onClick={() => setSidebarOpen(false)}
              aria-hidden="true"
            />
            <motion.aside
              initial={{ x: -320 }} animate={{ x: 0 }} exit={{ x: -320 }}
              transition={{ type: 'spring', stiffness: 380, damping: 36 }}
              className="absolute left-0 top-0 bottom-0 w-72 max-w-[88vw] bg-bg-0 border-r border-line-faint flex flex-col"
              aria-label="Primary navigation"
            >
              <SidebarBody
                onNavigate={() => setSidebarOpen(false)}
                onClose={() => setSidebarOpen(false)}
              />
            </motion.aside>
          </motion.div>
        )}
      </AnimatePresence>
    </>
  );
};
