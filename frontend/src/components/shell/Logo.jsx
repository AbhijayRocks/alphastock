import React from 'react';
import { cn } from '../../lib/utils.js';

// AlphaStock mark — three ascending candlestick bars beneath a bright upward
// trend line that peaks at the tallest bar (the "alpha" — return above the
// market). A single warm-gold gradient is reserved exclusively for this mark.
//
// Variants:
//   <Logo />                 tile mark (default, for app/nav/favicon)
//   <Logo tile={false} />    glyph only, transparent background
//   <Logo monochrome />      single-ink version for print / disabled states
export const Logo = ({ size = 24, className, monochrome = false, tile = true }) => {
  const stroke = monochrome ? '#F1F5F9' : 'url(#as-gold)';
  const barFill = monochrome ? '#475569' : 'url(#as-gold-soft)';
  const peak = monochrome ? '#F1F5F9' : '#FFD478';

  return (
    <span className={cn('inline-flex items-center justify-center shrink-0', className)} aria-label="AlphaStock">
      <svg viewBox="0 0 64 64" width={size} height={size} role="img" aria-hidden="true">
        <defs>
          <linearGradient id="as-gold" x1="8" y1="48" x2="56" y2="14" gradientUnits="userSpaceOnUse">
            <stop offset="0%" stopColor="#B68A2C" />
            <stop offset="45%" stopColor="#F4C45D" />
            <stop offset="100%" stopColor="#FFD478" />
          </linearGradient>
          <linearGradient id="as-gold-soft" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="#F4C45D" stopOpacity="0.55" />
            <stop offset="100%" stopColor="#B68A2C" stopOpacity="0.22" />
          </linearGradient>
          <radialGradient id="as-glow" cx="50%" cy="18%" r="75%">
            <stop offset="0%" stopColor="#F4C45D" stopOpacity="0.20" />
            <stop offset="70%" stopColor="#F4C45D" stopOpacity="0" />
          </radialGradient>
        </defs>

        {tile && (
          <>
            <rect width="64" height="64" rx="15" fill="#10131A" />
            <rect width="64" height="64" rx="15" fill="url(#as-glow)" />
            <rect x="0.75" y="0.75" width="62.5" height="62.5" rx="14.25" fill="none" stroke="#262E40" strokeWidth="1.2" />
          </>
        )}

        {/* baseline */}
        <line x1="13" y1="49" x2="51" y2="49" stroke={monochrome ? '#384358' : '#3A2F1A'} strokeWidth="1" strokeLinecap="round" />

        {/* ascending candlestick bars */}
        <rect x="15.5" y="38" width="6" height="11" rx="2" fill={barFill} />
        <rect x="29"   y="31" width="6" height="18" rx="2" fill={barFill} />
        <rect x="42.5" y="22" width="6" height="27" rx="2" fill={barFill} />

        {/* trend line rising to the peak */}
        <path
          d="M14 43 L24.5 36 L34 30 L45.5 18"
          fill="none"
          stroke={stroke}
          strokeWidth="3.4"
          strokeLinecap="round"
          strokeLinejoin="round"
        />
        {/* peak node = alpha */}
        <circle cx="45.5" cy="18" r="3.4" fill={peak} stroke="#10131A" strokeWidth="1.4" />
      </svg>
    </span>
  );
};

export const Wordmark = ({ className, compact = false }) => (
  <div className={cn('flex items-center gap-2.5 select-none', className)}>
    <Logo size={compact ? 22 : 26} />
    <div className="flex flex-col leading-none">
      <span className="font-display font-bold text-sm tracking-tight text-ink-1">
        Alpha<span className="text-alpha">Stock</span>
      </span>
      {!compact && (
        <span className="text-2xs font-medium tracking-[0.18em] text-ink-4 uppercase mt-0.5">Terminal</span>
      )}
    </div>
  </div>
);

// Horizontal lockup — for headers, presentations, README hero, etc.
export const LogoLockup = ({ size = 40, className }) => (
  <div className={cn('inline-flex items-center gap-3 select-none', className)}>
    <Logo size={size} />
    <span className="font-display font-bold text-2xl tracking-tight text-ink-1">
      Alpha<span className="text-alpha">Stock</span>
    </span>
    <span className="font-display font-medium text-md tracking-tight text-ink-3">Terminal</span>
  </div>
);

// Stacked variant — for splash screens, app icons, login screen.
export const LogoStacked = ({ size = 80, className }) => (
  <div className={cn('inline-flex flex-col items-center gap-3 select-none', className)}>
    <Logo size={size} />
    <span className="font-display font-bold text-xs tracking-[0.2em] uppercase text-ink-2">AlphaStock</span>
  </div>
);
