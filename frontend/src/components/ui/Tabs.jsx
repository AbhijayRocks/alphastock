import React from 'react';
import { motion } from 'framer-motion';
import { cn } from '../../lib/utils.js';

export const SegmentedControl = ({ value, onChange, options, size = 'md', className }) => {
  const sizeCls = {
    sm: 'h-7 text-xs p-0.5',
    md: 'h-8 text-sm p-1',
    lg: 'h-10 text-sm p-1',
  }[size];
  return (
    <div
      role="tablist"
      className={cn(
        'relative inline-flex items-center bg-bg-2 border border-line-muted rounded-lg',
        sizeCls, className,
      )}
    >
      {options.map((opt) => {
        const active = opt.value === value;
        return (
          <button
            key={opt.value}
            role="tab"
            aria-selected={active}
            onClick={() => onChange?.(opt.value)}
            className={cn(
              'relative inline-flex items-center justify-center gap-1.5 px-3 rounded-md font-medium',
              'transition-colors duration-180 ease-out',
              active ? 'text-ink-1' : 'text-ink-3 hover:text-ink-1',
            )}
            style={{ height: '100%' }}
          >
            {active && (
              <motion.span
                layoutId={`seg-${options.map((o) => o.value).join('-')}`}
                className="absolute inset-0 rounded-md bg-bg-3 border border-line-strong shadow-soft"
                transition={{ type: 'spring', stiffness: 380, damping: 32 }}
              />
            )}
            <span className="relative">{opt.label}</span>
          </button>
        );
      })}
    </div>
  );
};

export const Tabs = ({ tabs, value, onChange, className }) => (
  <div className={cn('border-b border-line-muted', className)}>
    <div className="flex items-end gap-1" role="tablist">
      {tabs.map((t) => {
        const active = t.value === value;
        return (
          <button
            key={t.value}
            role="tab"
            aria-selected={active}
            onClick={() => onChange?.(t.value)}
            className={cn(
              'relative px-3 py-2.5 text-sm font-medium transition-colors duration-180',
              active ? 'text-ink-1' : 'text-ink-3 hover:text-ink-1',
            )}
          >
            <span className="inline-flex items-center gap-1.5">{t.icon ? <t.icon className="w-4 h-4" /> : null}{t.label}</span>
            {active && (
              <motion.span
                layoutId="tabs-underline"
                className="absolute left-0 right-0 -bottom-px h-px bg-alpha"
                transition={{ type: 'spring', stiffness: 380, damping: 32 }}
              />
            )}
          </button>
        );
      })}
    </div>
  </div>
);
