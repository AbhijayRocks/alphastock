import React from 'react';
import { useLocation } from 'react-router-dom';
import { useApp } from '../../context/AppContext.jsx';
import { useApi } from '../../hooks/useApi.js';
import { api } from '../../api/client.js';
import { Badge } from '../ui/Badge.jsx';
import { Tooltip } from '../ui/Tooltip.jsx';
import { UserMenu } from './UserMenu.jsx';
import { IconCommand, IconRefresh, IconActivity } from './Icons.jsx';
import { REGIME_META } from '../../data/universe.js';
import { cn } from '../../lib/utils.js';

const ROUTE_TITLES = {
  '/':          { eyebrow: 'Command Center', title: 'Market Overview' },
  '/screener':  { eyebrow: 'Discovery',      title: 'Market Screener' },
  '/analysis':  { eyebrow: 'Deep Dive',      title: 'Stock Analysis' },
  '/portfolio': { eyebrow: 'Allocation',     title: 'Portfolio Optimizer' },
  '/backtest':  { eyebrow: 'Validation',     title: 'Strategy Backtest' },
  '/settings':  { eyebrow: 'Configuration',  title: 'Settings' },
};

const HamburgerIcon = (p) => (
  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" {...p}>
    <path d="M4 7h16M4 12h16M4 17h16" />
  </svg>
);

export const Topbar = () => {
  const { pathname } = useLocation();
  const { backend, setPaletteOpen, setSidebarOpen } = useApp();
  const { data: regime, loading: rLoading, refetch: rRefetch } = useApi(() => api.regime(), []);
  const meta = ROUTE_TITLES[pathname] || { eyebrow: 'AlphaStock', title: 'Terminal' };
  const r = regime?.regime || 'unknown';
  const rm = REGIME_META[r] || REGIME_META.unknown;

  return (
    <header className="sticky top-0 z-30 bg-bg-0/85 backdrop-blur-md border-b border-line-faint">
      <div className="flex items-center gap-3 px-4 sm:px-6 h-14">
        {/* Mobile menu */}
        <button
          onClick={() => setSidebarOpen(true)}
          className="lg:hidden w-9 h-9 grid place-items-center rounded-lg border border-line-muted bg-bg-1 hover:bg-bg-2 transition-colors text-ink-2"
          aria-label="Open menu"
        >
          <HamburgerIcon className="w-4 h-4" />
        </button>

        <div className="min-w-0">
          <div className="eyebrow hidden sm:block">{meta.eyebrow}</div>
          <h1 className="font-display font-semibold text-md text-ink-1 leading-tight truncate">{meta.title}</h1>
        </div>

        <div className="hairline-v h-8 mx-2 hidden md:block" />

        {/* Regime indicator */}
        <Tooltip content={rm.description}>
          <button
            onClick={rRefetch}
            className="hidden md:inline-flex items-center gap-2 h-8 px-2.5 rounded-lg border border-line-muted bg-bg-1 hover:bg-bg-2 transition-colors group"
            aria-label={`Market regime: ${rm.label}. Click to refresh.`}
          >
            <span className={cn(
              'w-1.5 h-1.5 rounded-full',
              rm.tone === 'bull' && 'bg-bull animate-pulseSoft',
              rm.tone === 'bear' && 'bg-bear animate-pulseSoft',
              rm.tone === 'warn' && 'bg-warn animate-pulseSoft',
              (rm.tone === 'ink' || !rm.tone) && 'bg-ink-4',
            )} />
            <span className="text-2xs font-medium tracking-wider uppercase text-ink-3">Regime</span>
            <span className="text-xs font-semibold text-ink-1">{rLoading ? '…' : rm.label}</span>
            <IconRefresh className="w-3 h-3 text-ink-5 opacity-0 group-hover:opacity-100 transition-opacity" />
          </button>
        </Tooltip>

        <div className="ml-auto flex items-center gap-2">
          <Badge
            tone={backend.backendOk ? 'bull' : 'warn'}
            dot
            size="sm"
            className="hidden sm:inline-flex"
          >
            {backend.backendOk === null ? 'Connecting…' : backend.backendOk ? 'Live data' : 'Offline'}
          </Badge>

          <button
            onClick={() => setPaletteOpen(true)}
            className="inline-flex items-center gap-2 h-8 px-2.5 rounded-lg border border-line-muted bg-bg-1 hover:bg-bg-2 transition-colors text-xs text-ink-3"
            aria-label="Open command palette"
          >
            <IconCommand className="w-3.5 h-3.5" />
            <span className="hidden sm:inline">Search</span>
            <span className="kbd">⌘K</span>
          </button>

          <div className="hairline-v h-7 mx-0.5 hidden sm:block" />

          <UserMenu />
        </div>
      </div>
    </header>
  );
};
