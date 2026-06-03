import React from 'react';
import { Link } from 'react-router-dom';
import { useApp } from '../../context/AppContext.jsx';
import { cn } from '../../lib/utils.js';

// Application footer — intentionally minimal and institutional.
// Status reflects live connectivity rather than any "demo" labelling.
export const Footer = () => {
  const { backend } = useApp();
  const year = new Date().getFullYear();
  const live = backend.backendOk;

  return (
    <footer className="border-t border-line-faint mt-2">
      <div className="max-w-[1440px] mx-auto px-4 sm:px-6 py-4 flex flex-col sm:flex-row items-center justify-between gap-3">
        <div className="flex items-center gap-2 text-2xs text-ink-4">
          <span className="font-medium text-ink-3">© {year} AlphaStock</span>
          <span className="text-ink-5">·</span>
          <span>NSE equities</span>
          <span className="text-ink-5 hidden sm:inline">·</span>
          <span className="hidden sm:inline">All rights reserved</span>
        </div>

        <div className="flex items-center gap-4 text-2xs text-ink-4">
          <Link to="/settings" className="hover:text-ink-2 transition-colors">Settings</Link>
          <span className="text-ink-5">·</span>
          <span className="inline-flex items-center gap-1.5">
            <span className={cn(
              'w-1.5 h-1.5 rounded-full',
              live === null ? 'bg-ink-4' : live ? 'bg-bull' : 'bg-warn',
            )} />
            <span>{live === null ? 'Connecting' : live ? 'Market data live' : 'Cached data'}</span>
          </span>
        </div>
      </div>
    </footer>
  );
};
