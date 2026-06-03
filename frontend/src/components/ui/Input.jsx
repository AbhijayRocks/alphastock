import React from 'react';
import { cn } from '../../lib/utils.js';

export const Input = React.forwardRef(({
  className = '', size = 'md', leadingIcon: LI, trailingIcon: TI, trailing,
  invalid = false, ...rest
}, ref) => {
  const sizeCls = {
    sm: 'h-8 text-sm rounded-md',
    md: 'h-9 text-sm rounded-lg',
    lg: 'h-11 text-md rounded-lg',
  }[size];
  return (
    <div className={cn('relative inline-flex items-center w-full')}>
      {LI && <LI className="absolute left-3 w-4 h-4 text-ink-4 pointer-events-none" />}
      <input
        ref={ref}
        className={cn(
          'w-full bg-bg-1 border text-ink-1 placeholder:text-ink-4 transition-all duration-180',
          'focus:bg-bg-2 focus:shadow-focus-iris focus:border-iris/0',
          'disabled:opacity-50 disabled:cursor-not-allowed',
          invalid ? 'border-bear/40' : 'border-line-muted hover:border-line-strong',
          LI ? 'pl-9' : 'pl-3',
          (TI || trailing) ? 'pr-9' : 'pr-3',
          sizeCls, className,
        )}
        {...rest}
      />
      {TI && <TI className="absolute right-3 w-4 h-4 text-ink-4 pointer-events-none" />}
      {trailing && <div className="absolute right-2 inline-flex">{trailing}</div>}
    </div>
  );
});
Input.displayName = 'Input';

export const Select = React.forwardRef(({
  className = '', size = 'md', children, ...rest
}, ref) => {
  const sizeCls = {
    sm: 'h-8 text-sm rounded-md pl-3 pr-8',
    md: 'h-9 text-sm rounded-lg pl-3 pr-8',
    lg: 'h-11 text-md rounded-lg pl-3.5 pr-9',
  }[size];
  return (
    <div className="relative inline-flex w-full">
      <select
        ref={ref}
        className={cn(
          'appearance-none w-full bg-bg-1 border border-line-muted text-ink-1',
          'transition-all duration-180 cursor-pointer',
          'hover:border-line-strong focus:shadow-focus-iris',
          sizeCls, className,
        )}
        {...rest}
      >
        {children}
      </select>
      <svg className="pointer-events-none absolute right-2.5 top-1/2 -translate-y-1/2 w-4 h-4 text-ink-4" viewBox="0 0 16 16" fill="none">
        <path d="M4 6l4 4 4-4" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round"/>
      </svg>
    </div>
  );
});
Select.displayName = 'Select';
