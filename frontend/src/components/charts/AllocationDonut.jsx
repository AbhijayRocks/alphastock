import React, { useState } from 'react';
import { PieChart, Pie, Cell, ResponsiveContainer } from 'recharts';
import { SECTOR_COLOR, META_BY_TICKER } from '../../data/universe.js';
import { tickerSymbol, toDisplayTicker, cn } from '../../lib/utils.js';

const COLORS = ['#F4C45D', '#818CF8', '#34D399', '#38BDF8', '#FB7185', '#FBBF24', '#A78BFA', '#22D3EE', '#FB923C', '#4ADE80', '#F472B6'];

export const AllocationDonut = ({ allocations = {}, height = 260 }) => {
  const [active, setActive] = useState(null);
  const items = Object.entries(allocations)
    .filter(([, w]) => w > 0.001)
    .sort((a, b) => b[1] - a[1])
    .map(([t, w], i) => {
      const display = toDisplayTicker(t);
      return {
        name: tickerSymbol(display),
        ticker: display,
        sector: META_BY_TICKER[display]?.sector || '—',
        value: w,
        color: SECTOR_COLOR[META_BY_TICKER[display]?.sector] || COLORS[i % COLORS.length],
      };
    });

  if (!items.length) return null;
  const hovered = active !== null ? items[active] : items[0];

  return (
    <div className="relative">
      <ResponsiveContainer width="100%" height={height}>
        <PieChart>
          <Pie
            data={items}
            dataKey="value"
            cx="50%" cy="50%"
            innerRadius={Math.floor(height * 0.32)}
            outerRadius={Math.floor(height * 0.45)}
            stroke="#0A0B0F"
            strokeWidth={2}
            startAngle={90}
            endAngle={-270}
            paddingAngle={1.4}
            onMouseEnter={(_, i) => setActive(i)}
            onMouseLeave={() => setActive(null)}
          >
            {items.map((it, i) => (
              <Cell
                key={i}
                fill={it.color}
                fillOpacity={active === null || active === i ? 1 : 0.35}
                style={{ transition: 'fill-opacity 180ms' }}
              />
            ))}
          </Pie>
        </PieChart>
      </ResponsiveContainer>

      {/* Center label */}
      <div className="absolute inset-0 grid place-items-center pointer-events-none">
        <div className="text-center">
          <div className="eyebrow">{hovered.name}</div>
          <div className="font-display font-bold text-2xl text-ink-1 tabular">
            {(hovered.value * 100).toFixed(1)}%
          </div>
          <div className="text-2xs text-ink-4 truncate max-w-[140px]">{hovered.sector}</div>
        </div>
      </div>
    </div>
  );
};

export const AllocationLegend = ({ allocations = {}, className }) => {
  const items = Object.entries(allocations)
    .filter(([, w]) => w > 0.001)
    .sort((a, b) => b[1] - a[1])
    .map(([t, w], i) => {
      const display = toDisplayTicker(t);
      const meta = META_BY_TICKER[display];
      return {
        ticker: display,
        sym: tickerSymbol(display),
        name: meta?.name || display,
        sector: meta?.sector || '—',
        weight: w,
        color: SECTOR_COLOR[meta?.sector] || COLORS[i % COLORS.length],
      };
    });

  return (
    <ul className={cn('divide-y divide-line-faint', className)}>
      {items.map((it) => (
        <li key={it.ticker} className="flex items-center gap-3 py-2.5">
          <span className="w-2.5 h-2.5 rounded-sm" style={{ background: it.color }} />
          <div className="flex-1 min-w-0">
            <div className="text-sm font-semibold text-ink-1 truncate">{it.sym}</div>
            <div className="text-2xs text-ink-4 truncate">{it.sector}</div>
          </div>
          <div className="text-right">
            <div className="text-sm font-semibold text-ink-1 tabular">{(it.weight * 100).toFixed(1)}%</div>
            <div className="w-24 h-1 rounded-full bg-bg-3 overflow-hidden mt-1">
              <div className="h-full rounded-full" style={{ width: `${Math.min(100, it.weight * 100 * 3.5)}%`, background: it.color }} />
            </div>
          </div>
        </li>
      ))}
    </ul>
  );
};
