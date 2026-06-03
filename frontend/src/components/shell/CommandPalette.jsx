import React, { useEffect, useMemo, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { AnimatePresence, motion } from 'framer-motion';
import { useApp } from '../../context/AppContext.jsx';
import { UNIVERSE } from '../../data/universe.js';
import {
  IconSearch, IconHome, IconCompass, IconBrain, IconBriefcase, IconBeaker,
  IconSettings, IconStar, IconArrowRight,
} from './Icons.jsx';
import { cn, tickerSymbol } from '../../lib/utils.js';

const NAV_ITEMS = [
  { id: 'nav-overview',  label: 'Overview',  path: '/',          icon: IconHome,      group: 'Navigate' },
  { id: 'nav-screener',  label: 'Screener',  path: '/screener',  icon: IconCompass,   group: 'Navigate' },
  { id: 'nav-analysis',  label: 'Analysis',  path: '/analysis',  icon: IconBrain,     group: 'Navigate' },
  { id: 'nav-portfolio', label: 'Portfolio', path: '/portfolio', icon: IconBriefcase, group: 'Navigate' },
  { id: 'nav-backtest',  label: 'Backtest',  path: '/backtest',  icon: IconBeaker,    group: 'Navigate' },
  { id: 'nav-settings',  label: 'Settings',  path: '/settings',  icon: IconSettings,  group: 'Navigate' },
];

export const CommandPalette = () => {
  const { paletteOpen, setPaletteOpen, toggleWatchlist, isWatched } = useApp();
  const [q, setQ] = useState('');
  const [active, setActive] = useState(0);
  const inputRef = useRef(null);
  const listRef  = useRef(null);
  const navigate = useNavigate();

  useEffect(() => { if (paletteOpen) { setQ(''); setActive(0); setTimeout(() => inputRef.current?.focus(), 30); } }, [paletteOpen]);

  const items = useMemo(() => {
    const needle = q.trim().toLowerCase();
    const tickers = UNIVERSE.map((u) => ({
      id: `t-${u.ticker}`,
      label: tickerSymbol(u.ticker),
      sub: u.name,
      meta: u.sector,
      ticker: u.ticker,
      type: 'ticker',
      group: 'Tickers',
    }));
    const all = [...NAV_ITEMS, ...tickers];
    if (!needle) return all.slice(0, 24);
    return all
      .map((it) => {
        const hay = `${it.label} ${it.sub || ''} ${it.meta || ''}`.toLowerCase();
        const score = hay.includes(needle) ? (it.label.toLowerCase().startsWith(needle) ? 2 : 1) : 0;
        return { it, score };
      })
      .filter((x) => x.score > 0)
      .sort((a, b) => b.score - a.score)
      .slice(0, 24)
      .map((x) => x.it);
  }, [q]);

  const groups = useMemo(() => {
    const map = new Map();
    items.forEach((it) => { if (!map.has(it.group)) map.set(it.group, []); map.get(it.group).push(it); });
    return [...map.entries()];
  }, [items]);

  const flatIndex = useMemo(() => groups.flatMap(([, xs]) => xs), [groups]);

  useEffect(() => { setActive((i) => Math.min(i, Math.max(0, flatIndex.length - 1))); }, [flatIndex.length]);
  useEffect(() => {
    listRef.current?.querySelector(`[data-idx="${active}"]`)?.scrollIntoView({ block: 'nearest' });
  }, [active]);

  const runItem = (it) => {
    if (!it) return;
    if (it.type === 'ticker') navigate(`/analysis?ticker=${encodeURIComponent(it.ticker)}`);
    else if (it.path)         navigate(it.path);
    setPaletteOpen(false);
  };

  const onKeyDown = (e) => {
    if (e.key === 'ArrowDown') { e.preventDefault(); setActive((i) => Math.min(flatIndex.length - 1, i + 1)); }
    else if (e.key === 'ArrowUp') { e.preventDefault(); setActive((i) => Math.max(0, i - 1)); }
    else if (e.key === 'Enter')   { e.preventDefault(); runItem(flatIndex[active]); }
    else if (e.key === 'Escape')  { e.preventDefault(); setPaletteOpen(false); }
  };

  return (
    <AnimatePresence>
      {paletteOpen && (
        <motion.div
          className="fixed inset-0 z-[100] flex items-start justify-center pt-[12vh] px-4"
          initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
          transition={{ duration: 0.18 }}
          onMouseDown={(e) => { if (e.target === e.currentTarget) setPaletteOpen(false); }}
        >
          <div className="absolute inset-0 bg-bg-0/70 backdrop-blur-sm" />
          <motion.div
            initial={{ opacity: 0, y: 12, scale: 0.98 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: 8, scale: 0.985 }}
            transition={{ duration: 0.22, ease: [0.22, 0.61, 0.36, 1] }}
            className="relative w-full max-w-2xl surface-elev shadow-pop overflow-hidden"
            role="dialog" aria-label="Command palette"
          >
            <div className="flex items-center gap-3 h-12 px-4 border-b border-line-muted">
              <IconSearch className="w-4 h-4 text-ink-4" />
              <input
                ref={inputRef}
                value={q}
                onChange={(e) => setQ(e.target.value)}
                onKeyDown={onKeyDown}
                placeholder="Search tickers, pages, actions…"
                className="flex-1 bg-transparent text-sm text-ink-1 placeholder:text-ink-4 outline-none"
              />
              <span className="kbd">esc</span>
            </div>

            <div ref={listRef} className="max-h-[58vh] overflow-y-auto py-2">
              {flatIndex.length === 0 ? (
                <div className="px-4 py-8 text-center text-sm text-ink-4">No results for “{q}”.</div>
              ) : groups.map(([g, xs]) => (
                <div key={g} className="px-2 pb-1">
                  <div className="eyebrow px-2 py-1.5">{g}</div>
                  {xs.map((it) => {
                    const idx = flatIndex.indexOf(it);
                    const isActive = idx === active;
                    return (
                      <button
                        key={it.id}
                        data-idx={idx}
                        onMouseEnter={() => setActive(idx)}
                        onClick={() => runItem(it)}
                        className={cn(
                          'w-full flex items-center gap-3 px-3 h-10 rounded-lg text-left',
                          isActive ? 'bg-bg-3 border border-line-strong' : 'border border-transparent hover:bg-bg-2',
                        )}
                      >
                        <span className={cn(
                          'w-7 h-7 grid place-items-center rounded-md border',
                          isActive ? 'border-line-strong bg-bg-2 text-alpha' : 'border-line-muted bg-bg-2 text-ink-3',
                        )}>
                          {it.type === 'ticker' ? (
                            <span className="text-2xs font-semibold tabular">{it.label.slice(0, 3)}</span>
                          ) : (
                            <it.icon className="w-3.5 h-3.5" />
                          )}
                        </span>
                        <div className="min-w-0 flex-1">
                          <div className="text-sm text-ink-1 font-medium truncate">{it.label}</div>
                          {it.sub && <div className="text-2xs text-ink-4 truncate">{it.sub}</div>}
                        </div>
                        {it.meta && <span className="text-2xs text-ink-4 hidden sm:inline">{it.meta}</span>}
                        {it.type === 'ticker' && (
                          <button
                            onClick={(e) => { e.stopPropagation(); toggleWatchlist(it.ticker); }}
                            className={cn(
                              'w-7 h-7 grid place-items-center rounded-md hover:bg-bg-3',
                              isWatched(it.ticker) ? 'text-alpha' : 'text-ink-4',
                            )}
                            aria-label="Toggle watchlist"
                          >
                            <IconStar className="w-3.5 h-3.5" />
                          </button>
                        )}
                        <IconArrowRight className="w-3.5 h-3.5 text-ink-5" />
                      </button>
                    );
                  })}
                </div>
              ))}
            </div>

            <div className="flex items-center gap-3 px-4 h-10 border-t border-line-muted text-2xs text-ink-4">
              <span className="flex items-center gap-1.5"><span className="kbd">↑</span><span className="kbd">↓</span> navigate</span>
              <span className="flex items-center gap-1.5"><span className="kbd">↵</span> open</span>
              <span className="flex items-center gap-1.5"><span className="kbd">esc</span> close</span>
              <span className="ml-auto text-ink-5">{flatIndex.length} results</span>
            </div>
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>
  );
};
