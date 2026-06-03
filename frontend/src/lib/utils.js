import clsx from 'clsx';
import { twMerge } from 'tailwind-merge';

export const cn = (...args) => twMerge(clsx(args));

// ── Ticker conversion ─────────────────────────────────────────────────────────
// Backend wants file format (RELIANCE_NS); display uses dot form (RELIANCE.NS).
export const toApiTicker     = (t) => String(t).replace('.NS', '_NS').replace('&', '_').replace('-', '_');
export const toDisplayTicker = (t) => String(t).replace('_NS', '.NS');
export const tickerSymbol    = (t) => String(t).replace('.NS', '').replace('_NS', '').replace('M_M', 'M&M');

// ── Number formatters ─────────────────────────────────────────────────────────
const NF = new Intl.NumberFormat('en-IN');
const NF_COMPACT = new Intl.NumberFormat('en-IN', { notation: 'compact', maximumFractionDigits: 2 });

export const fmtInt     = (n) => Number.isFinite(n) ? NF.format(Math.round(n)) : '—';
export const fmtCompact = (n) => Number.isFinite(n) ? NF_COMPACT.format(n) : '—';

export const fmtPrice = (n, { currency = '₹', dp = 2 } = {}) => {
  if (!Number.isFinite(n)) return '—';
  return `${currency}${n.toLocaleString('en-IN', { minimumFractionDigits: dp, maximumFractionDigits: dp })}`;
};

export const fmtPct = (n, { dp = 2, signed = true } = {}) => {
  if (!Number.isFinite(n)) return '—';
  const v = n * 100;
  const sign = signed && v > 0 ? '+' : '';
  return `${sign}${v.toFixed(dp)}%`;
};

export const fmtPctRaw = (v, { dp = 2, signed = true } = {}) => {
  if (!Number.isFinite(v)) return '—';
  const sign = signed && v > 0 ? '+' : '';
  return `${sign}${v.toFixed(dp)}%`;
};

export const fmtSigned = (n, dp = 2) => {
  if (!Number.isFinite(n)) return '—';
  const sign = n > 0 ? '+' : '';
  return `${sign}${n.toFixed(dp)}`;
};

// ── Sign + color helpers ──────────────────────────────────────────────────────
export const signClass = (n) =>
  n > 0 ? 'text-bull' : n < 0 ? 'text-bear' : 'text-ink-3';

export const signBgClass = (n) =>
  n > 0 ? 'bg-bull/10 text-bull' : n < 0 ? 'bg-bear/10 text-bear' : 'bg-bg-3 text-ink-3';

// ── Date helpers ──────────────────────────────────────────────────────────────
export const fmtDate = (d) => {
  try {
    const dt = typeof d === 'string' ? new Date(d) : d;
    return dt.toLocaleDateString('en-IN', { day: '2-digit', month: 'short', year: 'numeric' });
  } catch { return '—'; }
};

export const fmtTime = (d) => {
  try {
    const dt = typeof d === 'string' ? new Date(d) : d;
    return dt.toLocaleTimeString('en-IN', { hour: '2-digit', minute: '2-digit' });
  } catch { return '—'; }
};

export const timeAgo = (d) => {
  try {
    const dt = typeof d === 'string' ? new Date(d) : d;
    const s = Math.floor((Date.now() - dt.getTime()) / 1000);
    if (s < 60) return `${s}s ago`;
    if (s < 3600) return `${Math.floor(s / 60)}m ago`;
    if (s < 86400) return `${Math.floor(s / 3600)}h ago`;
    return `${Math.floor(s / 86400)}d ago`;
  } catch { return '—'; }
};

// ── Misc ──────────────────────────────────────────────────────────────────────
export const clamp = (n, lo, hi) => Math.max(lo, Math.min(hi, n));

export const debounce = (fn, ms = 200) => {
  let t;
  return (...args) => { clearTimeout(t); t = setTimeout(() => fn(...args), ms); };
};

export const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

// Deterministic-ish PRNG (mulberry32) so mock data is stable per ticker
export const seedRandom = (seed) => {
  let a = seed >>> 0;
  return () => {
    a = (a + 0x6D2B79F5) >>> 0;
    let t = a;
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
};

export const hashStr = (s) => {
  let h = 2166136261;
  for (let i = 0; i < s.length; i++) { h ^= s.charCodeAt(i); h = Math.imul(h, 16777619); }
  return h >>> 0;
};
