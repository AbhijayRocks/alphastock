import React from 'react';
import { Link } from 'react-router-dom';
import { META_BY_TICKER, SECTOR_COLOR } from '../../data/universe.js';
import { tickerSymbol, cn } from '../../lib/utils.js';

export const TickerCell = ({ ticker, name, sector, size = 'md', subdued = false, className }) => {
  const display = (ticker || '').replace('_NS', '.NS');
  const meta = META_BY_TICKER[display];
  const sym = tickerSymbol(display);
  const initials = sym.slice(0, 3);
  const color = SECTOR_COLOR[sector || meta?.sector] || '#94A3B8';

  const sizes = {
    sm: { box: 'w-7 h-7 text-2xs', name: 'text-sm', sub: 'text-2xs' },
    md: { box: 'w-9 h-9 text-xs', name: 'text-sm', sub: 'text-xs' },
    lg: { box: 'w-12 h-12 text-sm', name: 'text-md', sub: 'text-xs' },
  }[size];

  return (
    <Link
      to={`/analysis?ticker=${encodeURIComponent(display)}`}
      className={cn('group flex items-center gap-3 min-w-0', className)}
    >
      <span
        className={cn(
          'relative grid place-items-center rounded-md font-mono font-semibold shrink-0',
          'border border-line-muted bg-bg-2 group-hover:border-line-strong transition-colors',
          sizes.box,
        )}
        style={{ color }}
      >
        <span aria-hidden="true" className="absolute inset-0 rounded-md bg-sheen pointer-events-none" />
        <span className="relative tabular tracking-tight">{initials}</span>
      </span>
      <div className="min-w-0">
        <div className={cn('font-display font-semibold text-ink-1 truncate leading-tight group-hover:text-alpha transition-colors', sizes.name)}>
          {sym}
        </div>
        <div className={cn('text-ink-4 truncate leading-tight', sizes.sub, subdued && 'opacity-70')}>
          {name || meta?.name || display}
        </div>
      </div>
    </Link>
  );
};
