import React, { useMemo, useState, useCallback } from 'react';
import { useSearchParams, Link } from 'react-router-dom';
import { motion } from 'framer-motion';
import { useApi } from '../hooks/useApi.js';
import { api } from '../api/client.js';
import { useApp } from '../context/AppContext.jsx';
import {
  UNIVERSE, META_BY_TICKER, SECTOR_COLOR,
  HORIZONS, horizonDays, horizonLabel, isValidHorizon, DEFAULT_HORIZON,
} from '../data/universe.js';
import { Card, CardHeader, CardBody } from '../components/ui/Card.jsx';
import { Button } from '../components/ui/Button.jsx';
import { Select } from '../components/ui/Input.jsx';
import { Badge } from '../components/ui/Badge.jsx';
import { SegmentedControl, Tabs } from '../components/ui/Tabs.jsx';
import { EmptyState } from '../components/ui/Empty.jsx';
import { Skeleton } from '../components/ui/Skeleton.jsx';
import { Counter } from '../components/ui/Counter.jsx';
import { Tooltip } from '../components/ui/Tooltip.jsx';
import { HorizonSwitcher } from '../components/domain/HorizonSwitcher.jsx';
import { DirectionPill, ConfidenceMeter } from '../components/domain/DirectionPill.jsx';
import { ShapBars } from '../components/domain/ShapBars.jsx';
import { AreaChart } from '../components/charts/AreaChart.jsx';
import {
  ComposedChart, Area, Line, ReferenceLine, ReferenceDot,
  XAxis, YAxis, Tooltip as RTooltip, ResponsiveContainer,
} from 'recharts';
import {
  IconStar, IconStarFill, IconBrain, IconTarget, IconWaveform,
  IconArrowRight, IconRefresh, IconInfo,
} from '../components/shell/Icons.jsx';
import {
  toApiTicker, tickerSymbol, fmtPrice, cn,
} from '../lib/utils.js';

const fadeUp = {
  initial: { opacity: 0, y: 8 },
  animate: { opacity: 1, y: 0 },
  transition: { duration: 0.32, ease: [0.22, 0.61, 0.36, 1] },
};

const HISTORY_RANGES = [
  { value: 30,  label: '1M' },
  { value: 60,  label: '3M' },
  { value: 120, label: '6M' },
  { value: 252, label: '1Y' },
];

const ConfidenceBracket = ({ lower, upper, predicted }) => {
  const min = Math.min(lower, predicted, 0) - 0.005;
  const max = Math.max(upper, predicted, 0) + 0.005;
  const range = max - min;
  const pctOf = (v) => ((v - min) / range) * 100;
  return (
    <div className="relative h-9 w-full" role="img" aria-label={`Confidence interval ${(lower * 100).toFixed(2)}% to ${(upper * 100).toFixed(2)}% with predicted ${(predicted * 100).toFixed(2)}%`}>
      <div className="absolute inset-y-1/2 -translate-y-px left-0 right-0 h-px bg-line-muted" />
      <div className="absolute inset-y-1/2 -translate-y-px h-px bg-alpha"
           style={{ left: `${pctOf(lower)}%`, right: `${100 - pctOf(upper)}%` }} />
      <div className="absolute top-1/2 -translate-y-1/2 h-3 w-px bg-line-strong" style={{ left: `${pctOf(lower)}%` }} />
      <div className="absolute top-1/2 -translate-y-1/2 h-3 w-px bg-line-strong" style={{ left: `${pctOf(upper)}%` }} />
      <div className="absolute top-1/2 -translate-y-1/2 h-4 w-px bg-ink-5"
           style={{ left: `${pctOf(0)}%` }} title="Zero return baseline" />
      <div className="absolute top-1/2 -translate-x-1/2 -translate-y-1/2 w-3 h-3 rounded-full bg-alpha shadow-glow-alpha"
           style={{ left: `${pctOf(predicted)}%` }} />
      <div className="absolute bottom-0 left-0 text-2xs text-ink-5 tabular">{(lower * 100).toFixed(2)}%</div>
      <div className="absolute bottom-0 right-0 text-2xs text-ink-5 tabular">{(upper * 100).toFixed(2)}%</div>
    </div>
  );
};

// ── URL-driven primitives (single source of truth: searchParams) ─────────────
const useUrlTicker = (params, setParams, fallback) => {
  const raw = params.get('ticker') || fallback;
  const display = META_BY_TICKER[raw] ? raw : fallback;
  const set = useCallback((next) => {
    const p = new URLSearchParams(params);
    p.set('ticker', next);
    setParams(p, { replace: true });
  }, [params, setParams]);
  return [display, set];
};

const Analysis = () => {
  const [params, setParams] = useSearchParams();
  const { prefs, updatePrefs, isWatched, toggleWatchlist } = useApp();

  const [display, setDisplay] = useUrlTicker(params, setParams, 'RELIANCE.NS');

  // Horizon: URL ?horizon=... > prefs.horizon > default
  const urlHorizon = params.get('horizon');
  const horizon = isValidHorizon(urlHorizon) ? urlHorizon : prefs.horizon;
  const setHorizon = useCallback((next) => {
    updatePrefs({ horizon: next });
    const p = new URLSearchParams(params);
    p.delete('horizon');           // URL override clears once user picks new global default
    setParams(p, { replace: true });
  }, [params, setParams, updatePrefs]);

  // Model is selected internally; clients see insights, not implementation.
  const model = prefs.model || 'ensemble_clf';

  const [range, setRange] = useState(120);
  const [tab, setTab] = useState('thesis');

  const apiTicker = useMemo(() => toApiTicker(display), [display]);
  const meta = META_BY_TICKER[display];

  const { data: pred, loading: pLoading, refetch: pRefetch } = useApi(
    () => api.predict({ ticker: apiTicker, horizon, model }),
    [apiTicker, horizon, model],
  );
  const { data: explain, loading: eLoading } = useApi(
    () => api.explain({ ticker: apiTicker, horizon, top_n: 12 }),
    [apiTicker, horizon],
  );
  const { data: hist, loading: hLoading } = useApi(
    () => api.history(apiTicker, range),
    [apiTicker, range],
  );
  const { data: sim, loading: sLoading } = useApi(
    () => api.simulate({ ticker: apiTicker, horizon }),
    [apiTicker, horizon],
    { enabled: tab === 'risk' },
  );

  const watched = isWatched(display);
  const sectorColor = SECTOR_COLOR[meta?.sector] || '#94A3B8';

  // Split historical series from the projected target point.
  // Realized: hist.history (rendered as solid area).
  // Projected: a 2-point segment from the last actual close to the target
  //            placed `horizonDays(horizon)` days ahead (rendered separately).
  const { realized, projected, baselinePrice, targetPrice } = useMemo(() => {
    if (!hist?.history?.length) return { realized: [], projected: [], baselinePrice: null, targetPrice: null };
    const series = hist.history;
    const lastIdx = series.length - 1;
    const last = series[lastIdx];
    if (!pred) return { realized: series, projected: [], baselinePrice: last.price, targetPrice: null };
    const days = horizonDays(horizon);
    const targetPrice = last.price * (1 + pred.prediction.predicted_return);
    const tDate = new Date(last.date);
    tDate.setDate(tDate.getDate() + days);
    const targetDate = tDate.toISOString().slice(0, 10);
    return {
      realized: series,
      projected: [
        { date: last.date,   price: last.price,   projected: true },
        { date: targetDate,  price: targetPrice,  projected: true },
      ],
      baselinePrice: last.price,
      targetPrice,
    };
  }, [hist, pred, horizon]);

  // Counter cache keys keep the displayed number across horizon swaps —
  // so it animates from the previous shown figure, not from zero.
  const ck = (k) => `analysis:${apiTicker}:${k}`;

  return (
    <div className="space-y-5 pb-12">
      {/* Toolbar */}
      <motion.div {...fadeUp} className="flex items-center justify-between gap-4 flex-wrap">
        <div className="flex items-center gap-3 flex-wrap">
          <Select
            size="md"
            value={display}
            onChange={(e) => setDisplay(e.target.value)}
            className="min-w-[240px] font-medium"
            aria-label="Select ticker"
          >
            {UNIVERSE.map((u) => (
              <option key={u.ticker} value={u.ticker}>{tickerSymbol(u.ticker)} · {u.name}</option>
            ))}
          </Select>
          <span className="hairline-v h-6 hidden md:block" />
          <span className="eyebrow">Horizon</span>
          <HorizonSwitcher value={horizon} onChange={setHorizon} />
        </div>
        <div className="flex items-center gap-2">
          <Button size="sm" variant="ghost" leadingIcon={IconRefresh} onClick={pRefetch}>Refresh</Button>
          <Button
            size="sm"
            variant={watched ? 'primary' : 'surface'}
            leadingIcon={watched ? IconStarFill : IconStar}
            onClick={() => toggleWatchlist(display)}
            aria-pressed={watched}
          >
            {watched ? 'Watching' : 'Watch'}
          </Button>
        </div>
      </motion.div>

      {/* Identity strip */}
      <motion.div {...fadeUp}>
        <Card glow={pred?.prediction.direction === 'UP' ? 'alpha' : null}>
          <div className="px-6 py-5 flex items-center gap-5 flex-wrap">
            <div
              className="w-14 h-14 grid place-items-center rounded-xl bg-bg-2 border border-line-muted text-md font-mono font-bold tabular shrink-0"
              style={{ color: sectorColor }}
              aria-hidden="true"
            >
              {tickerSymbol(display).slice(0, 3)}
            </div>
            <div className="min-w-0 flex-1">
              <div className="flex items-center gap-2 flex-wrap">
                <h2 className="font-display font-bold text-2xl text-ink-1">{tickerSymbol(display)}</h2>
                <span className="text-md text-ink-3">·</span>
                <span className="text-md text-ink-2 truncate">{pred?.company_name || meta?.name}</span>
                {pred?.regime && <Badge tone="iris" size="sm" dot>Regime: {pred.regime}</Badge>}
              </div>
              <div className="flex items-center gap-3 mt-1 text-xs text-ink-4 flex-wrap">
                <span>{meta?.sector}</span>
                <span aria-hidden="true">·</span>
                <span>{meta?.industry}</span>
                {meta?.weight && (<><span aria-hidden="true">·</span><span>NIFTY weight {meta.weight.toFixed(2)}%</span></>)}
              </div>
            </div>
            <div className="flex items-baseline gap-2 shrink-0">
              <span className="font-display font-bold text-3xl text-ink-1 tabular">
                {pred ? fmtPrice(pred.current_price, { dp: 2 }) : '—'}
              </span>
              <span className="text-xs text-ink-4">Last close</span>
            </div>
          </div>

          {/* Forecast metrics row */}
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-px bg-line-faint border-t border-line-faint">
            <div className="bg-bg-1 px-6 py-4">
              <div className="eyebrow mb-2">Direction</div>
              {pLoading ? <Skeleton className="h-7 w-24" /> : (
                <DirectionPill direction={pred?.prediction.direction} probability={pred?.prediction.probability} size="lg" />
              )}
              <div className="text-2xs text-ink-4 mt-1.5 capitalize">
                Signal strength: <span className="text-ink-2">{pred?.prediction.signal_strength || '—'}</span>
              </div>
            </div>
            <div className="bg-bg-1 px-6 py-4">
              <div className="eyebrow mb-2 flex items-center gap-1.5">
                Expected Return <span className="text-ink-5">·</span>
                <span className="text-ink-2">{horizonLabel(horizon)}</span>
                <Tooltip content={`Predicted total return over the next ${horizonDays(horizon)} trading day${horizonDays(horizon) === 1 ? '' : 's'}.`}>
                  <IconInfo className="w-3 h-3 text-ink-5 cursor-help" />
                </Tooltip>
              </div>
              {pLoading ? <Skeleton className="h-7 w-24" /> : (
                <div className={cn(
                  'font-display font-bold text-2xl tabular',
                  pred?.prediction.predicted_return >= 0 ? 'text-bull' : 'text-bear',
                )}>
                  {pred?.prediction.predicted_return >= 0 ? '+' : ''}
                  <Counter
                    value={(pred?.prediction.predicted_return || 0) * 100}
                    decimals={2}
                    cacheKey={ck('ret')}
                  />%
                </div>
              )}
              <div className="text-2xs text-ink-4 mt-1.5">Total return over the horizon</div>
            </div>
            <div className="bg-bg-1 px-6 py-4">
              <div className="eyebrow mb-2">Probability of UP</div>
              {pLoading ? <Skeleton className="h-7 w-24" /> : (
                <>
                  <div className="font-display font-bold text-2xl text-ink-1 tabular">
                    <Counter
                      value={(pred?.prediction.probability || 0) * 100}
                      decimals={1}
                      cacheKey={ck('prob')}
                    />%
                  </div>
                  <ConfidenceMeter probability={pred?.prediction.probability} className="mt-2" />
                </>
              )}
            </div>
            <div className="bg-bg-1 px-6 py-4">
              <div className="eyebrow mb-2 flex items-center gap-1.5">
                Confidence Interval
                <Tooltip content="Range of plausible returns. Bracket width grows with model uncertainty.">
                  <IconInfo className="w-3 h-3 text-ink-5 cursor-help" />
                </Tooltip>
              </div>
              {pLoading || !pred ? <Skeleton className="h-9 w-full" /> : (
                <ConfidenceBracket
                  lower={pred.prediction.confidence_lower}
                  upper={pred.prediction.confidence_upper}
                  predicted={pred.prediction.predicted_return}
                />
              )}
            </div>
          </div>
        </Card>
      </motion.div>

      {/* Tabs */}
      <motion.div {...fadeUp}>
        <Tabs
          value={tab}
          onChange={setTab}
          tabs={[
            { value: 'thesis',  label: 'Forecast Thesis', icon: IconWaveform },
            { value: 'drivers', label: 'Key Drivers',     icon: IconBrain },
            { value: 'risk',    label: 'Risk · Monte Carlo', icon: IconTarget },
            { value: 'price',   label: 'Price History',   icon: IconTarget },
          ]}
        />
      </motion.div>

      {/* Body */}
      <motion.div key={tab} {...fadeUp} className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        {tab === 'thesis' && (
          <>
            <Card className="lg:col-span-2">
              <CardHeader
                eyebrow="Price · Forecast Projection"
                title={`${horizonLabel(horizon)} forward target`}
                subtitle={pred
                  ? `Model projects ${pred.prediction.direction === 'UP' ? 'upside' : 'downside'} of ${(pred.prediction.predicted_return * 100).toFixed(2)}% over the next ${horizonDays(horizon)} trading day${horizonDays(horizon) === 1 ? '' : 's'}.`
                  : ''}
                action={
                  <SegmentedControl
                    size="sm"
                    value={range}
                    onChange={setRange}
                    options={HISTORY_RANGES}
                  />
                }
              />
              <CardBody className="pt-2">
                {hLoading ? <Skeleton className="h-[260px] w-full" /> : realized.length ? (
                  <ForecastChart
                    realized={realized}
                    projected={projected}
                    baseline={baselinePrice}
                    target={targetPrice}
                    direction={pred?.prediction.direction}
                  />
                ) : (
                  <EmptyState title="No history" description="Could not load historical prices." />
                )}
                {pred && (
                  <div className="flex items-center justify-between mt-3 px-1 flex-wrap gap-y-2">
                    <div className="text-2xs text-ink-5">
                      Forecast valid for next {horizonLabel(horizon)} · Generated {new Date(pred.last_updated).toLocaleTimeString('en-IN')}
                    </div>
                    <div className="flex items-center gap-4 text-2xs">
                      <span className="inline-flex items-center gap-1.5">
                        <span className="w-3 h-0.5 rounded" style={{ background: pred.prediction.direction === 'UP' ? '#10B981' : '#F43F5E' }} />
                        <span className="text-ink-3">Realized</span>
                      </span>
                      <span className="inline-flex items-center gap-1.5">
                        <span className="inline-block w-3 h-0.5 rounded border-t border-dashed" style={{ borderColor: '#F4C45D' }} />
                        <span className="text-ink-3">Projected</span>
                      </span>
                      <span className="inline-flex items-center gap-1.5">
                        <span className="w-2 h-2 rounded-full bg-alpha shadow-glow-alpha" />
                        <span className="text-ink-3">Target {targetPrice ? `· ${fmtPrice(targetPrice, { dp: 0 })}` : ''}</span>
                      </span>
                    </div>
                  </div>
                )}
              </CardBody>
            </Card>

            <Card>
              <CardHeader eyebrow="In Plain English" title="Forecast Thesis" />
              <CardBody>
                {eLoading ? <Skeleton className="h-20 w-full" /> : (
                  <p className="text-sm text-ink-2 leading-relaxed">
                    {explain?.interpretation || 'Run prediction to see explanation.'}
                  </p>
                )}
                <div className="hairline my-4" />
                <div className="grid grid-cols-2 gap-3">
                  <div>
                    <div className="eyebrow mb-1">Lower bound</div>
                    <div className={cn(
                      'font-display font-semibold text-md tabular',
                      pred && pred.prediction.confidence_lower >= 0 ? 'text-bull' : 'text-bear',
                    )}>
                      {pred ? `${pred.prediction.confidence_lower >= 0 ? '+' : ''}${(pred.prediction.confidence_lower * 100).toFixed(2)}%` : '—'}
                    </div>
                  </div>
                  <div>
                    <div className="eyebrow mb-1">Upper bound</div>
                    <div className={cn(
                      'font-display font-semibold text-md tabular',
                      pred && pred.prediction.confidence_upper >= 0 ? 'text-bull' : 'text-bear',
                    )}>
                      {pred ? `${pred.prediction.confidence_upper >= 0 ? '+' : ''}${(pred.prediction.confidence_upper * 100).toFixed(2)}%` : '—'}
                    </div>
                  </div>
                </div>
                <div className="hairline my-4" />
                <div className="flex flex-col gap-2">
                  <Link to={`/portfolio?ticker=${encodeURIComponent(display)}&horizon=${horizon}`}>
                    <Button variant="iris" trailingIcon={IconArrowRight} className="w-full">Size with Portfolio Optimizer</Button>
                  </Link>
                  <Link to={`/backtest?ticker=${encodeURIComponent(display)}&horizon=${horizon}`}>
                    <Button variant="surface" trailingIcon={IconArrowRight} className="w-full">Validate via backtest</Button>
                  </Link>
                </div>
              </CardBody>
            </Card>
          </>
        )}

        {tab === 'drivers' && (
          <>
            <Card className="lg:col-span-2">
              <CardHeader
                eyebrow="Factor Attribution"
                title="What's driving this forecast"
                subtitle="The factors contributing most to this signal, ranked by impact"
                action={<Badge tone="alpha" size="sm">Top {explain?.top_features?.length || 12}</Badge>}
              />
              <CardBody>
                {eLoading ? (
                  <div className="space-y-2">
                    {Array.from({ length: 10 }).map((_, i) => <Skeleton key={i} className="h-5 w-full" />)}
                  </div>
                ) : (
                  <ShapBars features={explain?.top_features || []} />
                )}
              </CardBody>
            </Card>

            <Card>
              <CardHeader eyebrow="How to Read" title="Reading the drivers" />
              <CardBody>
                <ul className="space-y-3 text-xs text-ink-2">
                  <li className="flex gap-3">
                    <span className="w-1 h-12 rounded-full bg-bull shrink-0" />
                    <span><strong className="text-ink-1">Green bars</strong> push the forecast toward UP. Larger = stronger contribution.</span>
                  </li>
                  <li className="flex gap-3">
                    <span className="w-1 h-12 rounded-full bg-bear shrink-0" />
                    <span><strong className="text-ink-1">Red bars</strong> pull the forecast toward DOWN.</span>
                  </li>
                  <li className="flex gap-3 text-ink-3">
                    <span className="w-1 h-12 rounded-full bg-ink-4 shrink-0" />
                    <span>Each bar's length is that factor's marginal contribution — a fair, additive attribution.</span>
                  </li>
                </ul>
                <div className="hairline my-4" />
                <p className="text-xs text-ink-3 leading-relaxed">
                  <span className="text-ink-1 font-semibold">Why this matters: </span>
                  Transparency is essential in finance. Factor attribution lets you sanity-check every forecast — if a technology stock's signal is driven by a crude-oil factor, you'll see it and can judge accordingly.
                </p>
              </CardBody>
            </Card>
          </>
        )}

        {tab === 'risk' && (
          <>
            <Card className="lg:col-span-2">
              <CardHeader
                eyebrow="Merton Jump-Diffusion · Monte Carlo"
                title={`Simulated price cone · ${horizonLabel(horizon)}`}
                subtitle={sim
                  ? `${(sim.n_sims || 0).toLocaleString()} paths · ${sim.n_jumps_history ?? 0} historical jumps calibrated · centered on the model forecast`
                  : 'Thousands of jump-diffusion paths around the model forecast'}
              />
              <CardBody className="pt-2">
                {sLoading || !sim?.fan ? <Skeleton className="h-[300px] w-full" /> : (
                  <FanChart fan={sim.fan} S0={sim.current_price} />
                )}
                {sim && (
                  <div className="flex items-center gap-4 text-2xs mt-3 px-1 flex-wrap">
                    <span className="inline-flex items-center gap-1.5"><span className="w-3 h-2 rounded-sm bg-alpha/15 border border-alpha/30" /><span className="text-ink-3">90% range (p5–p95)</span></span>
                    <span className="inline-flex items-center gap-1.5"><span className="w-3 h-2 rounded-sm bg-alpha/30" /><span className="text-ink-3">Interquartile (p25–p75)</span></span>
                    <span className="inline-flex items-center gap-1.5"><span className="w-3 h-0.5 rounded bg-alpha" /><span className="text-ink-3">Median path</span></span>
                  </div>
                )}
              </CardBody>
            </Card>

            <Card>
              <CardHeader eyebrow="Tail Risk" title="Downside metrics" subtitle="From the simulated distribution" />
              <CardBody>
                {sLoading || !sim?.metrics ? (
                  <div className="space-y-2">{Array.from({ length: 4 }).map((_, i) => <Skeleton key={i} className="h-12 w-full" />)}</div>
                ) : (
                  <div className="space-y-3">
                    <RiskRow
                      label="95% Value-at-Risk"
                      help="The 5% worst-case loss over the horizon — you'd lose at least this much 1 day in 20."
                      value={`-${((sim.metrics.var_95 || 0) * 100).toFixed(1)}%`}
                      tone="bear"
                    />
                    <RiskRow
                      label="Expected Shortfall (CVaR)"
                      help="Average loss in that worst 5% of outcomes — captures crash/jump severity."
                      value={`-${((sim.metrics.cvar_95 || 0) * 100).toFixed(1)}%`}
                      tone="bear"
                    />
                    <RiskRow
                      label="Probability of Gain"
                      help="Share of simulated paths ending above today's price."
                      value={`${((sim.metrics.prob_up || 0) * 100).toFixed(0)}%`}
                      tone={(sim.metrics.prob_up || 0) >= 0.5 ? 'bull' : 'bear'}
                    />
                    <RiskRow
                      label="90% Return Range"
                      help="5th to 95th percentile of simulated horizon returns (fat-tailed, jump-aware)."
                      value={`${((sim.metrics.p05 || 0) * 100).toFixed(1)}% … +${((sim.metrics.p95 || 0) * 100).toFixed(1)}%`}
                      tone="neutral"
                    />
                  </div>
                )}
                <div className="hairline my-4" />
                <p className="text-2xs text-ink-4 leading-relaxed">
                  {sim?.summary || 'Simulates continuous (GARCH) volatility plus sudden jumps calibrated from history, so the range reflects real gap/crash risk — not a thin Gaussian band.'}
                </p>
              </CardBody>
            </Card>
          </>
        )}

        {tab === 'price' && (
          <Card className="lg:col-span-3">
            <CardHeader
              eyebrow="Price History"
              title={`${tickerSymbol(display)} closing prices`}
              action={
                <SegmentedControl
                  size="sm"
                  value={range}
                  onChange={setRange}
                  options={HISTORY_RANGES}
                />
              }
            />
            <CardBody>
              {hLoading ? <Skeleton className="h-[360px] w-full" /> : hist?.history?.length ? (
                <AreaChart
                  data={hist.history}
                  dataKey="price"
                  xKey="date"
                  color="#F4C45D"
                  height={360}
                  showYAxis
                  formatter={(v) => `₹${v?.toLocaleString?.('en-IN', { maximumFractionDigits: 2 })}`}
                />
              ) : (
                <EmptyState title="No history" description="Could not load historical prices." />
              )}
            </CardBody>
          </Card>
        )}
      </motion.div>
    </div>
  );
};

// ── ForecastChart: realized area + projected dashed segment with a target dot ─
const ForecastChart = ({ realized, projected, baseline, target, direction }) => {
  // Combine into a single domain so X axis is continuous, but keep two series.
  // Recharts renders nulls as gaps; we leverage that to separate the two.
  const all = useMemo(() => {
    const byDate = new Map();
    for (const p of realized) byDate.set(p.date, { date: p.date, realized: p.price });
    for (const p of projected) {
      const x = byDate.get(p.date) || { date: p.date };
      x.projected = p.price;
      byDate.set(p.date, x);
    }
    return [...byDate.values()].sort((a, b) => a.date.localeCompare(b.date));
  }, [realized, projected]);

  const color = direction === 'DOWN' ? '#F43F5E' : '#10B981';

  return (
    <div className="w-full">
      <RechartForecast
        data={all}
        color={color}
        target={target}
        baseline={baseline}
      />
    </div>
  );
};

// ComposedChart lets the realized area + projected dashed line coexist with
// different stroke patterns. `connectNulls={false}` cleanly separates them.
const RechartForecast = ({ data, color, target, baseline }) => (
  <ResponsiveContainer width="100%" height={260}>
    <ComposedChart data={data} margin={{ top: 12, right: 12, bottom: 4, left: 0 }}>
      <defs>
        <linearGradient id="grad-realized" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%"  stopColor={color} stopOpacity={0.28} />
          <stop offset="100%" stopColor={color} stopOpacity={0} />
        </linearGradient>
      </defs>
      <XAxis
        dataKey="date"
        tickLine={false}
        axisLine={false}
        minTickGap={28}
        tick={{ fontSize: 11, fill: '#64748B' }}
        tickFormatter={(v) => typeof v === 'string' ? v.slice(5) : v}
      />
      <YAxis
        tickLine={false}
        axisLine={false}
        tick={{ fontSize: 11, fill: '#64748B' }}
        width={56}
        domain={['dataMin - 5', 'dataMax + 5']}
        tickFormatter={(v) => v?.toLocaleString?.('en-IN', { maximumFractionDigits: 0 })}
      />
      {Number.isFinite(baseline) && (
        <ReferenceLine y={baseline} stroke="#384358" strokeDasharray="3 3" label={{ value: 'Last close', fill: '#94A3B8', fontSize: 10, position: 'insideTopLeft' }} />
      )}
      <RTooltip
        cursor={{ stroke: '#384358', strokeWidth: 1, strokeDasharray: '3 3' }}
        contentStyle={{ background: '#171B25', border: '1px solid #262E40', borderRadius: 10 }}
        labelStyle={{ color: '#94A3B8', fontSize: 11 }}
        formatter={(v, name) => v == null ? null : [`₹${v.toLocaleString('en-IN', { maximumFractionDigits: 2 })}`, name === 'realized' ? 'Realized' : 'Projected']}
      />
      <Area
        type="monotone"
        dataKey="realized"
        stroke={color}
        strokeWidth={1.75}
        fill="url(#grad-realized)"
        isAnimationActive
        animationDuration={500}
        connectNulls={false}
      />
      <Line
        type="monotone"
        dataKey="projected"
        stroke="#F4C45D"
        strokeWidth={2}
        strokeDasharray="4 4"
        dot={false}
        connectNulls={false}
        isAnimationActive
        animationDuration={500}
      />
      {Number.isFinite(target) && data.length > 0 && (
        <ReferenceDot
          x={data[data.length - 1].date}
          y={target}
          r={5}
          fill="#F4C45D"
          stroke="#0A0B0F"
          strokeWidth={2}
        />
      )}
    </ComposedChart>
  </ResponsiveContainer>
);

// ── Monte-Carlo fan chart: p5–p95 + IQR bands with a median path ─────────────
const FanChart = ({ fan, S0 }) => {
  const data = useMemo(() => {
    const { steps = [], p05 = [], p25 = [], p50 = [], p75 = [], p95 = [] } = fan || {};
    return steps.map((s, i) => ({
      step: s === 0 ? 'now' : `+${s}d`,
      band: [p05[i], p95[i]],
      inner: [p25[i], p75[i]],
      p50: p50[i],
    }));
  }, [fan]);

  const fmtMoney = (x) => `₹${x?.toLocaleString?.('en-IN', { maximumFractionDigits: 0 })}`;

  return (
    <ResponsiveContainer width="100%" height={300}>
      <ComposedChart data={data} margin={{ top: 12, right: 12, bottom: 4, left: 0 }}>
        <XAxis
          dataKey="step" tickLine={false} axisLine={false} minTickGap={24}
          tick={{ fontSize: 11, fill: '#64748B' }}
        />
        <YAxis
          tickLine={false} axisLine={false} width={56}
          tick={{ fontSize: 11, fill: '#64748B' }}
          domain={['dataMin', 'dataMax']}
          tickFormatter={(v) => v?.toLocaleString?.('en-IN', { maximumFractionDigits: 0 })}
        />
        {Number.isFinite(S0) && (
          <ReferenceLine y={S0} stroke="#384358" strokeDasharray="3 3"
            label={{ value: 'Now', fill: '#94A3B8', fontSize: 10, position: 'insideTopLeft' }} />
        )}
        <RTooltip
          cursor={{ stroke: '#384358', strokeWidth: 1, strokeDasharray: '3 3' }}
          contentStyle={{ background: '#171B25', border: '1px solid #262E40', borderRadius: 10 }}
          labelStyle={{ color: '#94A3B8', fontSize: 11 }}
          formatter={(v, name) => {
            const labels = { band: '90% range', inner: 'IQR (p25–p75)', p50: 'Median' };
            const txt = Array.isArray(v) ? `${fmtMoney(v[0])} – ${fmtMoney(v[1])}` : fmtMoney(v);
            return [txt, labels[name] || name];
          }}
        />
        <Area type="monotone" dataKey="band"  stroke="none" fill="#F4C45D" fillOpacity={0.12} isAnimationActive animationDuration={500} />
        <Area type="monotone" dataKey="inner" stroke="none" fill="#F4C45D" fillOpacity={0.22} isAnimationActive animationDuration={500} />
        <Line type="monotone" dataKey="p50" stroke="#F4C45D" strokeWidth={2} dot={false} isAnimationActive animationDuration={500} />
      </ComposedChart>
    </ResponsiveContainer>
  );
};

const RiskRow = ({ label, value, help, tone = 'neutral' }) => {
  const color = tone === 'bear' ? 'text-bear' : tone === 'bull' ? 'text-bull' : 'text-ink-1';
  return (
    <div className="flex items-start justify-between gap-3">
      <div className="min-w-0">
        <div className="text-xs font-medium text-ink-2">{label}</div>
        <div className="text-2xs text-ink-5 leading-snug mt-0.5">{help}</div>
      </div>
      <div className={cn('font-display font-bold text-md tabular shrink-0', color)}>{value}</div>
    </div>
  );
};

export default Analysis;
