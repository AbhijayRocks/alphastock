import React, { useMemo } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { motion } from 'framer-motion';
import { useApi } from '../hooks/useApi.js';
import { api } from '../api/client.js';
import { useApp } from '../context/AppContext.jsx';
import { MarketPulse } from '../components/domain/MarketPulse.jsx';
import { HorizonSwitcher } from '../components/domain/HorizonSwitcher.jsx';
import { DirectionPill, SignalStrengthBar, ConfidenceMeter } from '../components/domain/DirectionPill.jsx';
import { TickerCell } from '../components/domain/TickerCell.jsx';
import { StatTile } from '../components/ui/StatTile.jsx';
import { Card, CardHeader, CardBody } from '../components/ui/Card.jsx';
import { Badge, Pill } from '../components/ui/Badge.jsx';
import { Button, IconButton } from '../components/ui/Button.jsx';
import { Sparkline } from '../components/charts/Sparkline.jsx';
import { AreaChart } from '../components/charts/AreaChart.jsx';
import { EmptyState } from '../components/ui/Empty.jsx';
import { SkeletonStat, Skeleton } from '../components/ui/Skeleton.jsx';
import {
  IconArrowRight, IconArrowUp, IconArrowDown, IconBrain, IconTarget,
  IconWaveform, IconBolt, IconStar, IconStarFill, IconRefresh,
} from '../components/shell/Icons.jsx';
import { UNIVERSE, META_BY_TICKER } from '../data/universe.js';
import {
  toApiTicker, toDisplayTicker, tickerSymbol, fmtPrice, fmtPctRaw,
  hashStr, seedRandom, cn, signClass,
} from '../lib/utils.js';

// ─────────────────────────────────────────────────────────────────────────────

const fadeUp = {
  initial: { opacity: 0, y: 8 },
  animate: { opacity: 1, y: 0 },
  transition: { duration: 0.32, ease: [0.22, 0.61, 0.36, 1] },
};

// Use the universe + horizon to fetch predictions for top-N stocks and rank them.
const useUniversePredictions = (horizon) => {
  const tickers = useMemo(() => UNIVERSE.slice(0, 24).map((u) => toApiTicker(u.ticker)), []);
  return useApi(
    async () => {
      const res = await Promise.allSettled(tickers.map((t) => api.predict({ ticker: t, horizon })));
      return res
        .filter((r) => r.status === 'fulfilled')
        .map((r) => r.value);
    },
    [horizon, tickers.join(',')],
  );
};

const PickRow = ({ p, rank }) => {
  const display = toDisplayTicker(p.ticker);
  const sym = tickerSymbol(display);
  const pretRet = p.prediction.predicted_return * 100;
  const meta = META_BY_TICKER[display];
  const spark = useMemo(() => {
    const rng = seedRandom(hashStr(display + ':d'));
    let v = 100; const out = [];
    for (let i = 0; i < 30; i++) { v *= 1 + (rng() - 0.5) * 0.03; out.push({ price: v }); }
    return out;
  }, [display]);

  return (
    <Link
      to={`/analysis?ticker=${encodeURIComponent(display)}`}
      className="group grid grid-cols-[28px_1.6fr_auto_auto_70px] items-center gap-3 px-4 py-2.5 hover:bg-bg-2 transition-colors border-t border-line-faint first:border-t-0"
    >
      <span className="text-2xs font-mono text-ink-5 tabular">{String(rank).padStart(2, '0')}</span>
      <div className="min-w-0 flex items-center gap-2.5">
        <span className="w-7 h-7 grid place-items-center rounded-md bg-bg-2 border border-line-muted text-2xs font-mono font-semibold tabular text-ink-2 group-hover:border-line-strong">
          {sym.slice(0, 3)}
        </span>
        <div className="min-w-0">
          <div className="text-xs font-semibold text-ink-1 truncate group-hover:text-alpha transition-colors">{sym}</div>
          <div className="text-2xs text-ink-4 truncate">{meta?.sector || p.sector}</div>
        </div>
      </div>
      <SignalStrengthBar strength={p.prediction.signal_strength} />
      <span className={cn(
        'text-xs font-semibold tabular inline-flex items-center justify-end gap-0.5',
        signClass(pretRet),
      )}>
        {pretRet > 0 ? <IconArrowUp className="w-2.5 h-2.5" /> : pretRet < 0 ? <IconArrowDown className="w-2.5 h-2.5" /> : null}
        {pretRet > 0 ? '+' : ''}{pretRet.toFixed(2)}%
      </span>
      <Sparkline data={spark} stroke={pretRet >= 0 ? '#10B981' : '#F43F5E'} width={64} height={20} fill={false} />
    </Link>
  );
};

const TopPicksCard = ({ title, eyebrow, items, loading, tone }) => (
  <Card>
    <CardHeader
      eyebrow={eyebrow}
      title={title}
      action={
        <Pill className={cn(
          tone === 'bull' ? 'text-bull border-bull/30 bg-bull/10' :
          tone === 'bear' ? 'text-bear border-bear/30 bg-bear/10' : '',
        )}>
          {items.length} {tone === 'bull' ? 'longs' : tone === 'bear' ? 'shorts' : 'signals'}
        </Pill>
      }
    />
    <div>
      {loading && items.length === 0 ? (
        Array.from({ length: 5 }).map((_, i) => (
          <div key={i} className="grid grid-cols-[28px_1.6fr_auto_auto_70px] items-center gap-3 px-4 py-2.5 border-t border-line-faint">
            <Skeleton className="h-3 w-5" />
            <div className="flex items-center gap-2.5"><Skeleton className="w-7 h-7" /><Skeleton className="h-3 w-24" /></div>
            <Skeleton className="h-3 w-8" />
            <Skeleton className="h-3 w-10" />
            <Skeleton className="h-3 w-16" />
          </div>
        ))
      ) : items.length === 0 ? (
        <EmptyState title="No signals" description="No predictions returned for this horizon." />
      ) : (
        items.map((p, i) => <PickRow key={p.ticker} p={p} rank={i + 1} />)
      )}
    </div>
    <div className="px-4 py-2 border-t border-line-faint">
      <Link to="/screener" className="text-2xs font-medium text-ink-3 hover:text-alpha transition-colors inline-flex items-center gap-1">
        View all in screener <IconArrowRight className="w-3 h-3" />
      </Link>
    </div>
  </Card>
);

// ── Watchlist focus card ─────────────────────────────────────────────────────
const WatchlistFocus = ({ horizon }) => {
  const { watchlist } = useApp();
  const tickers = watchlist.slice(0, 5).map(toApiTicker);
  const { data, loading } = useApi(
    async () => {
      const res = await Promise.allSettled(tickers.map((t) => api.predict({ ticker: t, horizon })));
      return res.filter((r) => r.status === 'fulfilled').map((r) => r.value);
    },
    [horizon, tickers.join(',')],
  );

  return (
    <Card>
      <CardHeader
        eyebrow="Personal Focus"
        title="Watchlist Signals"
        subtitle="Your tracked tickers at the selected horizon"
        action={<Link to="/screener"><Button size="xs" variant="ghost" trailingIcon={IconArrowRight}>Manage</Button></Link>}
      />
      <div>
        {loading && (!data || data.length === 0) ? (
          Array.from({ length: 3 }).map((_, i) => (
            <div key={i} className="grid grid-cols-[1.6fr_auto_1fr_auto] items-center gap-3 px-4 py-3 border-t border-line-faint">
              <Skeleton className="h-3 w-40" />
              <Skeleton className="h-5 w-16" />
              <Skeleton className="h-1.5 w-full" />
              <Skeleton className="h-3 w-12" />
            </div>
          ))
        ) : data && data.length > 0 ? (
          data.map((p) => {
            const display = toDisplayTicker(p.ticker);
            const sym = tickerSymbol(display);
            return (
              <Link
                key={p.ticker}
                to={`/analysis?ticker=${encodeURIComponent(display)}`}
                className="grid grid-cols-[1.6fr_auto_1fr_auto] items-center gap-3 px-4 py-3 hover:bg-bg-2 transition-colors border-t border-line-faint group"
              >
                <div className="min-w-0">
                  <div className="text-sm font-semibold text-ink-1 truncate group-hover:text-alpha transition-colors">{sym}</div>
                  <div className="text-2xs text-ink-4 truncate">{p.company_name}</div>
                </div>
                <DirectionPill direction={p.prediction.direction} probability={p.prediction.probability} size="sm" />
                <ConfidenceMeter probability={p.prediction.probability} />
                <span className={cn('text-xs font-semibold tabular shrink-0 inline-flex items-center justify-end gap-0.5', signClass(p.prediction.predicted_return))}>
                  {p.prediction.predicted_return > 0 ? <IconArrowUp className="w-2.5 h-2.5" /> : p.prediction.predicted_return < 0 ? <IconArrowDown className="w-2.5 h-2.5" /> : null}
                  {p.prediction.predicted_return > 0 ? '+' : ''}{(p.prediction.predicted_return * 100).toFixed(2)}%
                </span>
              </Link>
            );
          })
        ) : (
          <EmptyState
            icon={IconStar}
            title="Build your watchlist"
            description="Star a ticker in the screener or command palette to track it here."
            action={<Link to="/screener"><Button size="sm" variant="surface" leadingIcon={IconStar}>Open Screener</Button></Link>}
          />
        )}
      </div>
    </Card>
  );
};

// ── Sector heat strip ────────────────────────────────────────────────────────
const SectorHeat = ({ predictions = [] }) => {
  const sectors = useMemo(() => {
    const map = new Map();
    for (const p of predictions) {
      const ret = p.prediction.predicted_return;
      const s = p.sector || META_BY_TICKER[toDisplayTicker(p.ticker)]?.sector || 'Other';
      if (!map.has(s)) map.set(s, { sum: 0, count: 0, up: 0, down: 0 });
      const it = map.get(s);
      it.sum += ret; it.count += 1; ret >= 0 ? it.up++ : it.down++;
    }
    return [...map.entries()]
      .map(([sector, v]) => ({ sector, avg: v.sum / v.count, up: v.up, down: v.down, count: v.count }))
      .sort((a, b) => b.avg - a.avg);
  }, [predictions]);

  if (!sectors.length) {
    return (
      <div className="grid grid-cols-2 md:grid-cols-3 gap-2 p-4">
        {Array.from({ length: 6 }).map((_, i) => <Skeleton key={i} className="h-14" />)}
      </div>
    );
  }

  return (
    <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-2 p-4">
      {sectors.map((s) => {
        const pct = s.avg * 100;
        const pos = pct >= 0;
        const intensity = Math.min(1, Math.abs(pct) / 4);
        return (
          <div
            key={s.sector}
            className={cn(
              'relative overflow-hidden rounded-lg border border-line-muted bg-bg-2 px-3 py-2.5 group hover:border-line-strong transition-colors',
            )}
          >
            <div
              className="absolute inset-0 pointer-events-none transition-opacity"
              style={{
                background: pos
                  ? `linear-gradient(135deg, rgba(16,185,129,${0.18 * intensity}), transparent)`
                  : `linear-gradient(135deg, rgba(244,63,94,${0.18 * intensity}), transparent)`,
              }}
            />
            <div className="relative min-w-0">
              <div className="text-2xs font-medium tracking-wider uppercase text-ink-4 truncate">{s.sector}</div>
              <div className={cn('font-display font-semibold text-md tabular', pos ? 'text-bull' : 'text-bear')}>
                {pos ? '+' : ''}{pct.toFixed(2)}%
              </div>
            </div>
          </div>
        );
      })}
    </div>
  );
};

// ─────────────────────────────────────────────────────────────────────────────

const Dashboard = () => {
  const { prefs, updatePrefs } = useApp();
  const horizon = prefs.horizon;
  const navigate = useNavigate();

  const { data: preds, loading: pLoading, refetch: pRefetch } = useUniversePredictions(horizon);
  const { data: health } = useApi(() => api.health(), []);

  // Rank by absolute predicted return; split into longs/shorts
  const { gainers, losers, totalSignals, strongCount, avgConfidence, avgReturn } = useMemo(() => {
    const list = preds || [];
    const sorted = [...list].sort((a, b) => b.prediction.predicted_return - a.prediction.predicted_return);
    const gainers = sorted.filter((p) => p.prediction.direction === 'UP').slice(0, 6);
    const losers  = sorted.filter((p) => p.prediction.direction === 'DOWN').slice(-6).reverse();
    const strongCount = list.filter((p) => p.prediction.signal_strength === 'strong').length;
    const avgConfidence = list.length
      ? list.reduce((s, p) => s + Math.abs(p.prediction.probability - 0.5), 0) / list.length * 2
      : 0;
    const avgReturn = list.length
      ? list.reduce((s, p) => s + p.prediction.predicted_return, 0) / list.length * 100
      : 0;
    return { gainers, losers, totalSignals: list.length, strongCount, avgConfidence, avgReturn };
  }, [preds]);

  // top spark for hero card: best gainer's history
  const heroTicker = gainers[0]?.ticker || (preds && preds[0]?.ticker);
  const { data: heroHist } = useApi(
    () => heroTicker ? api.history(heroTicker, 90) : Promise.resolve(null),
    [heroTicker],
  );

  return (
    <div className="space-y-5 pb-12">
      {/* Hero strip: market pulse + horizon picker */}
      <motion.div {...fadeUp} className="flex flex-col gap-4">
        <MarketPulse horizon={horizon} />

        <div className="flex items-center justify-between gap-4 flex-wrap">
          <div className="flex items-center gap-3 flex-wrap">
            <span className="eyebrow">Forecast horizon</span>
            <HorizonSwitcher value={horizon} onChange={(v) => updatePrefs({ horizon: v })} />
            <Badge tone="iris" dot size="sm">NIFTY 50 coverage</Badge>
          </div>
          <div className="flex items-center gap-2">
            <Button size="sm" variant="ghost" leadingIcon={IconRefresh} onClick={pRefetch}>Refresh</Button>
            <Link to="/screener"><Button size="sm" variant="primary" trailingIcon={IconArrowRight}>Open Screener</Button></Link>
          </div>
        </div>
      </motion.div>

      {/* KPI row */}
      <motion.div {...fadeUp} className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <StatTile
          eyebrow="Universe Coverage"
          value={health?.stocks_available ?? 50}
          valueSuffix=" / 50"
          valueDecimals={0}
          icon={IconBrain}
          tone="alpha"
          hint="NSE equities tracked live"
        />
        <StatTile
          eyebrow="Strong Signals"
          value={strongCount}
          valueDecimals={0}
          delta={{ value: strongCount, label: `of ${totalSignals} tracked`, sign: 0 }}
          icon={IconBolt}
          tone="iris"
        />
        <StatTile
          eyebrow="Avg Confidence"
          value={avgConfidence * 100}
          valueSuffix="%"
          valueDecimals={1}
          icon={IconTarget}
          delta={{ value: (avgConfidence * 100) - 50, sign: avgConfidence * 100 - 50 > 0 ? 1 : -1, label: 'vs random' }}
        />
        <StatTile
          eyebrow="Avg Expected Return"
          value={avgReturn}
          valueSuffix="%"
          valueDecimals={2}
          icon={IconWaveform}
          tone={avgReturn >= 0 ? 'bull' : 'bear'}
          delta={{ value: avgReturn, sign: Math.sign(avgReturn), label: `at ${horizon}` }}
        />
      </motion.div>

      {/* Hero panel: top conviction + chart */}
      <motion.div {...fadeUp} className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        <Card glow="alpha" className="lg:col-span-2">
          <CardHeader
            eyebrow="Top Conviction · Long"
            title={gainers[0] ? `${tickerSymbol(toDisplayTicker(gainers[0].ticker))} — ${gainers[0].company_name}` : 'Computing…'}
            subtitle={gainers[0] ? gainers[0].sector : ''}
            action={
              gainers[0] && (
                <DirectionPill
                  direction={gainers[0].prediction.direction}
                  probability={gainers[0].prediction.probability}
                  size="lg"
                />
              )
            }
          />
          <CardBody>
            <div className="grid grid-cols-3 gap-4 mb-3">
              <div>
                <div className="eyebrow mb-1">Predicted Return</div>
                <div className={cn('font-display font-bold text-2xl tabular',
                  gainers[0]?.prediction.predicted_return >= 0 ? 'text-bull' : 'text-bear')}>
                  {gainers[0] ? `${gainers[0].prediction.predicted_return >= 0 ? '+' : ''}${(gainers[0].prediction.predicted_return * 100).toFixed(2)}%` : '—'}
                </div>
                <div className="text-2xs text-ink-4 mt-0.5">
                  {gainers[0] ? `[${(gainers[0].prediction.confidence_lower * 100).toFixed(2)}% , ${(gainers[0].prediction.confidence_upper * 100).toFixed(2)}%]` : ''}
                </div>
              </div>
              <div>
                <div className="eyebrow mb-1">Current Price</div>
                <div className="font-display font-bold text-2xl tabular text-ink-1">
                  {gainers[0] ? fmtPrice(gainers[0].current_price, { dp: 2 }) : '—'}
                </div>
                <div className="text-2xs text-ink-4 mt-0.5">Last close</div>
              </div>
              <div>
                <div className="eyebrow mb-1">Signal</div>
                <div className="flex items-center gap-2 mt-1">
                  <SignalStrengthBar strength={gainers[0]?.prediction.signal_strength || 'weak'} />
                  <span className="text-xs font-medium text-ink-1 capitalize">
                    {gainers[0]?.prediction.signal_strength || '—'}
                  </span>
                </div>
                <div className="text-2xs text-ink-4 mt-1.5">Conviction at {horizon} horizon</div>
              </div>
            </div>

            <div className="rounded-lg border border-line-faint bg-bg-0/30 p-2">
              {heroHist?.history?.length ? (
                <AreaChart
                  data={heroHist.history}
                  dataKey="price"
                  xKey="date"
                  color="#F4C45D"
                  height={180}
                  formatter={(v) => `₹${v?.toLocaleString?.('en-IN', { maximumFractionDigits: 2 })}`}
                />
              ) : (
                <Skeleton className="h-[180px] w-full" />
              )}
            </div>

            {gainers[0] && (
              <div className="flex items-center justify-between mt-3">
                <div className="text-2xs text-ink-4">
                  Forecast generated <span className="text-ink-2">{new Date(gainers[0].last_updated).toLocaleTimeString('en-IN')}</span>
                </div>
                <Link to={`/analysis?ticker=${encodeURIComponent(toDisplayTicker(gainers[0].ticker))}`}>
                  <Button size="sm" variant="surface" trailingIcon={IconArrowRight}>Open analysis</Button>
                </Link>
              </div>
            )}
          </CardBody>
        </Card>

        <Card>
          <CardHeader eyebrow="Sector Heat" title="Expected return by sector" />
          <SectorHeat predictions={preds || []} />
        </Card>
      </motion.div>

      {/* Top picks */}
      <motion.div {...fadeUp} className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <TopPicksCard
          eyebrow="Top Signals"
          title={`Top Gainers · ${horizon}`}
          items={gainers}
          loading={pLoading}
          tone="bull"
        />
        <TopPicksCard
          eyebrow="Top Signals"
          title={`Top Losers · ${horizon}`}
          items={losers}
          loading={pLoading}
          tone="bear"
        />
      </motion.div>

      {/* Cross-sectional market-neutral signals */}
      <motion.div {...fadeUp}>
        <SignalsBoard horizon={horizon} />
      </motion.div>

      {/* Watchlist + System */}
      <motion.div {...fadeUp} className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        <div className="lg:col-span-2"><WatchlistFocus horizon={horizon} /></div>
        <Card>
          <CardHeader eyebrow="System" title="Market Status" />
          <CardBody>
            <ul className="space-y-3">
              <li className="flex items-center justify-between">
                <span className="text-xs text-ink-3">Data feed</span>
                <Badge tone={health?.status === 'healthy' ? 'bull' : 'warn'} dot size="sm">
                  {health?.status === 'healthy' ? 'Live' : 'Reconnecting'}
                </Badge>
              </li>
              <li className="flex items-center justify-between">
                <span className="text-xs text-ink-3">Coverage</span>
                <span className="text-xs font-semibold tabular text-ink-1">{health?.stocks_available ?? 50} / 50 instruments</span>
              </li>
              <li className="flex items-center justify-between">
                <span className="text-xs text-ink-3">Signals tracked</span>
                <span className="text-xs font-semibold tabular text-ink-1">{totalSignals || '—'}</span>
              </li>
              <li className="flex items-center justify-between">
                <span className="text-xs text-ink-3">Strong signals</span>
                <span className="text-xs font-semibold tabular text-bull">{strongCount}</span>
              </li>
            </ul>

            <div className="hairline my-4" />

            <div>
              <div className="eyebrow mb-2">Workflow</div>
              <ol className="text-xs text-ink-3 space-y-1.5">
                <li className="flex gap-2"><span className="text-ink-5">01</span> Read the market regime above</li>
                <li className="flex gap-2"><span className="text-ink-5">02</span> Scan top signals at this horizon</li>
                <li className="flex gap-2"><span className="text-ink-5">03</span> Review the key drivers in Analysis</li>
                <li className="flex gap-2"><span className="text-ink-5">04</span> Size positions in Portfolio</li>
              </ol>
            </div>
          </CardBody>
        </Card>
      </motion.div>
    </div>
  );
};

// ── Cross-sectional long/short signal board ──────────────────────────────────
const SignalsBoard = ({ horizon }) => {
  const { data, loading } = useApi(() => api.signals(horizon), [horizon]);
  const longs = data?.longs || [];
  const shorts = data?.shorts || [];

  const Col = ({ title, items, tone }) => (
    <div>
      <div className={cn('text-2xs font-semibold uppercase tracking-wider mb-2',
        tone === 'bull' ? 'text-bull' : 'text-bear')}>{title}</div>
      <div className="space-y-1">
        {items.slice(0, 8).map((s) => {
          const display = toDisplayTicker(s.ticker);
          return (
            <Link key={s.ticker} to={`/analysis?ticker=${encodeURIComponent(display)}&horizon=${horizon}`}
              className="flex items-center justify-between gap-2 px-2 py-1.5 rounded-md hover:bg-bg-2 transition-colors group">
              <div className="flex items-center gap-2 min-w-0">
                <span className="text-2xs font-mono text-ink-5 w-4 tabular">{s.rank}</span>
                <span className="text-xs font-semibold text-ink-1 truncate group-hover:text-alpha transition-colors">{tickerSymbol(display)}</span>
              </div>
              <div className="flex items-center gap-2 shrink-0">
                <span className="text-2xs text-ink-4 tabular">{Math.round((s.confidence || 0) * 100)}%</span>
                <span className="inline-block w-10 h-1 rounded-full bg-bg-3 overflow-hidden">
                  <span className={cn('block h-full', tone === 'bull' ? 'bg-bull' : 'bg-bear')}
                    style={{ width: `${Math.round((s.confidence || 0) * 100)}%` }} />
                </span>
              </div>
            </Link>
          );
        })}
      </div>
    </div>
  );

  return (
    <Card>
      <CardHeader
        eyebrow="Cross-Sectional · Market-Neutral"
        title="Long / Short Signals"
        subtitle={data ? `Quant ranking model · as of ${data.as_of} · ${horizon}` : 'Quant ranking model (rank + meta-labeling)'}
        action={<Pill>{(longs.length + shorts.length) || '—'} names</Pill>}
      />
      <CardBody>
        {loading && !data ? (
          <Skeleton className="h-40 w-full" />
        ) : (longs.length || shorts.length) ? (
          <>
            <div className="grid grid-cols-2 gap-5">
              <Col title="▲ Long (top rank)" items={longs} tone="bull" />
              <Col title="▼ Short (bottom rank)" items={shorts} tone="bear" />
            </div>
            <div className="text-2xs text-ink-5 mt-3">Bars = meta-label confidence. Market-neutral: long the top, short the bottom.</div>
          </>
        ) : (
          <EmptyState title="No signals yet" description="Train the cross-sectional model to populate this board." />
        )}
      </CardBody>
    </Card>
  );
};

export default Dashboard;
