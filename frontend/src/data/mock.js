// Mock data generators that mirror backend response shapes 1:1.
// Used when the backend is unreachable so every page renders fully.
//
// All shapes are derived directly from backend/api/schemas.py.
// Deterministic per-ticker via seeded RNG so the UI is stable between reloads.

import { UNIVERSE, META_BY_TICKER } from './universe.js';
import { hashStr, seedRandom, toApiTicker, toDisplayTicker } from '../lib/utils.js';

const FEATURES = [
  'MACD_14', 'RSI_14', 'BB_width_20', 'ATR_14', 'EMA_50_cross', 'SMA_200_dist',
  'returns_5d', 'returns_20d', 'volume_zscore', 'OBV_slope',
  'USD_INR_return', 'BRENT_return', 'GOLD_return', 'VIX_INDIA', 'US_10Y_change',
  'NIFTY_return_5d', 'NIFTY_return_20d', 'sector_momentum',
  'volatility_5d', 'volatility_20d', 'skew_60d', 'kurt_60d',
  'support_dist', 'resistance_dist', 'gap_pct',
];

const REGIMES = ['bull', 'bear', 'sideways', 'crisis'];

// ── Series generators ─────────────────────────────────────────────────────────
const priceSeries = (apiTicker, days = 90, basePrice = 1000) => {
  const rng = seedRandom(hashStr(apiTicker));
  const series = [];
  let p = basePrice * (0.5 + rng() * 1.5);
  const drift = (rng() - 0.45) * 0.0009;
  const vol = 0.012 + rng() * 0.014;
  const today = new Date();
  for (let i = days - 1; i >= 0; i--) {
    const d = new Date(today); d.setDate(d.getDate() - i);
    const shock = (rng() - 0.5) * vol * 2;
    p = Math.max(1, p * (1 + drift + shock));
    series.push({ date: d.toISOString().slice(0, 10), price: Math.round(p * 100) / 100 });
  }
  return series;
};

// ── /api/health ───────────────────────────────────────────────────────────────
export const mockHealth = () => ({
  status: 'healthy',
  models_loaded: 750,
  stocks_available: UNIVERSE.length,
  version: '1.0.0',
});

// ── /api/regime ───────────────────────────────────────────────────────────────
export const mockRegime = () => {
  const idx = Math.floor(Date.now() / 86400000) % REGIMES.length;
  const regime = ['bull', 'bull', 'sideways', 'bull'][idx % 4];
  const since = new Date(); since.setDate(since.getDate() - (40 + (idx * 12) % 90));
  const duration_days = Math.floor((Date.now() - since.getTime()) / 86400000);
  const descriptions = {
    bull:     'Markets trending upward with low volatility. Momentum strategies work well.',
    bear:     'Markets trending downward with elevated fear. Capital preservation is key.',
    sideways: 'No clear trend. Range-bound choppy action. Breakout strategies preferred.',
    crisis:   'Extreme volatility and panic. All correlations spike. High uncertainty.',
  };
  return { regime, description: descriptions[regime], since: since.toISOString().slice(0, 10), duration_days };
};

// ── /api/pulse ────────────────────────────────────────────────────────────────
const PULSE_LABELS = [[56, 'Bullish'], [53, 'Mildly Bullish'], [48, 'Neutral'], [45, 'Cautious'], [0, 'Bearish']];
const PULSE_STANCE = { bull: 'Risk-On', bear: 'Risk-Off', sideways: 'Neutral', crisis: 'Defensive' };

export const mockPulse = (horizon = '5d') => {
  const reg = mockRegime();
  const n = UNIVERSE.length;
  const seed = Math.floor(Date.now() / 3600000);          // shifts hourly
  const advancers = 18 + (seed % 20);                      // 18..37
  const decliners = n - advancers;
  const pct_advancing = Math.round((advancers / n) * 1000) / 10;
  const tilted_up = 22 + (seed % 18);                      // 22..39
  const avg_prob_up = 0.5 + ((tilted_up - n / 2) / n) * 0.18;
  const conviction = Math.round(avg_prob_up * 100);
  const conviction_label = PULSE_LABELS.find(([t]) => conviction >= t)[1];
  return {
    horizon,
    conviction,
    conviction_label,
    avg_prob_up: Math.round(avg_prob_up * 1e4) / 1e4,
    tilted_up,
    universe: n,
    breadth: { advancers, decliners, unchanged: 0, pct_advancing },
    leading_sector: { sector: 'Information Technology', avg_change: 1.24 },
    lagging_sector: { sector: 'Metals', avg_change: -0.91 },
    regime: reg.regime,
    stance: PULSE_STANCE[reg.regime] || '—',
  };
};

// ── /api/models ───────────────────────────────────────────────────────────────
export const mockModels = () => ({
  total_stocks: UNIVERSE.length,
  stocks: UNIVERSE.map((m) => {
    const rng = seedRandom(hashStr(m.ticker));
    const best_accuracy = {
      '1d':  +(0.52 + rng() * 0.12).toFixed(4),
      '5d':  +(0.55 + rng() * 0.14).toFixed(4),
      '20d': +(0.58 + rng() * 0.14).toFixed(4),
    };
    return {
      ticker: toApiTicker(m.ticker),
      company_name: m.name,
      sector: m.sector,
      horizons_available: ['1d', '5d', '20d'],
      best_accuracy,
    };
  }),
});

// ── /api/prices ───────────────────────────────────────────────────────────────
export const mockPrices = () => {
  const prices = {};
  for (const m of UNIVERSE) {
    const rng = seedRandom(hashStr(m.ticker + ':price'));
    const base = 200 + rng() * 4500;
    const pct = (rng() - 0.48) * 4;
    prices[toApiTicker(m.ticker)] = {
      price: +(base.toFixed(2)),
      pct_change: +(pct.toFixed(2)),
    };
  }
  return { prices };
};

// ── /api/history/{ticker} ─────────────────────────────────────────────────────
export const mockHistory = (ticker, days = 30) => {
  const apiTicker = String(ticker).toUpperCase();
  const display = toDisplayTicker(apiTicker);
  const meta = META_BY_TICKER[display] || { weight: 1.5 };
  const base = 300 + meta.weight * 220;
  return { ticker: apiTicker, history: priceSeries(apiTicker, days, base) };
};

// ── /api/predict ──────────────────────────────────────────────────────────────
export const mockPredict = ({ ticker, horizon = '1d', model = 'ensemble_clf' }) => {
  const apiTicker = String(ticker).toUpperCase();
  const display = toDisplayTicker(apiTicker);
  const meta = META_BY_TICKER[display] || { name: display, sector: 'Unknown', weight: 1.5 };
  const rng = seedRandom(hashStr(apiTicker + ':' + horizon));
  const probability = +(0.4 + rng() * 0.45).toFixed(4);
  const horizonMul = { '1d': 0.7, '5d': 1.4, '20d': 2.8 }[horizon] || 1;
  const predicted_return = +((probability - 0.5) * 0.06 * horizonMul).toFixed(4);
  const margin = Math.abs(predicted_return) * 0.3 + 0.005;
  const current_price = +(300 + meta.weight * 220 + rng() * 40).toFixed(2);
  const dist = Math.abs(probability - 0.5);
  const signal_strength = dist >= 0.15 ? 'strong' : dist >= 0.08 ? 'moderate' : 'weak';

  return {
    ticker: apiTicker,
    company_name: meta.name,
    sector: meta.sector,
    horizon,
    current_price,
    prediction: {
      direction: probability > 0.5 ? 'UP' : 'DOWN',
      probability,
      predicted_return,
      confidence_lower: +(predicted_return - margin).toFixed(4),
      confidence_upper: +(predicted_return + margin).toFixed(4),
      signal_strength,
    },
    regime: mockRegime().regime,
    model_used: model,
    last_updated: new Date().toISOString(),
    disclaimer: 'Analytical signal for research. Investments are subject to market risks.',
  };
};

// ── /api/explain ──────────────────────────────────────────────────────────────
export const mockExplain = ({ ticker, horizon = '1d', top_n = 15 }) => {
  const apiTicker = String(ticker).toUpperCase();
  const rng = seedRandom(hashStr(apiTicker + ':' + horizon + ':explain'));
  const shuffled = [...FEATURES].sort(() => rng() - 0.5).slice(0, top_n);
  const top_features = shuffled
    .map((f) => {
      const v = (rng() - 0.4) * 0.04;
      return { feature: f, importance: +Math.abs(v).toFixed(6), direction: v > 0 ? 'positive' : 'negative' };
    })
    .sort((a, b) => b.importance - a.importance);
  const top3 = top_features.slice(0, 3).map((f) => f.feature).join(', ');
  const net = top_features.reduce((s, f) => s + (f.direction === 'positive' ? f.importance : -f.importance), 0);
  const dir = net > 0 ? 'upward' : 'downward';
  return {
    ticker: apiTicker,
    horizon,
    top_features,
    interpretation: `The model is biased ${dir} primarily due to: ${top3}. These features had the largest influence on this prediction.`,
  };
};

// ── /api/backtest ─────────────────────────────────────────────────────────────
export const mockBacktest = ({ ticker, horizon = '1d', transaction_cost = 0.001 }) => {
  const apiTicker = String(ticker).toUpperCase();
  const rng = seedRandom(hashStr(apiTicker + ':' + horizon + ':bt'));
  const n = 252;
  const eq = [1.0], bh = [1.0], dates = [];
  const today = new Date();
  const drift = 0.0006 + rng() * 0.0007;
  const bhDrift = 0.0004 + rng() * 0.0004;
  for (let i = 0; i < n; i++) {
    eq.push(eq[eq.length - 1] * (1 + drift + (rng() - 0.5) * 0.012 - transaction_cost * 0.05));
    bh.push(bh[bh.length - 1] * (1 + bhDrift + (rng() - 0.5) * 0.014));
    const d = new Date(today); d.setDate(d.getDate() - (n - i)); dates.push(d.toISOString().slice(0, 10));
  }
  const annual_return = eq[eq.length - 1] - 1;
  const benchmark_annual_return = bh[bh.length - 1] - 1;
  let peak = eq[0], maxDD = 0;
  for (const v of eq) { peak = Math.max(peak, v); maxDD = Math.min(maxDD, (v - peak) / peak); }
  const sharpe = +(0.7 + rng() * 1.6).toFixed(2);
  return {
    ticker: apiTicker,
    horizon,
    metrics: {
      hit_rate: +(0.5 + rng() * 0.12).toFixed(4),
      annual_return: +annual_return.toFixed(4),
      benchmark_annual_return: +benchmark_annual_return.toFixed(4),
      excess_return: +(annual_return - benchmark_annual_return).toFixed(4),
      sharpe_ratio: sharpe,
      max_drawdown: +maxDD.toFixed(4),
      calmar_ratio: +(annual_return / Math.max(0.01, -maxDD)).toFixed(2),
      n_trades: Math.floor(40 + rng() * 80),
      equity_curve: eq.map((v) => +v.toFixed(4)),
      buyhold_curve: bh.map((v) => +v.toFixed(4)),
      dates,
    },
    summary: `The strategy achieves ${(annual_return * 100).toFixed(1)}% annual return with a Sharpe ratio of ${sharpe.toFixed(2)}.`,
  };
};

// ── /api/simulate (Monte Carlo fan) ───────────────────────────────────────────
export const mockSimulate = ({ ticker, horizon = '20d', n_sims = 2000 }) => {
  const apiTicker = String(ticker).toUpperCase();
  const display = toDisplayTicker(apiTicker);
  const meta = META_BY_TICKER[display] || { weight: 1.5 };
  const S0 = 300 + meta.weight * 220;
  const days = { '1d': 1, '5d': 5, '20d': 20 }[horizon] || 20;
  const rng = seedRandom(hashStr(apiTicker + ':mc'));
  const drift = (rng() - 0.45) * 0.012;
  const vol = 0.012 + rng() * 0.012;
  const steps = [], p05 = [], p25 = [], p50 = [], p75 = [], p95 = [];
  for (let t = 0; t <= days; t++) {
    const s = Math.sqrt(t) * vol;
    const m = S0 * Math.exp(drift * t);
    steps.push(t);
    p50.push(+m.toFixed(2));
    p05.push(+(m * Math.exp(-1.64 * s)).toFixed(2));
    p25.push(+(m * Math.exp(-0.67 * s)).toFixed(2));
    p75.push(+(m * Math.exp(0.67 * s)).toFixed(2));
    p95.push(+(m * Math.exp(1.64 * s)).toFixed(2));
  }
  const predicted_return = +(drift * days).toFixed(4);
  const lo = -(0.02 + rng() * 0.06), hi = 0.03 + rng() * 0.08;
  return {
    ticker: apiTicker, horizon, current_price: +S0.toFixed(2), predicted_return,
    n_sims, n_jumps_history: 25 + Math.floor(rng() * 45),
    fan: { steps, p05, p25, p50, p75, p95 },
    metrics: {
      p05: +lo.toFixed(4), p95: +hi.toFixed(4),
      var_95: +(-lo + rng() * 0.02).toFixed(4), cvar_95: +(-lo + 0.03 + rng() * 0.03).toFixed(4),
      prob_up: +(0.5 + rng() * 0.12).toFixed(4),
    },
    summary: `${n_sims.toLocaleString()} Monte-Carlo paths (demo). Over ${horizon}, 90% range [${(lo * 100).toFixed(1)}%, ${(hi * 100).toFixed(1)}%].`,
  };
};

// ── /api/signals (cross-sectional long/short board) ───────────────────────────
export const mockSignals = (horizon = '5d') => {
  const rng = seedRandom(hashStr('signals:' + horizon));
  const scored = UNIVERSE.map((m) => ({ m, s: rng() - 0.5 })).sort((a, b) => b.s - a.s);
  const k = Math.max(1, Math.floor(UNIVERSE.length * 0.2));
  const mk = (arr, side) => arr.map((x, i) => ({
    ticker: toApiTicker(x.m.ticker), rank: i + 1, side,
    score: +x.s.toFixed(4), confidence: +(0.5 + Math.abs(x.s) * 0.45).toFixed(4),
    company_name: x.m.name, sector: x.m.sector, price: +(200 + rng() * 4000).toFixed(2),
  }));
  return {
    horizon, as_of: new Date().toISOString().slice(0, 10), n_universe: UNIVERSE.length,
    longs: mk(scored.slice(0, k), 'LONG'),
    shorts: mk(scored.slice(-k).reverse(), 'SHORT'),
    summary: `Demo market-neutral board (${horizon}).`,
  };
};

// ── /api/news ─────────────────────────────────────────────────────────────────
export const mockNewsSectors = () => ({
  sectors: [
    'Financial Services', 'Information Technology', 'Energy', 'FMCG', 'Healthcare',
    'Materials', 'Consumer Discretionary', 'Communication', 'Capital Goods',
    'Utilities', 'Industrials',
  ],
});

export const mockNews = (sector = 'Financial Services') => {
  const rng = seedRandom(hashStr('news:' + sector));
  const srcs = ['Economic Times', 'Moneycontrol', 'Business Standard', 'LiveMint', 'Reuters'];
  const templates = [
    `${sector} stocks rally as investors turn optimistic`,
    `Top ${sector} picks for the week ahead`,
    `${sector} index outperforms the broader market`,
    `Analysts upgrade key ${sector} names on strong outlook`,
    `${sector} sector faces headwinds amid global cues`,
    `What's really driving the ${sector} move?`,
    `FIIs increase exposure to ${sector} stocks`,
    `${sector}: earnings season preview and what to watch`,
  ];
  const articles = templates.map((t, i) => ({
    headline: t,
    link: 'https://news.google.com',
    source: srcs[Math.floor(rng() * srcs.length)],
    published: new Date(Date.now() - i * 3600 * 1000 * (1 + rng() * 4)).toISOString(),
    summary: `Demo summary. Connect the backend for live ${sector} news.`,
  }));
  return { sector, count: articles.length, articles };
};

// ── /api/optimize_portfolio ───────────────────────────────────────────────────
export const mockOptimize = ({ tickers, horizon = '20d', risk_tolerance = 1.0 }) => {
  const t = tickers.map((x) => String(x).toUpperCase());
  const rng = seedRandom(hashStr(t.join(',') + ':' + horizon + ':' + risk_tolerance));
  const raw = t.map(() => Math.pow(rng() + 0.1, 1.0 + risk_tolerance * 0.5));
  const sum = raw.reduce((a, b) => a + b, 0);
  const allocations = Object.fromEntries(t.map((tk, i) => [tk, +(raw[i] / sum).toFixed(4)]));
  const top = Object.entries(allocations).sort((a, b) => b[1] - a[1])[0];
  return {
    horizon,
    risk_tolerance,
    allocations,
    summary: `Optimized allocation for ${t.length} assets over a ${horizon} horizon. Largest weighting: ${(top[1] * 100).toFixed(1)}% in ${top[0]}.`,
  };
};
