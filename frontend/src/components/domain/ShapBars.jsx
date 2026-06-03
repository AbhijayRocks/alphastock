import React, { useMemo } from 'react';
import { motion } from 'framer-motion';
import { cn } from '../../lib/utils.js';

// SHAP-style horizontal bar list. Positive bars push to the right (toward UP),
// negative bars to the left (toward DOWN). Visually mirrors finance research UIs.
export const ShapBars = ({ features = [], className }) => {
  const max = useMemo(() => Math.max(...features.map((f) => Math.abs(f.importance)), 0.0001), [features]);
  if (!features.length) return null;
  return (
    <ul className={cn('flex flex-col gap-1.5', className)}>
      {features.map((f, i) => {
        const pct = (Math.abs(f.importance) / max) * 100;
        const pos = f.direction === 'positive';
        return (
          <li key={f.feature + i} className="grid grid-cols-[140px_1fr_64px] items-center gap-3 group">
            <span className="text-xs text-ink-2 font-medium truncate text-right group-hover:text-ink-1">{f.feature}</span>
            <div className="relative h-5 bg-bg-2 rounded-md overflow-hidden">
              <div className="absolute inset-y-0 left-1/2 w-px bg-line-strong" />
              <motion.div
                initial={{ width: '0%' }}
                animate={{ width: `${(pct / 2).toFixed(2)}%` }}
                transition={{ duration: 0.6, ease: [0.22, 0.61, 0.36, 1], delay: i * 0.02 }}
                className={cn(
                  'absolute inset-y-0',
                  pos
                    ? 'left-1/2 bg-gradient-to-r from-bull/60 to-bull rounded-r-md'
                    : 'right-1/2 bg-gradient-to-l from-bear/60 to-bear rounded-l-md',
                )}
                style={{ boxShadow: pos ? 'inset 0 0 0 1px rgba(16,185,129,0.3)' : 'inset 0 0 0 1px rgba(244,63,94,0.3)' }}
              />
            </div>
            <span className={cn(
              'text-2xs font-semibold tabular text-right',
              pos ? 'text-bull' : 'text-bear',
            )}>
              {pos ? '+' : '−'}{(Math.abs(f.importance) * 100).toFixed(2)}
            </span>
          </li>
        );
      })}
    </ul>
  );
};
