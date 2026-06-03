import React from 'react';
import { Counter } from './Counter.jsx';
import { Sparkline } from '../charts/Sparkline.jsx';
import { cn } from '../../lib/utils.js';

// Premium KPI tile with eyebrow + big number + delta + optional sparkline.
export const StatTile = ({
  eyebrow, label, value, valueSuffix, valuePrefix, valueDecimals = 0,
  delta,            // { value, label, sign }   sign = +/-/0  (auto from value if omitted)
  spark,            // [{ price }] series
  tone = 'ink',     // 'ink' | 'alpha' | 'bull' | 'bear' | 'iris'
  icon: Icon, hint, className, loading = false,
}) => {
  const toneRing = {
    ink:   'before:bg-transparent',
    alpha: 'before:bg-alpha-radial',
    iris:  'before:bg-iris-radial',
    bull:  'before:bg-bull/0',
    bear:  'before:bg-bear/0',
  }[tone] || '';

  const sparkColor = {
    alpha: '#F4C45D', iris: '#818CF8', bull: '#10B981', bear: '#F43F5E', ink: '#94A3B8',
  }[tone];

  const sign = delta?.sign ?? (delta && Number.isFinite(delta.value) ? Math.sign(delta.value) : 0);
  const deltaCls = sign > 0 ? 'text-bull' : sign < 0 ? 'text-bear' : 'text-ink-3';

  return (
    <div className={cn(
      'relative isolate overflow-hidden surface px-5 py-4 flex flex-col gap-2.5 min-h-[120px]',
      'transition-all duration-220 ease-out hover:border-line-strong hover:shadow-elev',
      tone !== 'ink' && 'before:absolute before:inset-0 before:opacity-60 before:pointer-events-none',
      toneRing,
      className,
    )}>
      <div className="relative z-10 flex items-center justify-between gap-2">
        <div className="eyebrow">{eyebrow || label}</div>
        {Icon && (
          <span className="w-6 h-6 grid place-items-center rounded-md bg-bg-2 text-ink-3 border border-line-muted">
            <Icon className="w-3.5 h-3.5" />
          </span>
        )}
      </div>
      <div className="relative z-10 flex items-end justify-between gap-3">
        <div className="min-w-0">
          {loading ? (
            <div className="skeleton h-8 w-28" />
          ) : (
            <div className="font-display font-semibold text-3xl text-ink-1 tabular leading-none">
              {valuePrefix}<Counter value={value} decimals={valueDecimals} />{valueSuffix}
            </div>
          )}
          {delta && (
            <div className={cn('mt-2 text-xs font-medium flex items-center gap-1.5 tabular', deltaCls)}>
              <span aria-hidden="true">{sign > 0 ? '▲' : sign < 0 ? '▼' : '◆'}</span>
              <span>{delta.value > 0 && delta.sign !== 0 ? '+' : ''}{delta.value?.toFixed?.(2) ?? delta.value}</span>
              {delta.label && <span className="text-ink-4 font-normal normal-case tracking-normal">· {delta.label}</span>}
            </div>
          )}
        </div>
        {spark && spark.length > 0 && (
          <Sparkline data={spark} stroke={sparkColor} width={84} height={32} />
        )}
      </div>
      {hint && <div className="relative z-10 text-2xs text-ink-4 mt-1">{hint}</div>}
    </div>
  );
};
