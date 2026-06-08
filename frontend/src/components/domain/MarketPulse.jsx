import React from 'react';
import { useApi } from '../../hooks/useApi.js';
import { api } from '../../api/client.js';
import { cn } from '../../lib/utils.js';
import { IconActivity } from '../shell/Icons.jsx';

// Conviction → visual tone. Above midline leans bullish, below leans bearish.
const convictionTone = (c) => (c >= 53 ? 'bull' : c <= 47 ? 'bear' : 'ink');

const TONE = {
  bull: { text: 'text-bull', seg: 'bg-bull', ring: 'border-bull/30', bg: 'from-bull/12 via-bull/0' },
  bear: { text: 'text-bear', seg: 'bg-bear', ring: 'border-bear/30', bg: 'from-bear/12 via-bear/0' },
  ink:  { text: 'text-ink-1', seg: 'bg-iris', ring: 'border-line-strong', bg: 'from-iris/10 via-iris/0' },
};

const STANCE_TONE = {
  'Risk-On': 'text-bull', 'Risk-Off': 'text-bear',
  Defensive: 'text-warn', Neutral: 'text-ink-2',
};

const REGIME_LABEL = { bull: 'Bull', bear: 'Bear', sideways: 'Sideways', crisis: 'Crisis', unknown: '—' };

const pct = (v) => `${v > 0 ? '+' : ''}${Number(v).toFixed(2)}%`;

const SECTORS = 10; // conviction bar segments

const SectorRow = ({ label, move }) => {
  if (!move) return null;
  const up = move.avg_change >= 0;
  return (
    <div className="flex items-center justify-between gap-3 text-xs">
      <span className="text-ink-4">{label}</span>
      <span className="flex items-center gap-1.5 min-w-0">
        <span className={cn('truncate', up ? 'text-ink-2' : 'text-ink-2')}>{move.sector}</span>
        <span className={cn('font-mono tabular-nums font-semibold', up ? 'text-bull' : 'text-bear')}>
          {pct(move.avg_change)}
        </span>
      </span>
    </div>
  );
};

export const MarketPulse = ({ horizon = '5d' }) => {
  const { data, loading } = useApi(() => api.pulse(horizon), [horizon]);

  const conviction = data?.conviction ?? 50;
  const tone = TONE[convictionTone(conviction)];
  const filled = Math.round((conviction / 100) * SECTORS);
  const breadth = data?.breadth || { advancers: 0, decliners: 0, pct_advancing: 0 };
  const advPct = breadth.pct_advancing ?? 0;
  const stance = data?.stance || '—';

  return (
    <div className={cn('relative overflow-hidden surface px-6 py-5 isolate', tone.ring)}>
      <div className={cn('absolute inset-0 bg-gradient-to-br pointer-events-none', tone.bg)} />
      <div className="absolute inset-x-0 -top-px h-px bg-gradient-to-r from-transparent via-line-strong to-transparent" />

      <div className="relative grid gap-6 lg:grid-cols-[minmax(0,1fr)_1px_minmax(0,1.1fr)] lg:gap-8">
        {/* ── Conviction ─────────────────────────────────────────── */}
        <div className="min-w-0">
          <div className="flex items-center gap-2 mb-2.5">
            <span className="eyebrow">Model Conviction</span>
            <span className="text-2xs text-ink-5">·</span>
            <span className="text-2xs text-ink-4 inline-flex items-center gap-1">
              <IconActivity className="w-3 h-3" /> NIFTY-50 · {horizon}
            </span>
          </div>

          <div className="flex items-end gap-3">
            <div className="flex items-baseline gap-1">
              <span className={cn('font-display font-bold text-4xl leading-none tabular-nums', tone.text)}>
                {loading ? '…' : conviction}
              </span>
              <span className="text-sm text-ink-5 font-medium">/100</span>
            </div>
            <span className={cn('font-display font-semibold text-md mb-0.5', tone.text)}>
              {loading ? '' : data?.conviction_label}
            </span>
          </div>

          {/* Segmented conviction bar */}
          <div className="mt-3 flex items-center gap-1">
            {Array.from({ length: SECTORS }).map((_, i) => (
              <span
                key={i}
                className={cn(
                  'h-1.5 flex-1 rounded-full transition-colors',
                  i < filled ? tone.seg : 'bg-bg-3',
                )}
              />
            ))}
          </div>

          <p className="mt-2.5 text-xs text-ink-3">
            <span className={cn('font-semibold', tone.text)}>{loading ? '—' : data?.tilted_up}</span>
            <span className="text-ink-4"> of {data?.universe ?? 50} names tilted up</span>
            <span className="text-ink-5"> · avg P(up) {loading ? '—' : (data?.avg_prob_up ?? 0).toFixed(2)}</span>
          </p>
        </div>

        <div className="hairline-v hidden lg:block" />

        {/* ── Market breadth + sectors ───────────────────────────── */}
        <div className="min-w-0">
          <div className="flex items-center justify-between gap-2 mb-2.5">
            <span className="eyebrow">Market Breadth</span>
            <span className="text-2xs text-ink-4 inline-flex items-center gap-1.5">
              <span className="live-dot" /> live
            </span>
          </div>

          <div className="flex items-center gap-4">
            <div className="flex items-baseline gap-1.5">
              <span className="font-display font-bold text-2xl text-bull tabular-nums">{breadth.advancers}</span>
              <span className="text-bull text-sm">▲</span>
            </div>
            <div className="flex items-baseline gap-1.5">
              <span className="font-display font-bold text-2xl text-bear tabular-nums">{breadth.decliners}</span>
              <span className="text-bear text-sm">▼</span>
            </div>
            <span className="ml-auto text-xs text-ink-3 tabular-nums">
              <span className={cn('font-semibold', advPct >= 50 ? 'text-bull' : 'text-bear')}>{advPct}%</span> advancing
            </span>
          </div>

          {/* Advance/decline proportion bar */}
          <div className="mt-2.5 h-2 w-full rounded-full overflow-hidden bg-bear/30 flex">
            <span className="h-full bg-bull transition-all" style={{ width: `${advPct}%` }} />
          </div>

          <div className="mt-3 space-y-1.5">
            <SectorRow label="Leading" move={data?.leading_sector} />
            <SectorRow label="Lagging" move={data?.lagging_sector} />
          </div>
        </div>
      </div>

      {/* Regime context — folded in, not the headline */}
      <div className="relative mt-4 pt-3 border-t border-line-faint flex items-center gap-2 text-2xs">
        <span className="text-ink-5 uppercase tracking-wider">Regime</span>
        <span className="text-ink-2 font-medium">{REGIME_LABEL[data?.regime] || '—'}</span>
        <span className="text-ink-5">·</span>
        <span className={cn('font-medium', STANCE_TONE[stance] || 'text-ink-3')}>{stance}</span>
      </div>
    </div>
  );
};
