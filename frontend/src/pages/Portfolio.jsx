import React, { useMemo, useState, useCallback } from 'react';
import { useSearchParams } from 'react-router-dom';
import { motion } from 'framer-motion';
import { api } from '../api/client.js';
import { useApp } from '../context/AppContext.jsx';
import { useToast } from '../components/ui/Toast.jsx';
import { UNIVERSE, META_BY_TICKER, SECTOR_COLOR, isValidHorizon } from '../data/universe.js';
import { Card, CardHeader, CardBody } from '../components/ui/Card.jsx';
import { Button, IconButton } from '../components/ui/Button.jsx';
import { Input } from '../components/ui/Input.jsx';
import { Badge, Pill } from '../components/ui/Badge.jsx';
import { SegmentedControl } from '../components/ui/Tabs.jsx';
import { EmptyState } from '../components/ui/Empty.jsx';
import { Skeleton } from '../components/ui/Skeleton.jsx';
import { HorizonSwitcher } from '../components/domain/HorizonSwitcher.jsx';
import { AllocationDonut, AllocationLegend } from '../components/charts/AllocationDonut.jsx';
import {
  IconBriefcase, IconScale, IconTarget, IconArrowRight, IconBolt, IconShield,
  IconRefresh, IconStarFill, IconPlus, IconMinus, IconSearch, IconX,
} from '../components/shell/Icons.jsx';
import { toApiTicker, toDisplayTicker, tickerSymbol, cn } from '../lib/utils.js';

const fadeUp = {
  initial: { opacity: 0, y: 8 },
  animate: { opacity: 1, y: 0 },
  transition: { duration: 0.32, ease: [0.22, 0.61, 0.36, 1] },
};

const RISK_LEVELS = [
  { value: 0.5, label: 'Defensive', tone: 'iris', description: 'Low volatility, stable correlations' },
  { value: 1.0, label: 'Balanced',  tone: 'ink',  description: 'Default Markowitz frontier' },
  { value: 2.0, label: 'Growth',    tone: 'alpha', description: 'Tilt toward high-return picks' },
  { value: 3.5, label: 'Aggressive', tone: 'bear', description: 'Maximize predicted return' },
];

const TickerChip = ({ ticker, onRemove }) => {
  const display = toDisplayTicker(ticker);
  const meta = META_BY_TICKER[display];
  const color = SECTOR_COLOR[meta?.sector] || '#94A3B8';
  return (
    <span className="inline-flex items-center gap-2 h-8 pl-2 pr-1 rounded-md bg-bg-2 border border-line-muted">
      <span className="w-5 h-5 grid place-items-center rounded text-2xs font-mono font-semibold tabular bg-bg-3" style={{ color }}>
        {tickerSymbol(display).slice(0, 3)}
      </span>
      <span className="text-xs font-medium text-ink-1">{tickerSymbol(display)}</span>
      <button
        onClick={() => onRemove(display)}
        className="w-5 h-5 grid place-items-center rounded text-ink-4 hover:text-bear hover:bg-bg-3"
        aria-label="Remove"
      >
        <IconX className="w-3 h-3" />
      </button>
    </span>
  );
};

const Portfolio = () => {
  const { prefs, updatePrefs, watchlist } = useApp();
  const toast = useToast();
  const [params, setParams] = useSearchParams();

  // Horizon: URL ?horizon=... > prefs.horizon > sensible default for allocation (20d)
  const urlHorizon = params.get('horizon');
  const horizon = isValidHorizon(urlHorizon) ? urlHorizon : (prefs.horizon || '20d');
  const setHorizon = useCallback((next) => {
    updatePrefs({ horizon: next });
    const p = new URLSearchParams(params);
    p.delete('horizon');
    setParams(p, { replace: true });
  }, [params, setParams, updatePrefs]);

  const [risk, setRisk] = useState(1.0);

  // Seed tickers: ?ticker=X comma-list > watchlist > default
  const urlTickers = (params.get('tickers') || params.get('ticker') || '')
    .split(',').map((s) => s.trim()).filter(Boolean).filter((t) => META_BY_TICKER[t]);
  const [tickers, setTickers] = useState(() =>
    urlTickers.length ? urlTickers :
    watchlist.length  ? watchlist.slice(0, 6) :
    ['RELIANCE.NS', 'TCS.NS', 'HDFCBANK.NS', 'INFY.NS', 'BHARTIARTL.NS']
  );
  const [q, setQ] = useState('');
  const [result, setResult] = useState(null);
  const [running, setRunning] = useState(false);

  const addable = useMemo(() => {
    const needle = q.trim().toLowerCase();
    return UNIVERSE
      .filter((u) => !tickers.includes(u.ticker))
      .filter((u) => !needle || u.ticker.toLowerCase().includes(needle) || u.name.toLowerCase().includes(needle) || u.sector.toLowerCase().includes(needle))
      .slice(0, 7);
  }, [q, tickers]);

  const runOptimize = async () => {
    if (tickers.length < 2) {
      toast.warn({ title: 'Pick at least 2 tickers', description: 'Diversification requires a minimum of two assets.' });
      return;
    }
    setRunning(true);
    try {
      const res = await api.optimize({
        tickers: tickers.map(toApiTicker),
        horizon,
        risk_tolerance: risk,
      });
      setResult(res);
      toast.success({ title: 'Portfolio optimized', description: `${tickers.length} assets · risk ${risk.toFixed(1)} · horizon ${horizon}` });
    } catch (e) {
      toast.error({ title: 'Optimization failed', description: e?.message || 'Backend unreachable' });
    } finally {
      setRunning(false);
    }
  };

  const sectorBreakdown = useMemo(() => {
    if (!result?.allocations) return [];
    const map = new Map();
    for (const [t, w] of Object.entries(result.allocations)) {
      const sec = META_BY_TICKER[toDisplayTicker(t)]?.sector || '—';
      map.set(sec, (map.get(sec) || 0) + w);
    }
    return [...map.entries()].sort((a, b) => b[1] - a[1]);
  }, [result]);

  const totalCount = tickers.length;
  const largest = result?.allocations
    ? Object.entries(result.allocations).sort((a, b) => b[1] - a[1])[0]
    : null;

  return (
    <div className="space-y-5 pb-12">
      <motion.div {...fadeUp}>
        <Card glow="iris">
          <div className="px-6 py-5 flex items-center justify-between gap-4 flex-wrap">
            <div className="flex items-center gap-4">
              <span className="w-12 h-12 grid place-items-center rounded-xl bg-bg-2 border border-line-muted text-iris-soft">
                <IconScale className="w-5 h-5" />
              </span>
              <div>
                <div className="eyebrow">Quant Allocation</div>
                <h2 className="font-display font-bold text-2xl text-ink-1 leading-tight">Portfolio Optimizer</h2>
                <p className="text-xs text-ink-3 mt-0.5 max-w-md">Markowitz efficient frontier · dynamic covariance · forecast-driven expected returns.</p>
              </div>
            </div>
            <div className="flex items-center gap-3">
              <Badge tone="alpha" dot size="sm">{totalCount} assets selected</Badge>
              <Button
                size="lg"
                variant="primary"
                loading={running}
                leadingIcon={IconBolt}
                onClick={runOptimize}
              >
                {result ? 'Re-optimize' : 'Run optimization'}
              </Button>
            </div>
          </div>
        </Card>
      </motion.div>

      {/* Configuration row */}
      <motion.div {...fadeUp} className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        <Card className="lg:col-span-2">
          <CardHeader eyebrow="Step 1 · Universe" title="Select tickers" subtitle={`Pull from your watchlist or search the NIFTY 50 (${tickers.length}/15)`} />
          <CardBody>
            <div className="flex flex-wrap gap-2 mb-3">
              {tickers.length === 0
                ? <div className="text-xs text-ink-4">No tickers selected.</div>
                : tickers.map((t) => <TickerChip key={t} ticker={t} onRemove={(x) => setTickers((xs) => xs.filter((y) => y !== x))} />)}
            </div>
            <div className="hairline mb-3" />
            <Input
              value={q}
              onChange={(e) => setQ(e.target.value)}
              placeholder="Search to add (e.g. RELIANCE, IT, Bank…)"
              leadingIcon={IconSearch}
            />
            {q && (
              <ul className="mt-2 border border-line-faint rounded-lg bg-bg-1 max-h-48 overflow-y-auto divide-y divide-line-faint">
                {addable.length === 0 ? (
                  <li className="px-3 py-2 text-xs text-ink-4 italic">No matches</li>
                ) : addable.map((u) => (
                  <li key={u.ticker}>
                    <button
                      onClick={() => { setTickers((xs) => xs.length < 15 ? [...xs, u.ticker] : xs); setQ(''); }}
                      className="w-full flex items-center gap-3 px-3 py-2 hover:bg-bg-2 transition-colors text-left"
                    >
                      <span className="w-7 h-7 grid place-items-center rounded-md bg-bg-2 border border-line-muted text-2xs font-mono font-semibold tabular" style={{ color: SECTOR_COLOR[u.sector] }}>
                        {tickerSymbol(u.ticker).slice(0, 3)}
                      </span>
                      <div className="flex-1 min-w-0">
                        <div className="text-sm font-medium text-ink-1 truncate">{tickerSymbol(u.ticker)}</div>
                        <div className="text-2xs text-ink-4 truncate">{u.name} · {u.sector}</div>
                      </div>
                      <IconPlus className="w-3.5 h-3.5 text-ink-4" />
                    </button>
                  </li>
                ))}
              </ul>
            )}

            <div className="flex items-center gap-2 mt-3">
              {watchlist.length > 0 && (
                <Button size="xs" variant="ghost" leadingIcon={IconStarFill} onClick={() => setTickers(watchlist.slice(0, 12))}>
                  Use watchlist ({watchlist.length})
                </Button>
              )}
              {tickers.length > 0 && (
                <Button size="xs" variant="ghost" leadingIcon={IconMinus} onClick={() => setTickers([])}>Clear all</Button>
              )}
            </div>
          </CardBody>
        </Card>

        <Card>
          <CardHeader eyebrow="Step 2 · Risk" title="Set risk tolerance" subtitle="Higher = chase return. Lower = chase stability." />
          <CardBody>
            <div className="flex flex-col gap-3">
              <SegmentedControl
                size="sm"
                value={(() => {
                  const closest = RISK_LEVELS.reduce((a, b) => Math.abs(b.value - risk) < Math.abs(a.value - risk) ? b : a, RISK_LEVELS[0]);
                  return closest.value;
                })()}
                onChange={(v) => setRisk(v)}
                options={RISK_LEVELS.map((l) => ({ value: l.value, label: l.label }))}
              />

              <div className="flex items-center gap-3">
                <span className="text-2xs text-ink-4 w-8 text-right tabular">0.1</span>
                <input
                  type="range"
                  min="0.1" max="5" step="0.1"
                  value={risk}
                  onChange={(e) => setRisk(parseFloat(e.target.value))}
                  className="flex-1 accent-alpha h-1 cursor-pointer"
                  style={{ accentColor: '#F4C45D' }}
                />
                <span className="text-2xs text-ink-4 w-8 tabular">5.0</span>
              </div>

              <div className="flex items-baseline gap-2">
                <div className="font-display font-bold text-3xl text-alpha tabular">{risk.toFixed(1)}</div>
                <div className="text-xs text-ink-4">risk multiplier</div>
              </div>

              <div className="hairline my-1" />

              <div>
                <div className="eyebrow mb-1.5">Horizon</div>
                <HorizonSwitcher value={horizon} onChange={setHorizon} />
              </div>

              <p className="text-2xs text-ink-4 leading-relaxed mt-1">
                {RISK_LEVELS.reduce((a, b) => Math.abs(b.value - risk) < Math.abs(a.value - risk) ? b : a, RISK_LEVELS[0]).description}. Built on mean-variance optimization with dynamic conditional covariance.
              </p>
            </div>
          </CardBody>
        </Card>
      </motion.div>

      {/* Result panel */}
      <motion.div {...fadeUp}>
        <Card>
          <CardHeader
            eyebrow="Step 3 · Output"
            title={result ? 'Optimized Allocation' : 'Run optimization to view allocation'}
            subtitle={result ? `Horizon ${result.horizon} · Risk multiplier ${result.risk_tolerance.toFixed(1)}` : 'Pick tickers, set risk, then click run.'}
            action={
              result && (
                <Button size="sm" variant="ghost" leadingIcon={IconRefresh} onClick={runOptimize}>Re-optimize</Button>
              )
            }
          />
          <CardBody>
            {running ? (
              <div className="grid grid-cols-1 lg:grid-cols-2 gap-4 items-center">
                <Skeleton className="h-[260px] w-full" />
                <Skeleton className="h-[260px] w-full" />
              </div>
            ) : !result ? (
              <EmptyState
                icon={IconBriefcase}
                title="No optimization yet"
                description="Pick tickers, choose a risk level, then run. You'll get a full allocation breakdown with a written summary."
                action={<Button size="sm" variant="primary" leadingIcon={IconBolt} onClick={runOptimize}>Run optimization</Button>}
              />
            ) : (
              <div className="grid grid-cols-1 lg:grid-cols-5 gap-6 items-start">
                <div className="lg:col-span-2">
                  <AllocationDonut allocations={result.allocations} height={300} />
                </div>
                <div className="lg:col-span-2">
                  <div className="eyebrow mb-2">Per-asset weighting</div>
                  <AllocationLegend allocations={result.allocations} />
                </div>
                <div className="lg:col-span-1">
                  <div className="eyebrow mb-2">Sector breakdown</div>
                  <ul className="space-y-2">
                    {sectorBreakdown.map(([sec, w]) => (
                      <li key={sec} className="flex items-center gap-2">
                        <span className="w-2.5 h-2.5 rounded-sm shrink-0" style={{ background: SECTOR_COLOR[sec] || '#94A3B8' }} />
                        <span className="text-xs text-ink-2 truncate flex-1">{sec}</span>
                        <span className="text-xs font-semibold text-ink-1 tabular">{(w * 100).toFixed(1)}%</span>
                      </li>
                    ))}
                  </ul>

                  <div className="hairline my-4" />
                  <div className="eyebrow mb-1.5">Concentration</div>
                  {largest && (
                    <div className="text-xs text-ink-2">
                      Largest position: <span className="text-ink-1 font-semibold">{tickerSymbol(toDisplayTicker(largest[0]))}</span> at <span className="text-alpha font-semibold tabular">{(largest[1] * 100).toFixed(1)}%</span>
                    </div>
                  )}
                </div>
              </div>
            )}

            {result && (
              <>
                <div className="hairline my-5" />
                <div className="flex items-start gap-3">
                  <span className="w-8 h-8 grid place-items-center rounded-md bg-iris/10 text-iris border border-iris/25 shrink-0">
                    <IconShield className="w-4 h-4" />
                  </span>
                  <div className="flex-1">
                    <div className="eyebrow mb-1">Allocation Summary</div>
                    <p className="text-sm text-ink-2 leading-relaxed">{result.summary}</p>
                  </div>
                </div>
              </>
            )}
          </CardBody>
        </Card>
      </motion.div>
    </div>
  );
};

export default Portfolio;
