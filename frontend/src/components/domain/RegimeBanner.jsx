import React from 'react';
import { useApi } from '../../hooks/useApi.js';
import { api } from '../../api/client.js';
import { REGIME_META } from '../../data/universe.js';
import { cn } from '../../lib/utils.js';
import { IconActivity } from '../shell/Icons.jsx';

const TONE = {
  bull: { bg: 'from-bull/15 via-bull/0', dot: 'bg-bull', text: 'text-bull', ring: 'border-bull/30' },
  bear: { bg: 'from-bear/15 via-bear/0', dot: 'bg-bear', text: 'text-bear', ring: 'border-bear/30' },
  warn: { bg: 'from-warn/15 via-warn/0', dot: 'bg-warn', text: 'text-warn', ring: 'border-warn/30' },
  ink:  { bg: 'from-iris/10 via-iris/0', dot: 'bg-ink-3', text: 'text-ink-2', ring: 'border-line-strong' },
};

// Map each regime to a desk-level positioning stance — the takeaway an
// investor actually acts on, rather than internal detector mechanics.
const STANCE = {
  bull:     { label: 'Risk-On',   tone: 'text-bull', ring: 'border-bull/30 bg-bull/10' },
  bear:     { label: 'Risk-Off',  tone: 'text-bear', ring: 'border-bear/30 bg-bear/10' },
  sideways: { label: 'Neutral',   tone: 'text-ink-2', ring: 'border-line-strong bg-bg-2' },
  crisis:   { label: 'Defensive', tone: 'text-warn', ring: 'border-warn/30 bg-warn/10' },
  unknown:  { label: '—',         tone: 'text-ink-3', ring: 'border-line-muted bg-bg-2' },
};

// Ordered posture scale; the active regime lights up.
const SCALE = [
  { key: 'bear',     short: 'Bear',     active: 'bg-bear' },
  { key: 'sideways', short: 'Sideways', active: 'bg-ink-3' },
  { key: 'bull',     short: 'Bull',     active: 'bg-bull' },
];

export const RegimeBanner = () => {
  const { data, loading } = useApi(() => api.regime(), []);
  const r = data?.regime || 'unknown';
  const meta = REGIME_META[r] || REGIME_META.unknown;
  const tone = TONE[meta.tone] || TONE.ink;
  const stance = STANCE[r] || STANCE.unknown;
  // Crisis is an overlay on a bearish posture for the scale highlight.
  const scaleKey = r === 'crisis' ? 'bear' : r;

  return (
    <div className={cn(
      'relative overflow-hidden surface px-6 py-5 isolate',
      tone.ring,
    )}>
      <div className={cn('absolute inset-0 bg-gradient-to-br pointer-events-none', tone.bg)} />
      <div className="absolute inset-x-0 -top-px h-px bg-gradient-to-r from-transparent via-line-strong to-transparent" />

      <div className="relative flex items-center justify-between gap-6">
        <div className="flex items-center gap-4 min-w-0">
          <div className={cn(
            'w-12 h-12 grid place-items-center rounded-xl bg-bg-2 border', tone.ring,
          )}>
            <div className="relative">
              <span className={cn('w-2.5 h-2.5 rounded-full', tone.dot)} />
              <span className={cn('absolute inset-[-6px] rounded-full border-2 animate-pulseSoft', tone.ring)} />
            </div>
          </div>
          <div className="min-w-0">
            <div className="flex items-center gap-2 mb-1">
              <span className="eyebrow">Market Regime</span>
              <span className="text-2xs text-ink-5">·</span>
              <span className="text-2xs text-ink-4 inline-flex items-center gap-1">
                <IconActivity className="w-3 h-3" /> Auto-detected
              </span>
            </div>
            <div className="flex items-baseline gap-3">
              <h2 className={cn('font-display font-bold text-2xl', tone.text)}>
                {loading ? '…' : meta.label}
              </h2>
              <span className="text-sm text-ink-3 truncate hidden md:inline">{meta.description}</span>
            </div>
          </div>
        </div>

        <div className="shrink-0 flex items-center gap-6 pr-1">
          {/* Posture scale */}
          <div className="hidden lg:flex items-end gap-1.5">
            {SCALE.map((s) => {
              const isActive = s.key === scaleKey;
              return (
                <div key={s.key} className="flex flex-col items-center gap-1.5">
                  <span className={cn(
                    'h-1.5 w-12 rounded-full transition-colors',
                    isActive ? s.active : 'bg-bg-3',
                  )} />
                  <span className={cn('text-2xs', isActive ? 'text-ink-2 font-medium' : 'text-ink-5')}>{s.short}</span>
                </div>
              );
            })}
          </div>

          <div className="hairline-v h-12 hidden lg:block" />

          {/* Suggested stance */}
          <div className="text-right">
            <div className="eyebrow mb-1.5">Suggested Stance</div>
            <span className={cn(
              'inline-flex items-center px-3 py-1 rounded-lg border font-display font-semibold text-md',
              stance.ring, stance.tone,
            )}>
              {loading ? '…' : stance.label}
            </span>
          </div>
        </div>
      </div>
    </div>
  );
};
