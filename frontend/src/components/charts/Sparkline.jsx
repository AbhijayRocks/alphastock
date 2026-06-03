import React, { useId, useMemo } from 'react';
import { cn } from '../../lib/utils.js';

// Lightweight sparkline — no recharts overhead for inline use in rows/tiles.
export const Sparkline = ({
  data = [],
  width = 96,
  height = 28,
  stroke,        // explicit color overrides auto sign coloring
  strokeWidth = 1.5,
  fill = true,
  className,
  ariaLabel,
}) => {
  const id = useId().replace(/:/g, '');
  const { d, area, color, points } = useMemo(() => {
    if (!data.length) return { d: '', area: '', color: '#64748B', points: [] };
    const ys = data.map((p) => (typeof p === 'number' ? p : p.price ?? p.value ?? 0));
    const min = Math.min(...ys), max = Math.max(...ys);
    const range = max - min || 1;
    const stepX = ys.length > 1 ? width / (ys.length - 1) : 0;
    const pts = ys.map((y, i) => [i * stepX, height - ((y - min) / range) * (height - 4) - 2]);
    const path = pts.map(([x, y], i) => `${i === 0 ? 'M' : 'L'}${x.toFixed(2)},${y.toFixed(2)}`).join(' ');
    const last = ys[ys.length - 1], first = ys[0];
    const auto = last >= first ? '#10B981' : '#F43F5E';
    const area = `${path} L${width},${height} L0,${height} Z`;
    return { d: path, area, color: stroke || auto, points: pts };
  }, [data, width, height, stroke]);

  if (!data.length) return null;
  return (
    <svg
      role="img"
      aria-label={ariaLabel}
      viewBox={`0 0 ${width} ${height}`}
      width={width}
      height={height}
      className={cn('overflow-visible', className)}
    >
      <defs>
        <linearGradient id={`gr-${id}`} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor={color} stopOpacity="0.35" />
          <stop offset="100%" stopColor={color} stopOpacity="0" />
        </linearGradient>
      </defs>
      {fill && <path d={area} fill={`url(#gr-${id})`} />}
      <path d={d} fill="none" stroke={color} strokeWidth={strokeWidth} strokeLinejoin="round" strokeLinecap="round" />
      {points.length > 0 && (
        <circle
          cx={points[points.length - 1][0]} cy={points[points.length - 1][1]}
          r={2.2} fill={color} stroke="#0A0B0F" strokeWidth="1.2"
        />
      )}
    </svg>
  );
};
