import React from 'react';
import { cn } from '../../lib/utils.js';

const tones = {
  ink:   'bg-bg-3 text-ink-2 border-line-muted',
  alpha: 'bg-alpha/10 text-alpha border-alpha/25',
  iris:  'bg-iris/10 text-iris-soft border-iris/25',
  bull:  'bg-bull/10 text-bull border-bull/25',
  bear:  'bg-bear/10 text-bear border-bear/25',
  warn:  'bg-warn/10 text-warn border-warn/25',
  info:  'bg-info/10 text-info border-info/25',
  outline: 'bg-transparent text-ink-3 border-line-muted',
  solid: 'bg-ink-1 text-bg-0 border-transparent',
};

export const Badge = ({ tone = 'ink', size = 'sm', icon: Icon, dot, className, children, ...rest }) => {
  const sizeCls = {
    xs: 'h-5 px-1.5 text-2xs',
    sm: 'h-6 px-2   text-2xs',
    md: 'h-7 px-2.5 text-xs',
  }[size];
  return (
    <span
      className={cn(
        'inline-flex items-center gap-1.5 rounded-md font-medium border uppercase tracking-wider',
        sizeCls, tones[tone], className,
      )}
      {...rest}
    >
      {dot && <span className={cn('w-1.5 h-1.5 rounded-full', `bg-current opacity-80`)} />}
      {Icon && <Icon className="w-3 h-3" />}
      {children}
    </span>
  );
};

export const Pill = ({ children, className, ...rest }) => (
  <span
    className={cn('pill bg-bg-2 text-ink-3 border border-line-muted', className)}
    {...rest}
  >{children}</span>
);
