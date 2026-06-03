import React, { useMemo, useState, useCallback } from 'react';
import { useSearchParams } from 'react-router-dom';
import { motion } from 'framer-motion';
import { LineChart, Line, ResponsiveContainer, Tooltip, XAxis, YAxis, ReferenceLine, Legend } from 'recharts';
import { api } from '../api/client.js';
import { useApp } from '../context/AppContext.jsx';
import { UNIVERSE, META_BY_TICKER, isValidHorizon, DEFAULT_HORIZON } from '../data/universe.js';
import { Card, CardHeader, CardBody } from '../components/ui/Card.jsx';
import { Button } from '../components/ui/Button.jsx';
import { Select, Input } from '../components/ui/Input.jsx';
import { Badge } from '../components/ui/Badge.jsx';
import { Skeleton } from '../components/ui/Skeleton.jsx';
import { Counter } from '../components/ui/Counter.jsx';
import { EmptyState } from '../components/ui/Empty.jsx';
import { HorizonSwitcher } from '../components/domain/HorizonSwitcher.jsx';
import { IconBeaker, IconBolt, IconTarget, IconShield, IconActivity, IconRefresh } from '../components/shell/Icons.jsx';
import { toApiTicker, tickerSymbol, cn } from '../lib/utils.js';

const fadeUp = {
  initial: { opacity: 0, y: 8 },
  animate: { opacity: 1, y: 0 },
  transition: { duration: 0.32, ease: [0.22, 0.61, 0.36, 1] },
};

const Metric = ({ label, value, suffix, tone = 'ink', hint }) => (
  <div className="surface-flat px-4 py-3.5">
    <div className="eyebrow mb-1.5">{label}</div>
    <div className={cn(
      'font-display font-bold text-2xl tabular',
      tone === 'bull' ? 'text-bull' : tone === 'bear' ? 'text-bear' : tone === 'alpha' ? 'text-alpha' : 'text-ink-1',
    )}>
      <Counter value={value} decimals={2} />{suffix}
    </div>
    {hint && <div className="text-2xs text-ink-4 mt-1">{hint}</div>}
  </div>
);

const Backtest = () => {
  const { prefs, updatePrefs } = useApp();
  const [params, setParams] = useSearchParams();

  // Ticker: URL > default
  const urlTicker = params.get('ticker');
  const ticker = META_BY_TICKER[urlTicker] ? urlTicker : 'RELIANCE.NS';
  const setTicker = useCallback((next) => {
    const p = new URLSearchParams(params);
    p.set('ticker', next);
    setParams(p, { replace: true });
  }, [params, setParams]);

  // Horizon: URL > prefs > default
  const urlHorizon = params.get('horizon');
  const horizon = isValidHorizon(urlHorizon) ? urlHorizon : (prefs.horizon || DEFAULT_HORIZON);
  const setHorizon = useCallback((next) => {
    updatePrefs({ horizon: next });
    const p = new URLSearchParams(params);
    p.delete('horizon');
    setParams(p, { replace: true });
  }, [params, setParams, updatePrefs]);

  const [tc, setTc] = useState(0.001);
  const [running, setRunning] = useState(false);
  const [result, setResult] = useState(null);

  const run = async () => {
    setRunning(true);
    try {
      const res = await api.backtest({ ticker: toApiTicker(ticker), horizon, transaction_cost: tc });
      setResult(res);
    } catch (e) {
      console.error(e);
    } finally {
      setRunning(false);
    }
  };

  const chartData = useMemo(() => {
    if (!result?.metrics?.equity_curve) return [];
    const eq = result.metrics.equity_curve;
    const bh = result.metrics.buyhold_curve || [];
    const ds = result.metrics.dates || [];
    return eq.map((v, i) => ({ date: ds[i] || String(i), strategy: v, buyhold: bh[i] }));
  }, [result]);

  return (
    <div className="space-y-5 pb-12">
      <motion.div {...fadeUp}>
        <Card glow="iris">
          <div className="px-6 py-5 flex items-center justify-between gap-4 flex-wrap">
            <div className="flex items-center gap-4">
              <span className="w-12 h-12 grid place-items-center rounded-xl bg-bg-2 border border-line-muted text-iris-soft">
                <IconBeaker className="w-5 h-5" />
              </span>
              <div>
                <div className="eyebrow">Strategy Validation</div>
                <h2 className="font-display font-bold text-2xl text-ink-1 leading-tight">Walk-Forward Backtest</h2>
                <p className="text-xs text-ink-3 mt-0.5 max-w-md">
                  Time-series-aware splits with embargo periods · simulates UP/DOWN signal trades against buy-and-hold benchmark.
                </p>
              </div>
            </div>
            <Button size="lg" variant="primary" loading={running} leadingIcon={IconBolt} onClick={run}>
              Run backtest
            </Button>
          </div>
        </Card>
      </motion.div>

      <motion.div {...fadeUp}>
        <Card>
          <CardHeader eyebrow="Setup" title="Backtest configuration" />
          <CardBody>
            <div className="grid grid-cols-1 md:grid-cols-12 gap-3 items-end">
              <div className="md:col-span-5">
                <label className="eyebrow block mb-1.5">Ticker</label>
                <Select value={ticker} onChange={(e) => setTicker(e.target.value)}>
                  {UNIVERSE.map((u) => <option key={u.ticker} value={u.ticker}>{tickerSymbol(u.ticker)} · {u.name}</option>)}
                </Select>
              </div>
              <div className="md:col-span-3">
                <label className="eyebrow block mb-1.5">Horizon</label>
                <HorizonSwitcher value={horizon} onChange={setHorizon} />
              </div>
              <div className="md:col-span-2">
                <label className="eyebrow block mb-1.5">Transaction cost</label>
                <Input
                  type="number" step="0.0005" min="0" max="0.05"
                  value={tc} onChange={(e) => setTc(parseFloat(e.target.value || 0))}
                  trailing={<span className="text-2xs text-ink-4 pr-2">per trade</span>}
                />
              </div>
              <div className="md:col-span-2 flex items-end justify-end">
                <Button size="md" variant="primary" loading={running} leadingIcon={IconBolt} onClick={run} className="w-full">
                  Run
                </Button>
              </div>
            </div>
          </CardBody>
        </Card>
      </motion.div>

      {/* Result */}
      <motion.div {...fadeUp}>
        <Card>
          <CardHeader
            eyebrow="Results"
            title={result ? `${tickerSymbol(ticker)} · ${horizon} backtest` : 'Run a backtest to view results'}
            subtitle={result ? result.summary : 'Strategy: long when model predicts UP, cash when DOWN. Benchmark: buy and hold.'}
            action={result && <Button size="sm" variant="ghost" leadingIcon={IconRefresh} onClick={run}>Re-run</Button>}
          />
          <CardBody>
            {running ? (
              <div className="space-y-3">
                <Skeleton className="h-20 w-full" />
                <Skeleton className="h-[300px] w-full" />
              </div>
            ) : !result ? (
              <EmptyState
                icon={IconBeaker}
                title="No results yet"
                description="Pick a ticker, horizon, and run the backtest."
                action={<Button size="sm" variant="primary" leadingIcon={IconBolt} onClick={run}>Run backtest</Button>}
              />
            ) : (
              <>
                <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-7 gap-2">
                  <Metric label="Annual Return" tone={result.metrics.annual_return >= 0 ? 'bull' : 'bear'} value={result.metrics.annual_return * 100} suffix="%" />
                  <Metric label="Benchmark" value={result.metrics.benchmark_annual_return * 100} suffix="%" />
                  <Metric label="Excess" tone={result.metrics.excess_return >= 0 ? 'bull' : 'bear'} value={result.metrics.excess_return * 100} suffix="%" />
                  <Metric label="Sharpe" tone="alpha" value={result.metrics.sharpe_ratio} />
                  <Metric label="Max Drawdown" tone="bear" value={result.metrics.max_drawdown * 100} suffix="%" />
                  <Metric label="Calmar" value={result.metrics.calmar_ratio} />
                  <Metric label="Hit Rate" value={result.metrics.hit_rate * 100} suffix="%" hint={`${result.metrics.n_trades} trades`} />
                </div>

                <div className="mt-5 rounded-lg border border-line-faint bg-bg-0/30 p-2">
                  <ResponsiveContainer width="100%" height={340}>
                    <LineChart data={chartData} margin={{ top: 12, right: 12, bottom: 4, left: 0 }}>
                      <XAxis
                        dataKey="date"
                        tickLine={false} axisLine={false}
                        tick={{ fontSize: 11, fill: '#64748B' }}
                        minTickGap={28}
                        tickFormatter={(v) => typeof v === 'string' ? v.slice(2, 7) : v}
                      />
                      <YAxis
                        tickLine={false} axisLine={false}
                        tick={{ fontSize: 11, fill: '#64748B' }}
                        width={56}
                        tickFormatter={(v) => (v * 100 - 100).toFixed(0) + '%'}
                      />
                      <Tooltip
                        cursor={{ stroke: '#384358', strokeWidth: 1, strokeDasharray: '3 3' }}
                        contentStyle={{ background: '#171B25', border: '1px solid #262E40', borderRadius: 10 }}
                        labelStyle={{ color: '#94A3B8', fontSize: 11 }}
                        formatter={(v, name) => [`${((v - 1) * 100).toFixed(2)}%`, name === 'strategy' ? 'Strategy' : 'Buy & Hold']}
                      />
                      <ReferenceLine y={1} stroke="#384358" strokeDasharray="3 3" />
                      <Legend
                        wrapperStyle={{ fontSize: 11, color: '#94A3B8' }}
                        formatter={(value) => value === 'strategy' ? 'Strategy' : 'Buy & Hold'}
                      />
                      <Line type="monotone" dataKey="buyhold" stroke="#64748B" strokeWidth={1.4} dot={false} strokeDasharray="3 3" isAnimationActive />
                      <Line type="monotone" dataKey="strategy" stroke="#F4C45D" strokeWidth={2} dot={false} isAnimationActive animationDuration={700} />
                    </LineChart>
                  </ResponsiveContainer>
                </div>
              </>
            )}
          </CardBody>
        </Card>
      </motion.div>

      <div className="text-2xs text-ink-5 text-center pt-2">
        Past performance is not indicative of future results.
      </div>
    </div>
  );
};

export default Backtest;
