import React, { useMemo } from 'react';
import { useNavigate } from 'react-router-dom';
import { useApi } from '../../hooks/useApi.js';
import { api } from '../../api/client.js';
import { UNIVERSE, META_BY_TICKER } from '../../data/universe.js';
import { Sparkline } from '../charts/Sparkline.jsx';
import { IconArrowUp, IconArrowDown } from './Icons.jsx';
import { toApiTicker, toDisplayTicker, tickerSymbol, hashStr, seedRandom, cn } from '../../lib/utils.js';

// Generate stable mini sparkline data without round-trips per row.
const miniSeries = (display) => {
  const rng = seedRandom(hashStr(display + ':tape'));
  let v = 100; const out = [];
  for (let i = 0; i < 30; i++) { v *= 1 + (rng() - 0.5) * 0.03; out.push({ price: v }); }
  return out;
};

export const TickerTape = () => {
  const { data, loading } = useApi(() => api.prices(), []);
  const navigate = useNavigate();

  const rows = useMemo(() => {
    if (!data?.prices) return [];
    return Object.entries(data.prices).map(([apiTicker, p]) => ({
      apiTicker,
      display: toDisplayTicker(apiTicker),
      price: p.price,
      pct: p.pct_change,
    })).sort((a, b) => (META_BY_TICKER[b.display]?.weight || 0) - (META_BY_TICKER[a.display]?.weight || 0));
  }, [data]);

  if (loading && rows.length === 0) {
    return <div className="h-9 border-b border-line-faint bg-bg-1/60" />;
  }
  if (rows.length === 0) return null;
  const doubled = [...rows, ...rows];

  return (
    <div className="h-9 border-b border-line-faint bg-bg-1/60 overflow-hidden relative group">
      <div className="absolute inset-0 pointer-events-none z-10"
        style={{ background: 'linear-gradient(90deg, #0A0B0F 0%, transparent 6%, transparent 94%, #0A0B0F 100%)' }} />
      <div className="flex items-center h-full whitespace-nowrap animate-tickerScroll group-hover:[animation-play-state:paused]">
        {doubled.map((r, i) => {
          const pos = r.pct >= 0;
          return (
            <button
              key={`${r.apiTicker}-${i}`}
              onClick={() => navigate(`/analysis?ticker=${encodeURIComponent(r.display)}`)}
              className="inline-flex items-center gap-2 px-3.5 h-full text-xs hover:bg-bg-2/60 transition-colors group/row"
            >
              <span className="font-semibold tabular text-ink-2 group-hover/row:text-ink-1">{tickerSymbol(r.display)}</span>
              <span className="tabular text-ink-3">₹{r.price?.toLocaleString('en-IN', { maximumFractionDigits: 0 })}</span>
              <span className={cn('inline-flex items-center gap-0.5 tabular font-medium', pos ? 'text-bull' : 'text-bear')}>
                {pos ? <IconArrowUp className="w-2.5 h-2.5" /> : <IconArrowDown className="w-2.5 h-2.5" />}
                {pos ? '+' : ''}{r.pct.toFixed(2)}%
              </span>
              <Sparkline data={miniSeries(r.display)} stroke={pos ? '#10B981' : '#F43F5E'} width={36} height={14} fill={false} />
              <span className="w-px h-3.5 bg-line-muted opacity-50 ml-1" />
            </button>
          );
        })}
      </div>
    </div>
  );
};
