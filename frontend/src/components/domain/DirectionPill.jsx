import React from 'react';
import { cn } from '../../lib/utils.js';
import { IconArrowUp, IconArrowDown } from '../shell/Icons.jsx';

export const DirectionPill = ({ direction, probability, size = 'md', showProb = true, className }) => {
  const up = direction === 'UP';
  const sizeCls = {
    sm: 'h-6 px-2 text-2xs gap-1',
    md: 'h-7 px-2.5 text-xs gap-1.5',
    lg: 'h-8 px-3 text-sm gap-1.5',
  }[size];
  return (
    <span className={cn(
      'inline-flex items-center rounded-md font-semibold border',
      up ? 'bg-bull/10 text-bull border-bull/25' : 'bg-bear/10 text-bear border-bear/25',
      sizeCls, className,
    )}>
      {up ? <IconArrowUp className="w-3 h-3" /> : <IconArrowDown className="w-3 h-3" />}
      {direction}
      {showProb && Number.isFinite(probability) && (
        <span className="opacity-75 font-medium ml-0.5">{(probability * 100).toFixed(0)}%</span>
      )}
    </span>
  );
};

export const SignalStrengthBar = ({ strength, className }) => {
  const map = { strong: 3, moderate: 2, weak: 1 };
  const level = map[strength] || 1;
  return (
    <span className={cn('inline-flex items-end gap-[2px] h-3', className)}>
      {[1, 2, 3].map((i) => (
        <span key={i} className={cn(
          'w-1 rounded-sm',
          i === 1 ? 'h-1.5' : i === 2 ? 'h-2.5' : 'h-3',
          i <= level ? (level === 3 ? 'bg-alpha' : level === 2 ? 'bg-iris' : 'bg-ink-3') : 'bg-line-muted',
        )} />
      ))}
    </span>
  );
};

export const ConfidenceMeter = ({ probability, className }) => {
  const v = Number.isFinite(probability) ? probability : 0.5;
  const distance = Math.abs(v - 0.5);
  // 50% centered, fill outward toward direction
  const widthPct = distance * 200; // 0..100
  const goingUp = v >= 0.5;
  return (
    <div className={cn('relative h-1.5 rounded-full bg-bg-3 overflow-hidden', className)}>
      <div className="absolute inset-y-0 left-1/2 w-px bg-line-strong" />
      <div
        className={cn(
          'absolute inset-y-0 rounded-full transition-[width] duration-500',
          goingUp ? 'left-1/2 bg-bull' : 'right-1/2 bg-bear',
        )}
        style={{ width: `${widthPct.toFixed(2)}%` }}
      />
    </div>
  );
};
