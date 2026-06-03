import React, { useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import { motion } from 'framer-motion';
import { useApi } from '../hooks/useApi.js';
import { api } from '../api/client.js';
import { useApp } from '../context/AppContext.jsx';
import { useToast } from '../components/ui/Toast.jsx';
import { Card } from '../components/ui/Card.jsx';
import { Button } from '../components/ui/Button.jsx';
import { Input, Select } from '../components/ui/Input.jsx';
import { Pill } from '../components/ui/Badge.jsx';
import { Sparkline } from '../components/charts/Sparkline.jsx';
import { HorizonSwitcher } from '../components/domain/HorizonSwitcher.jsx';
import { DirectionPill, SignalStrengthBar, ConfidenceMeter } from '../components/domain/DirectionPill.jsx';
import { EmptyState } from '../components/ui/Empty.jsx';
import { Skeleton } from '../components/ui/Skeleton.jsx';
import {
  IconSearch, IconStar, IconStarFill,
  IconRefresh, IconDownload, IconSliders, IconArrowUp, IconArrowDown,
} from '../components/shell/Icons.jsx';
import { UNIVERSE, SECTORS, META_BY_TICKER, SECTOR_COLOR } from '../data/universe.js';
import {
  toApiTicker, toDisplayTicker, tickerSymbol, cn, fmtPrice, hashStr, seedRandom, signClass,
} from '../lib/utils.js';

// ── CSV export ────────────────────────────────────────────────────────────────
const csvEscape = (v) => {
  if (v == null) return '';
  const s = String(v);
  return /[",\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s;
};

const buildCsv = (rows, horizon) => {
  const header = [
    'ticker', 'company', 'sector', 'industry', 'current_price',
    'direction', 'probability', `predicted_return_${horizon}`,
    'confidence_lower', 'confidence_upper', 'signal_strength',
    'regime', 'last_updated',
  ];
  const lines = [header.join(',')];
  for (const p of rows) {
    const display = toDisplayTicker(p.ticker);
    const meta = META_BY_TICKER[display] || {};
    lines.push([
      tickerSymbol(display),
      p.company_name,
      p.sector,
      meta.industry || '',
      p.current_price,
      p.prediction.direction,
      p.prediction.probability,
      p.prediction.predicted_return,
      p.prediction.confidence_lower,
      p.prediction.confidence_upper,
      p.prediction.signal_strength,
      p.regime,
      p.last_updated,
    ].map(csvEscape).join(','));
  }
  return lines.join('\n');
};

const downloadCsv = (text, filename) => {
  const blob = new Blob([text], { type: 'text/csv;charset=utf-8;' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url; a.download = filename; document.body.appendChild(a);
  a.click(); document.body.removeChild(a);
  setTimeout(() => URL.revokeObjectURL(url), 1500);
};

const fadeUp = {
  initial: { opacity: 0, y: 8 },
  animate: { opacity: 1, y: 0 },
  transition: { duration: 0.32, ease: [0.22, 0.61, 0.36, 1] },
};

const useScreenerData = (horizon) => {
  const tickers = useMemo(() => UNIVERSE.map((u) => toApiTicker(u.ticker)), []);
  return useApi(
    async () => {
      const res = await Promise.allSettled(tickers.map((t) => api.predict({ ticker: t, horizon })));
      return res.filter((r) => r.status === 'fulfilled').map((r) => r.value);
    },
    [horizon, tickers.join(',')],
  );
};

const SORTS = [
  { value: 'return-desc', label: 'Expected return — high to low' },
  { value: 'return-asc',  label: 'Expected return — low to high' },
  { value: 'conf-desc',   label: 'Confidence — high to low' },
  { value: 'sym-asc',     label: 'Ticker — A to Z' },
  { value: 'price-desc',  label: 'Price — high to low' },
];

const DIRECTIONS = [
  { value: 'all',  label: 'All' },
  { value: 'UP',   label: 'Long only' },
  { value: 'DOWN', label: 'Short only' },
];

const STRENGTHS = [
  { value: 'all',      label: 'Any strength' },
  { value: 'strong',   label: 'Strong only' },
  { value: 'moderate', label: 'Moderate+' },
];

const sparkFor = (apiTicker) => {
  const rng = seedRandom(hashStr(apiTicker + ':scr'));
  let v = 100; const out = [];
  for (let i = 0; i < 30; i++) { v *= 1 + (rng() - 0.5) * 0.03; out.push({ price: v }); }
  return out;
};

const Screener = () => {
  const { prefs, updatePrefs, isWatched, toggleWatchlist } = useApp();
  const toast = useToast();
  const horizon = prefs.horizon;
  const [q, setQ] = useState('');
  const [sector, setSector] = useState('all');
  const [direction, setDirection] = useState('all');
  const [strength, setStrength] = useState('all');
  const [sort, setSort] = useState('return-desc');
  const [showFilters, setShowFilters] = useState(true);

  const { data, loading, refetch } = useScreenerData(horizon);

  const filtered = useMemo(() => {
    let xs = data || [];
    const needle = q.trim().toLowerCase();
    if (needle) {
      xs = xs.filter((p) => {
        const display = toDisplayTicker(p.ticker);
        return display.toLowerCase().includes(needle)
          || p.company_name.toLowerCase().includes(needle)
          || (p.sector || '').toLowerCase().includes(needle);
      });
    }
    if (sector !== 'all') xs = xs.filter((p) => p.sector === sector);
    if (direction !== 'all') xs = xs.filter((p) => p.prediction.direction === direction);
    if (strength === 'strong') xs = xs.filter((p) => p.prediction.signal_strength === 'strong');
    else if (strength === 'moderate') xs = xs.filter((p) => p.prediction.signal_strength !== 'weak');

    const sorted = [...xs];
    if (sort === 'return-desc') sorted.sort((a, b) => b.prediction.predicted_return - a.prediction.predicted_return);
    else if (sort === 'return-asc') sorted.sort((a, b) => a.prediction.predicted_return - b.prediction.predicted_return);
    else if (sort === 'conf-desc') sorted.sort((a, b) => Math.abs(b.prediction.probability - 0.5) - Math.abs(a.prediction.probability - 0.5));
    else if (sort === 'sym-asc') sorted.sort((a, b) => a.ticker.localeCompare(b.ticker));
    else if (sort === 'price-desc') sorted.sort((a, b) => b.current_price - a.current_price);
    return sorted;
  }, [data, q, sector, direction, strength, sort]);

  const stats = useMemo(() => ({
    total: filtered.length,
    longs: filtered.filter((p) => p.prediction.direction === 'UP').length,
    shorts: filtered.filter((p) => p.prediction.direction === 'DOWN').length,
    strong: filtered.filter((p) => p.prediction.signal_strength === 'strong').length,
  }), [filtered]);

  const clearFilters = () => { setQ(''); setSector('all'); setDirection('all'); setStrength('all'); };
  const activeFilterCount = [q && 'q', sector !== 'all' && 'sec', direction !== 'all' && 'dir', strength !== 'all' && 'str'].filter(Boolean).length;

  return (
    <div className="space-y-5 pb-10">
      <motion.div {...fadeUp} className="flex items-center justify-between gap-3 flex-wrap">
        <div className="flex items-center gap-3">
          <span className="eyebrow">Forecast horizon</span>
          <HorizonSwitcher value={horizon} onChange={(v) => updatePrefs({ horizon: v })} />
        </div>
        <div className="flex items-center gap-2">
          <Button size="sm" variant="ghost" leadingIcon={IconRefresh} onClick={refetch}>Refresh</Button>
          <Button
            size="sm"
            variant="ghost"
            leadingIcon={IconDownload}
            disabled={!filtered.length}
            onClick={() => {
              if (!filtered.length) return;
              const stamp = new Date().toISOString().slice(0, 19).replace(/[:T]/g, '-');
              downloadCsv(buildCsv(filtered, horizon), `alphastock-screener-${horizon}-${stamp}.csv`);
              toast.success({ title: 'Exported CSV', description: `${filtered.length} rows · ${horizon}` });
            }}
          >Export CSV</Button>
          <Button size="sm" variant="ghost" leadingIcon={IconSliders} onClick={() => setShowFilters((x) => !x)}>
            {showFilters ? 'Hide filters' : 'Show filters'}
          </Button>
        </div>
      </motion.div>

      {/* Filters */}
      {showFilters && (
        <motion.div {...fadeUp}>
          <Card>
            <div className="p-4 grid grid-cols-1 md:grid-cols-12 gap-3 items-end">
              <div className="md:col-span-4">
                <label className="eyebrow block mb-1.5">Search</label>
                <Input
                  value={q}
                  onChange={(e) => setQ(e.target.value)}
                  leadingIcon={IconSearch}
                  placeholder="Ticker, company, sector…"
                />
              </div>
              <div className="md:col-span-3">
                <label className="eyebrow block mb-1.5">Sector</label>
                <Select value={sector} onChange={(e) => setSector(e.target.value)}>
                  <option value="all">All sectors</option>
                  {SECTORS.map((s) => <option key={s} value={s}>{s}</option>)}
                </Select>
              </div>
              <div className="md:col-span-2">
                <label className="eyebrow block mb-1.5">Direction</label>
                <Select value={direction} onChange={(e) => setDirection(e.target.value)}>
                  {DIRECTIONS.map((d) => <option key={d.value} value={d.value}>{d.label}</option>)}
                </Select>
              </div>
              <div className="md:col-span-3">
                <label className="eyebrow block mb-1.5">Strength</label>
                <Select value={strength} onChange={(e) => setStrength(e.target.value)}>
                  {STRENGTHS.map((d) => <option key={d.value} value={d.value}>{d.label}</option>)}
                </Select>
              </div>
            </div>
            <div className="hairline mx-4" />
            <div className="p-3 flex items-center justify-between gap-3 flex-wrap">
              <div className="flex items-center gap-2 flex-wrap">
                <Pill>{stats.total} matches</Pill>
                <Pill className="text-bull border-bull/25 bg-bull/10">{stats.longs} longs</Pill>
                <Pill className="text-bear border-bear/25 bg-bear/10">{stats.shorts} shorts</Pill>
                <Pill className="text-alpha border-alpha/25 bg-alpha/10">{stats.strong} strong</Pill>
                {activeFilterCount > 0 && (
                  <button onClick={clearFilters} className="text-2xs font-medium text-ink-4 hover:text-ink-1 px-2 py-0.5 rounded-md hover:bg-bg-2 transition-colors">
                    Clear {activeFilterCount}
                  </button>
                )}
              </div>
              <div className="flex items-center gap-2">
                <span className="eyebrow hidden md:inline">Sort</span>
                <Select size="sm" value={sort} onChange={(e) => setSort(e.target.value)} className="min-w-[260px]">
                  {SORTS.map((s) => <option key={s.value} value={s.value}>{s.label}</option>)}
                </Select>
              </div>
            </div>
          </Card>
        </motion.div>
      )}

      {/* Table */}
      <motion.div {...fadeUp}>
        <Card>
          <div className="overflow-hidden">
            {/* Header */}
            <div className="grid items-center gap-3 px-4 h-10 border-b border-line-muted bg-bg-2/40 sticky top-0 z-10 text-2xs font-medium tracking-wider uppercase text-ink-4"
                 style={{ gridTemplateColumns: '28px 1.7fr 1.1fr 0.8fr 0.9fr 1fr 0.9fr 80px 32px' }}>
              <span></span>
              <span>Ticker</span>
              <span>Sector</span>
              <span className="text-right">Price</span>
              <span className="text-center">Direction</span>
              <span>Confidence</span>
              <span className="text-right">Exp. Return</span>
              <span className="text-right">30d</span>
              <span></span>
            </div>

            {/* Body */}
            <div className="max-h-[calc(100vh-360px)] overflow-y-auto">
              {loading && filtered.length === 0 ? (
                Array.from({ length: 14 }).map((_, i) => (
                  <div key={i} className="grid items-center gap-3 px-4 h-12 border-b border-line-faint"
                       style={{ gridTemplateColumns: '28px 1.7fr 1.1fr 0.8fr 0.9fr 1fr 0.9fr 80px 32px' }}>
                    <Skeleton className="w-4 h-4 rounded" />
                    <Skeleton className="h-3 w-32" />
                    <Skeleton className="h-3 w-20" />
                    <Skeleton className="h-3 w-14 ml-auto" />
                    <Skeleton className="h-5 w-16 mx-auto" />
                    <Skeleton className="h-1.5 w-full" />
                    <Skeleton className="h-3 w-12 ml-auto" />
                    <Skeleton className="h-4 w-full" />
                    <Skeleton className="w-5 h-5 rounded" />
                  </div>
                ))
              ) : filtered.length === 0 ? (
                <EmptyState
                  icon={IconSearch}
                  title="No matches"
                  description="Try clearing some filters or changing the horizon."
                  action={<Button size="sm" variant="surface" onClick={clearFilters}>Clear filters</Button>}
                />
              ) : (
                filtered.map((p, idx) => {
                  const display = toDisplayTicker(p.ticker);
                  const sym = tickerSymbol(display);
                  const meta = META_BY_TICKER[display];
                  const color = SECTOR_COLOR[p.sector] || '#94A3B8';
                  const watched = isWatched(display);
                  return (
                    <Link
                      key={p.ticker}
                      to={`/analysis?ticker=${encodeURIComponent(display)}`}
                      className="group grid items-center gap-3 px-4 h-14 border-b border-line-faint hover:bg-bg-2 transition-colors"
                      style={{ gridTemplateColumns: '28px 1.7fr 1.1fr 0.8fr 0.9fr 1fr 0.9fr 80px 32px' }}
                    >
                      <span className="text-2xs font-mono text-ink-5 tabular">{String(idx + 1).padStart(2, '0')}</span>
                      <div className="flex items-center gap-2.5 min-w-0">
                        <span
                          className="w-8 h-8 grid place-items-center rounded-md bg-bg-2 border border-line-muted text-2xs font-mono font-semibold tabular group-hover:border-line-strong shrink-0"
                          style={{ color }}
                        >{sym.slice(0, 3)}</span>
                        <div className="min-w-0">
                          <div className="text-sm font-semibold text-ink-1 truncate group-hover:text-alpha transition-colors">{sym}</div>
                          <div className="text-2xs text-ink-4 truncate">{p.company_name}</div>
                        </div>
                      </div>
                      <div className="min-w-0">
                        <div className="text-xs text-ink-2 truncate">{p.sector}</div>
                        <div className="text-2xs text-ink-5 truncate">{meta?.industry}</div>
                      </div>
                      <div className="text-right">
                        <div className="text-sm font-semibold text-ink-1 tabular">{fmtPrice(p.current_price, { dp: 2 })}</div>
                      </div>
                      <div className="flex items-center justify-center gap-1.5">
                        <DirectionPill
                          direction={p.prediction.direction}
                          probability={p.prediction.probability}
                          size="sm"
                        />
                      </div>
                      <div className="flex items-center gap-2">
                        <ConfidenceMeter probability={p.prediction.probability} className="w-full" />
                        <SignalStrengthBar strength={p.prediction.signal_strength} />
                      </div>
                      <div className={cn(
                        'text-sm font-semibold tabular inline-flex items-center justify-end gap-0.5 w-full',
                        signClass(p.prediction.predicted_return),
                      )}>
                        {p.prediction.predicted_return > 0 ? <IconArrowUp className="w-3 h-3" /> : p.prediction.predicted_return < 0 ? <IconArrowDown className="w-3 h-3" /> : null}
                        {p.prediction.predicted_return > 0 ? '+' : ''}{(p.prediction.predicted_return * 100).toFixed(2)}%
                      </div>
                      <Sparkline
                        data={sparkFor(p.ticker)}
                        stroke={p.prediction.predicted_return >= 0 ? '#10B981' : '#F43F5E'}
                        width={72} height={20} fill={false}
                      />
                      <button
                        onClick={(e) => { e.preventDefault(); e.stopPropagation(); toggleWatchlist(display); }}
                        className={cn(
                          'w-7 h-7 grid place-items-center rounded-md transition-colors',
                          watched ? 'text-alpha hover:bg-bg-3' : 'text-ink-5 hover:text-ink-2 hover:bg-bg-3',
                        )}
                        aria-label={watched ? 'Remove from watchlist' : 'Add to watchlist'}
                      >
                        {watched ? <IconStarFill className="w-3.5 h-3.5" /> : <IconStar className="w-3.5 h-3.5" />}
                      </button>
                    </Link>
                  );
                })
              )}
            </div>
          </div>
        </Card>
      </motion.div>

      <div className="text-2xs text-ink-5 text-center pt-2">
        {filtered.length} of {data?.length || 50} stocks · horizon {horizon} · sorted by {SORTS.find((s) => s.value === sort)?.label}
      </div>
    </div>
  );
};

export default Screener;
