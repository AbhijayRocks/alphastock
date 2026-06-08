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
import { AnimatedGlowingSearchBar } from '@/components/ui/animated-glowing-search-bar.jsx';
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
    'market_cap_cr', 'pe', 'forward_pe', 'pb', 'roe_pct', 'roa_pct',
    'de_ratio', 'revenue_growth_pct', 'earnings_growth_pct', 'dividend_yield_pct', 'beta',
    'rsi_14', 'macd_hist', 'vs_sma_50', 'vs_sma_200', 'from_52w_high',
    'ret_5d', 'ret_20d', 'ret_60d', 'rvol', 'garch_vol', 'xsec_signal',
    'regime', 'last_updated',
  ];
  const lines = [header.join(',')];
  for (const p of rows) {
    const display = toDisplayTicker(p.ticker);
    const meta = META_BY_TICKER[display] || {};
    const f = p.fundamentals || {};
    const t = p.technicals || {};
    const fv = (v) => (v == null ? '' : v);
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
      fv(f.market_cap_cr), fv(f.pe), fv(f.forward_pe), fv(f.pb), fv(f.roe), fv(f.roa),
      fv(f.de), fv(f.revenue_growth), fv(f.earnings_growth), fv(f.dividend_yield), fv(f.beta),
      fv(t.rsi_14), fv(t.macd_hist), fv(t.vs_sma_50), fv(t.vs_sma_200), fv(t.from_52w_high),
      fv(t.ret_5d), fv(t.ret_20d), fv(t.ret_60d), fv(t.rvol), fv(t.garch_vol), p.signal?.side || '',
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

// One fast call returns the whole board (model + technicals + fundamentals +
// cross-sectional signal per stock), replacing 50 per-stock /predict requests.
const useScreenerData = (horizon) => useApi(() => api.screen(horizon), [horizon]);

const SORTS = [
  { value: 'return-desc', label: 'Expected return — high to low' },
  { value: 'return-asc',  label: 'Expected return — low to high' },
  { value: 'conf-desc',   label: 'Confidence — high to low' },
  { value: 'mcap-desc',   label: 'Market cap — high to low' },
  { value: 'pe-asc',      label: 'P/E — low to high' },
  { value: 'roe-desc',    label: 'ROE — high to low' },
  { value: 'div-desc',    label: 'Dividend yield — high to low' },
  { value: 'rsi-asc',     label: 'RSI — low to high (oversold first)' },
  { value: 'ret20-desc',  label: '1-month return — high to low' },
  { value: 'sym-asc',     label: 'Ticker — A to Z' },
  { value: 'price-desc',  label: 'Price — high to low' },
];

// Fundamental formatters (values arrive pre-normalized from /api/fundamentals).
const fmtMcap = (cr) => cr == null ? '—'
  : cr >= 1e5 ? `₹${(cr / 1e5).toFixed(2)}L Cr`
  : `₹${Math.round(cr).toLocaleString('en-IN')} Cr`;
const fmtNum = (v, dp = 2, suffix = '') => (v == null || Number.isNaN(v)) ? '—' : `${v.toFixed(dp)}${suffix}`;
// Treat a min/max input as inactive when blank; coerce to number otherwise.
const numOr = (s) => s === '' || s == null ? null : Number(s);

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

// One-click screens. Each `f` is a partial filter set applied on a clean slate.
const PRESETS = [
  { id: 'value',    label: 'Value',            f: { peMax: '20', roeMin: '15' } },
  { id: 'quality',  label: 'Quality',          f: { roeMin: '18', deMax: '0.5' } },
  { id: 'dividend', label: 'High dividend',    f: { divMin: '2' } },
  { id: 'oversold', label: 'Oversold bounce',  f: { rsiMax: '35', aboveSma200: true } },
  { id: 'breakout', label: '52w breakout',     f: { near52High: '3', aboveSma50: true } },
  { id: 'momentum', label: 'Momentum',         f: { ret1mMin: '8', aboveSma50: true } },
  { id: 'longs',    label: 'Conviction longs', f: { signalSide: 'LONG', direction: 'UP' } },
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
  // Fundamental filters (blank = inactive)
  const [peMax, setPeMax] = useState('');
  const [roeMin, setRoeMin] = useState('');
  const [mcapMin, setMcapMin] = useState('');
  const [divMin, setDivMin] = useState('');
  const [deMax, setDeMax] = useState('');
  // Technical filters
  const [rsiMax, setRsiMax] = useState('');
  const [rsiMin, setRsiMin] = useState('');
  const [aboveSma50, setAboveSma50] = useState(false);
  const [aboveSma200, setAboveSma200] = useState(false);
  const [near52High, setNear52High] = useState('');
  const [ret1mMin, setRet1mMin] = useState('');
  // Model & signal filters
  const [probMin, setProbMin] = useState('');
  const [expRetMin, setExpRetMin] = useState('');
  const [signalSide, setSignalSide] = useState('all');

  const { data: screenResp, loading, refetch } = useScreenerData(horizon);

  // Adapt each /api/screen row to the shape the table already expects
  // (a nested `prediction` object), keeping technicals / fundamentals / signal.
  const data = useMemo(() => (screenResp?.rows || []).map((r) => ({
    ...r,
    prediction: {
      direction: r.direction,
      probability: r.probability,
      predicted_return: r.predicted_return ?? 0,
      signal_strength: r.signal_strength,
    },
  })), [screenResp]);

  const filtered = useMemo(() => {
    let xs = data || [];
    const needle = q.trim().toLowerCase();
    if (needle) {
      xs = xs.filter((p) => {
        const display = toDisplayTicker(p.ticker);
        return display.toLowerCase().includes(needle)
          || (p.company_name || '').toLowerCase().includes(needle)
          || (p.sector || '').toLowerCase().includes(needle);
      });
    }
    if (sector !== 'all') xs = xs.filter((p) => p.sector === sector);
    if (direction !== 'all') xs = xs.filter((p) => p.prediction.direction === direction);
    if (strength === 'strong') xs = xs.filter((p) => p.prediction.signal_strength === 'strong');
    else if (strength === 'moderate') xs = xs.filter((p) => p.prediction.signal_strength !== 'weak');

    // Fundamental filters — a stock missing the value for an active filter is excluded.
    const fpe = numOr(peMax), froe = numOr(roeMin), fmc = numOr(mcapMin), fdiv = numOr(divMin), fde = numOr(deMax);
    const pass = (v, ok) => (v == null ? false : ok(v));
    if (fpe  != null) xs = xs.filter((p) => pass(p.fundamentals?.pe,             (v) => v <= fpe));
    if (froe != null) xs = xs.filter((p) => pass(p.fundamentals?.roe,            (v) => v >= froe));
    if (fmc  != null) xs = xs.filter((p) => pass(p.fundamentals?.market_cap_cr,  (v) => v >= fmc));
    if (fdiv != null) xs = xs.filter((p) => pass(p.fundamentals?.dividend_yield, (v) => v >= fdiv));
    if (fde  != null) xs = xs.filter((p) => pass(p.fundamentals?.de,             (v) => v <= fde));

    // Technical filters
    const rmax = numOr(rsiMax), rmin = numOr(rsiMin), n52 = numOr(near52High), r1m = numOr(ret1mMin);
    if (rmax != null) xs = xs.filter((p) => p.technicals?.rsi_14 != null && p.technicals.rsi_14 <= rmax);
    if (rmin != null) xs = xs.filter((p) => p.technicals?.rsi_14 != null && p.technicals.rsi_14 >= rmin);
    if (aboveSma50)   xs = xs.filter((p) => (p.technicals?.vs_sma_50 ?? -1) > 0);
    if (aboveSma200)  xs = xs.filter((p) => (p.technicals?.vs_sma_200 ?? -1) > 0);
    if (n52 != null)  xs = xs.filter((p) => p.technicals?.from_52w_high != null && p.technicals.from_52w_high >= -(n52 / 100));
    if (r1m != null)  xs = xs.filter((p) => p.technicals?.ret_20d != null && p.technicals.ret_20d * 100 >= r1m);

    // Model & signal filters
    const pmin = numOr(probMin), ermin = numOr(expRetMin);
    if (pmin != null)  xs = xs.filter((p) => p.prediction.probability * 100 >= pmin);
    if (ermin != null) xs = xs.filter((p) => (p.prediction.predicted_return ?? 0) * 100 >= ermin);
    if (signalSide !== 'all') xs = xs.filter((p) => p.signal?.side === signalSide);

    const sorted = [...xs];
    if (sort === 'return-desc') sorted.sort((a, b) => b.prediction.predicted_return - a.prediction.predicted_return);
    else if (sort === 'return-asc') sorted.sort((a, b) => a.prediction.predicted_return - b.prediction.predicted_return);
    else if (sort === 'conf-desc') sorted.sort((a, b) => Math.abs(b.prediction.probability - 0.5) - Math.abs(a.prediction.probability - 0.5));
    else if (sort === 'mcap-desc') sorted.sort((a, b) => (b.fundamentals?.market_cap_cr ?? -Infinity) - (a.fundamentals?.market_cap_cr ?? -Infinity));
    else if (sort === 'pe-asc')    sorted.sort((a, b) => (a.fundamentals?.pe ?? Infinity) - (b.fundamentals?.pe ?? Infinity));
    else if (sort === 'roe-desc')  sorted.sort((a, b) => (b.fundamentals?.roe ?? -Infinity) - (a.fundamentals?.roe ?? -Infinity));
    else if (sort === 'div-desc')  sorted.sort((a, b) => (b.fundamentals?.dividend_yield ?? -Infinity) - (a.fundamentals?.dividend_yield ?? -Infinity));
    else if (sort === 'rsi-asc')   sorted.sort((a, b) => (a.technicals?.rsi_14 ?? Infinity) - (b.technicals?.rsi_14 ?? Infinity));
    else if (sort === 'ret20-desc') sorted.sort((a, b) => (b.technicals?.ret_20d ?? -Infinity) - (a.technicals?.ret_20d ?? -Infinity));
    else if (sort === 'sym-asc') sorted.sort((a, b) => a.ticker.localeCompare(b.ticker));
    else if (sort === 'price-desc') sorted.sort((a, b) => b.current_price - a.current_price);
    return sorted;
  }, [data, q, sector, direction, strength, sort, peMax, roeMin, mcapMin, divMin, deMax,
      rsiMax, rsiMin, aboveSma50, aboveSma200, near52High, ret1mMin, probMin, expRetMin, signalSide]);

  const stats = useMemo(() => ({
    total: filtered.length,
    longs: filtered.filter((p) => p.prediction.direction === 'UP').length,
    shorts: filtered.filter((p) => p.prediction.direction === 'DOWN').length,
    strong: filtered.filter((p) => p.prediction.signal_strength === 'strong').length,
  }), [filtered]);

  const clearFilters = () => {
    setQ(''); setSector('all'); setDirection('all'); setStrength('all');
    setPeMax(''); setRoeMin(''); setMcapMin(''); setDivMin(''); setDeMax('');
    setRsiMax(''); setRsiMin(''); setAboveSma50(false); setAboveSma200(false); setNear52High(''); setRet1mMin('');
    setProbMin(''); setExpRetMin(''); setSignalSide('all');
  };
  const activeFilterCount = [
    q && 'q', sector !== 'all' && 'sec', direction !== 'all' && 'dir', strength !== 'all' && 'str',
    peMax !== '' && 'pe', roeMin !== '' && 'roe', mcapMin !== '' && 'mc', divMin !== '' && 'div', deMax !== '' && 'de',
    rsiMax !== '' && 'rxa', rsiMin !== '' && 'rxi', aboveSma50 && 's50', aboveSma200 && 's200', near52High !== '' && '52h', ret1mMin !== '' && 'r1m',
    probMin !== '' && 'pm', expRetMin !== '' && 'erm', signalSide !== 'all' && 'sig',
  ].filter(Boolean).length;

  // ── Presets & saved screens ───────────────────────────────────────────────--
  const SETTERS = {
    q: setQ, sector: setSector, direction: setDirection, strength: setStrength,
    peMax: setPeMax, roeMin: setRoeMin, mcapMin: setMcapMin, divMin: setDivMin, deMax: setDeMax,
    rsiMax: setRsiMax, rsiMin: setRsiMin, aboveSma50: setAboveSma50, aboveSma200: setAboveSma200,
    near52High: setNear52High, ret1mMin: setRet1mMin,
    probMin: setProbMin, expRetMin: setExpRetMin, signalSide: setSignalSide,
  };
  // Apply a filter set on a clean slate (so a preset/saved screen is exact).
  const applyFilters = (obj) => { clearFilters(); Object.entries(obj || {}).forEach(([k, v]) => SETTERS[k]?.(v)); };
  const currentFilters = () => ({
    q, sector, direction, strength, peMax, roeMin, mcapMin, divMin, deMax,
    rsiMax, rsiMin, aboveSma50, aboveSma200, near52High, ret1mMin, probMin, expRetMin, signalSide,
  });

  const [screenName, setScreenName] = useState('');
  const savedScreens = prefs.savedScreens || [];
  const saveScreen = () => {
    const name = screenName.trim();
    if (!name) return;
    const entry = { id: `${Date.now()}`, name, filters: currentFilters() };
    updatePrefs({ savedScreens: [...savedScreens.filter((s) => s.name !== name), entry] });
    setScreenName('');
    toast.success({ title: 'Screen saved', description: name });
  };
  const deleteScreen = (id) => updatePrefs({ savedScreens: savedScreens.filter((s) => s.id !== id) });

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

      {/* Primary search — funnel icon toggles the advanced filter panel */}
      <motion.div {...fadeUp} className="flex justify-center sm:justify-start py-1">
        <AnimatedGlowingSearchBar
          value={q}
          onChange={(e) => setQ(e.target.value)}
          onFilterClick={() => setShowFilters((x) => !x)}
          placeholder="Search ticker, company, sector…"
          aria-label="Search stocks"
        />
      </motion.div>

      {/* Presets & saved screens */}
      <motion.div {...fadeUp}>
        <Card>
          <div className="p-3 flex flex-col gap-3">
            <div className="flex items-center gap-2 flex-wrap">
              <span className="eyebrow mr-1">Presets</span>
              {PRESETS.map((ps) => (
                <button
                  key={ps.id}
                  onClick={() => applyFilters(ps.f)}
                  className="px-2.5 h-7 rounded-lg border border-line-muted bg-bg-1 text-xs font-medium text-ink-2 hover:bg-bg-2 hover:text-ink-1 hover:border-line-strong transition-colors"
                >{ps.label}</button>
              ))}
            </div>
            <div className="hairline" />
            <div className="flex items-center gap-2 flex-wrap">
              <span className="eyebrow mr-1">Saved</span>
              {savedScreens.length === 0 && <span className="text-2xs text-ink-5">No saved screens yet</span>}
              {savedScreens.map((s) => (
                <span key={s.id} className="inline-flex items-center gap-1 pl-2.5 pr-1 h-7 rounded-lg border border-line-muted bg-bg-1 text-xs text-ink-2">
                  <button onClick={() => applyFilters(s.filters)} className="hover:text-ink-1 transition-colors max-w-[140px] truncate">{s.name}</button>
                  <button onClick={() => deleteScreen(s.id)} className="w-5 h-5 grid place-items-center rounded text-ink-5 hover:text-bear hover:bg-bg-3 transition-colors" aria-label={`Delete ${s.name}`}>×</button>
                </span>
              ))}
              <div className="ml-auto flex items-center gap-2">
                <Input
                  value={screenName}
                  onChange={(e) => setScreenName(e.target.value)}
                  onKeyDown={(e) => { if (e.key === 'Enter') saveScreen(); }}
                  placeholder="Name this screen…"
                  className="w-44"
                />
                <Button size="sm" variant="surface" disabled={!screenName.trim()} onClick={saveScreen}>Save current</Button>
              </div>
            </div>
          </div>
        </Card>
      </motion.div>

      {/* Filters */}
      {showFilters && (
        <motion.div {...fadeUp}>
          <Card>
            <div className="p-4 grid grid-cols-1 md:grid-cols-3 gap-3 items-end">
              <div>
                <label className="eyebrow block mb-1.5">Sector</label>
                <Select value={sector} onChange={(e) => setSector(e.target.value)}>
                  <option value="all">All sectors</option>
                  {SECTORS.map((s) => <option key={s} value={s}>{s}</option>)}
                </Select>
              </div>
              <div>
                <label className="eyebrow block mb-1.5">Direction</label>
                <Select value={direction} onChange={(e) => setDirection(e.target.value)}>
                  {DIRECTIONS.map((d) => <option key={d.value} value={d.value}>{d.label}</option>)}
                </Select>
              </div>
              <div>
                <label className="eyebrow block mb-1.5">Strength</label>
                <Select value={strength} onChange={(e) => setStrength(e.target.value)}>
                  {STRENGTHS.map((d) => <option key={d.value} value={d.value}>{d.label}</option>)}
                </Select>
              </div>
            </div>

            {/* Fundamental filters */}
            <div className="px-4 pb-4">
              <div className="eyebrow mb-2 text-ink-5">Fundamentals</div>
              <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-3 items-end">
                <div>
                  <label className="eyebrow block mb-1.5">P/E ≤</label>
                  <Input type="number" inputMode="decimal" value={peMax} onChange={(e) => setPeMax(e.target.value)} placeholder="e.g. 25" />
                </div>
                <div>
                  <label className="eyebrow block mb-1.5">ROE ≥ (%)</label>
                  <Input type="number" inputMode="decimal" value={roeMin} onChange={(e) => setRoeMin(e.target.value)} placeholder="e.g. 15" />
                </div>
                <div>
                  <label className="eyebrow block mb-1.5">Mkt cap ≥ (₹ Cr)</label>
                  <Input type="number" inputMode="decimal" value={mcapMin} onChange={(e) => setMcapMin(e.target.value)} placeholder="e.g. 50000" />
                </div>
                <div>
                  <label className="eyebrow block mb-1.5">Div yield ≥ (%)</label>
                  <Input type="number" inputMode="decimal" value={divMin} onChange={(e) => setDivMin(e.target.value)} placeholder="e.g. 1" />
                </div>
                <div>
                  <label className="eyebrow block mb-1.5">D/E ≤</label>
                  <Input type="number" inputMode="decimal" value={deMax} onChange={(e) => setDeMax(e.target.value)} placeholder="e.g. 1" />
                </div>
              </div>
            </div>

            {/* Technical filters */}
            <div className="px-4 pb-4">
              <div className="eyebrow mb-2 text-ink-5">Technicals</div>
              <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-3 items-end">
                <div>
                  <label className="eyebrow block mb-1.5">RSI ≥</label>
                  <Input type="number" inputMode="decimal" value={rsiMin} onChange={(e) => setRsiMin(e.target.value)} placeholder="e.g. 50" />
                </div>
                <div>
                  <label className="eyebrow block mb-1.5">RSI ≤</label>
                  <Input type="number" inputMode="decimal" value={rsiMax} onChange={(e) => setRsiMax(e.target.value)} placeholder="e.g. 30" />
                </div>
                <div>
                  <label className="eyebrow block mb-1.5">≤ % from 52w high</label>
                  <Input type="number" inputMode="decimal" value={near52High} onChange={(e) => setNear52High(e.target.value)} placeholder="e.g. 5" />
                </div>
                <div>
                  <label className="eyebrow block mb-1.5">1M return ≥ (%)</label>
                  <Input type="number" inputMode="decimal" value={ret1mMin} onChange={(e) => setRet1mMin(e.target.value)} placeholder="e.g. 5" />
                </div>
                <button type="button" onClick={() => setAboveSma50((x) => !x)}
                  className={cn('h-9 px-3 rounded-lg border text-xs font-medium transition-colors',
                    aboveSma50 ? 'border-bull/40 bg-bull/10 text-bull' : 'border-line-muted bg-bg-1 text-ink-3 hover:bg-bg-2')}>
                  Above 50-DMA
                </button>
                <button type="button" onClick={() => setAboveSma200((x) => !x)}
                  className={cn('h-9 px-3 rounded-lg border text-xs font-medium transition-colors',
                    aboveSma200 ? 'border-bull/40 bg-bull/10 text-bull' : 'border-line-muted bg-bg-1 text-ink-3 hover:bg-bg-2')}>
                  Above 200-DMA
                </button>
              </div>
            </div>

            {/* Model & signal filters */}
            <div className="px-4 pb-4">
              <div className="eyebrow mb-2 text-ink-5">Model &amp; signal</div>
              <div className="grid grid-cols-2 sm:grid-cols-3 gap-3 items-end">
                <div>
                  <label className="eyebrow block mb-1.5">Prob(up) ≥ (%)</label>
                  <Input type="number" inputMode="decimal" value={probMin} onChange={(e) => setProbMin(e.target.value)} placeholder="e.g. 60" />
                </div>
                <div>
                  <label className="eyebrow block mb-1.5">Exp. return ≥ (%)</label>
                  <Input type="number" inputMode="decimal" value={expRetMin} onChange={(e) => setExpRetMin(e.target.value)} placeholder="e.g. 1" />
                </div>
                <div>
                  <label className="eyebrow block mb-1.5">Cross-sectional pick</label>
                  <Select value={signalSide} onChange={(e) => setSignalSide(e.target.value)}>
                    <option value="all">Any</option>
                    <option value="LONG">Long picks only</option>
                    <option value="SHORT">Short picks only</option>
                  </Select>
                </div>
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
          <div className="overflow-x-auto">
            {/* Header */}
            <div className="grid items-center gap-3 px-4 h-10 border-b border-line-muted bg-bg-2/40 sticky top-0 z-10 text-2xs font-medium tracking-wider uppercase text-ink-4 min-w-[1200px]"
                 style={{ gridTemplateColumns: '28px 1.6fr 1fr 0.8fr 0.9fr 1fr 0.9fr 1fr 0.6fr 0.6fr 0.55fr 80px 32px' }}>
              <span></span>
              <span>Ticker</span>
              <span>Sector</span>
              <span className="text-right">Price</span>
              <span className="text-center">Direction</span>
              <span>Confidence</span>
              <span className="text-right">Exp. Return</span>
              <span className="text-right">Mkt Cap</span>
              <span className="text-right">P/E</span>
              <span className="text-right">ROE</span>
              <span className="text-right">RSI</span>
              <span className="text-right">30d</span>
              <span></span>
            </div>

            {/* Body */}
            <div className="max-h-[calc(100vh-360px)] overflow-y-auto min-w-[1200px]">
              {loading && filtered.length === 0 ? (
                Array.from({ length: 14 }).map((_, i) => (
                  <div key={i} className="grid items-center gap-3 px-4 h-12 border-b border-line-faint"
                       style={{ gridTemplateColumns: '28px 1.6fr 1fr 0.8fr 0.9fr 1fr 0.9fr 1fr 0.6fr 0.6fr 0.55fr 80px 32px' }}>
                    <Skeleton className="w-4 h-4 rounded" />
                    <Skeleton className="h-3 w-32" />
                    <Skeleton className="h-3 w-20" />
                    <Skeleton className="h-3 w-14 ml-auto" />
                    <Skeleton className="h-5 w-16 mx-auto" />
                    <Skeleton className="h-1.5 w-full" />
                    <Skeleton className="h-3 w-12 ml-auto" />
                    <Skeleton className="h-3 w-14 ml-auto" />
                    <Skeleton className="h-3 w-8 ml-auto" />
                    <Skeleton className="h-3 w-8 ml-auto" />
                    <Skeleton className="h-3 w-8 ml-auto" />
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
                      style={{ gridTemplateColumns: '28px 1.6fr 1fr 0.8fr 0.9fr 1fr 0.9fr 1fr 0.6fr 0.6fr 0.55fr 80px 32px' }}
                    >
                      <span className="text-2xs font-mono text-ink-5 tabular">{String(idx + 1).padStart(2, '0')}</span>
                      <div className="flex items-center gap-2.5 min-w-0">
                        <span
                          className="w-8 h-8 grid place-items-center rounded-md bg-bg-2 border border-line-muted text-2xs font-mono font-semibold tabular group-hover:border-line-strong shrink-0"
                          style={{ color }}
                        >{sym.slice(0, 3)}</span>
                        <div className="min-w-0">
                          <div className="text-sm font-semibold text-ink-1 truncate group-hover:text-alpha transition-colors flex items-center gap-1.5">
                            <span className="truncate">{sym}</span>
                            {p.signal && (
                              <span className={cn(
                                'shrink-0 px-1 py-px rounded text-[9px] font-bold tracking-wide',
                                p.signal.side === 'LONG' ? 'bg-bull/15 text-bull' : 'bg-bear/15 text-bear',
                              )}>{p.signal.side}</span>
                            )}
                          </div>
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
                      <div className="text-right text-xs text-ink-2 tabular truncate">{fmtMcap(p.fundamentals?.market_cap_cr)}</div>
                      <div className="text-right text-xs text-ink-2 tabular">{fmtNum(p.fundamentals?.pe, 1)}</div>
                      <div className="text-right text-xs text-ink-2 tabular">{fmtNum(p.fundamentals?.roe, 1)}</div>
                      <div className={cn('text-right text-xs tabular',
                        (p.technicals?.rsi_14 ?? 50) < 30 ? 'text-bull' : (p.technicals?.rsi_14 ?? 50) > 70 ? 'text-bear' : 'text-ink-2')}>
                        {fmtNum(p.technicals?.rsi_14, 0)}
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
