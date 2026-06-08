import React from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import { LayoutDashboard, Compass, Brain, Briefcase, FlaskConical, Newspaper, Settings } from 'lucide-react';
import { useApp } from '../../context/AppContext.jsx';
import { UserMenu } from './UserMenu.jsx';
import { IconCommand } from './Icons.jsx';
import { ExpandableTabs } from '@/components/ui/expandable-tabs.jsx';

const ROUTE_TITLES = {
  '/':          { eyebrow: 'Command Center', title: 'Market Overview' },
  '/screener':  { eyebrow: 'Discovery',      title: 'Market Screener' },
  '/analysis':  { eyebrow: 'Deep Dive',      title: 'Stock Analysis' },
  '/portfolio': { eyebrow: 'Allocation',     title: 'Portfolio Optimizer' },
  '/backtest':  { eyebrow: 'Validation',     title: 'Strategy Backtest' },
  '/settings':  { eyebrow: 'Configuration',  title: 'Settings' },
};

// Quick-nav for the top bar. A `route: null` entry marks a separator slot so
// the onChange index lines up 1:1 with the array passed to ExpandableTabs.
const NAV_TABS = [
  { title: 'Overview',  icon: LayoutDashboard, route: '/' },
  { title: 'Screener',  icon: Compass,         route: '/screener' },
  { title: 'Analysis',  icon: Brain,           route: '/analysis' },
  { type: 'separator',  route: null },
  { title: 'Portfolio', icon: Briefcase,       route: '/portfolio' },
  { title: 'Backtest',  icon: FlaskConical,    route: '/backtest' },
  { title: 'News',      icon: Newspaper,       route: '/news' },
  { type: 'separator',  route: null },
  { title: 'Settings',  icon: Settings,        route: '/settings' },
];

const HamburgerIcon = (p) => (
  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" {...p}>
    <path d="M4 7h16M4 12h16M4 17h16" />
  </svg>
);

export const Topbar = () => {
  const { pathname } = useLocation();
  const navigate = useNavigate();
  const { setPaletteOpen, setSidebarOpen } = useApp();
  const meta = ROUTE_TITLES[pathname] || { eyebrow: 'AlphaStock', title: 'Terminal' };

  const handleNavSelect = (index) => {
    const route = index != null ? NAV_TABS[index]?.route : null;
    if (route && route !== pathname) navigate(route);
  };

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

        <div className="ml-auto flex items-center gap-2">
          {/* Expandable quick-nav (large screens) */}
          <ExpandableTabs
            tabs={NAV_TABS.map(({ route, ...tab }) => tab)}
            onChange={handleNavSelect}
            className="hidden xl:flex mr-1 border-line-faint bg-bg-1/60 shadow-none"
          />

          <div className="hairline-v h-7 mx-0.5 hidden xl:block" />

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
