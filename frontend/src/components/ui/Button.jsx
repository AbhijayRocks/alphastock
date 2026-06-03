import React from 'react';
import { cn } from '../../lib/utils.js';

const variants = {
  primary:   'bg-alpha text-bg-0 hover:bg-alpha-soft active:bg-alpha-deep shadow-soft border-alpha-deep/30',
  iris:      'bg-iris-deep text-white hover:bg-iris active:bg-iris-deep shadow-soft border-iris-deep/40',
  surface:   'bg-bg-2 text-ink-1 hover:bg-bg-3 active:bg-bg-3 border-line-muted hover:border-line-strong',
  ghost:     'bg-transparent text-ink-2 hover:bg-bg-2 hover:text-ink-1 border-transparent',
  outline:   'bg-transparent text-ink-1 hover:bg-bg-2 border-line-muted hover:border-line-strong',
  bull:      'bg-bull/10 text-bull hover:bg-bull/20 border-bull/30',
  bear:      'bg-bear/10 text-bear hover:bg-bear/20 border-bear/30',
  danger:    'bg-bear text-white hover:bg-bear-soft border-bear/40',
};

const sizes = {
  xs: 'h-7  px-2.5 text-xs gap-1.5  rounded-md',
  sm: 'h-8  px-3   text-sm gap-1.5  rounded-md',
  md: 'h-9  px-3.5 text-sm gap-2    rounded-lg',
  lg: 'h-11 px-5   text-md gap-2.5  rounded-lg',
};

export const Button = React.forwardRef(({
  variant = 'surface', size = 'md', className = '',
  as: As = 'button', loading = false, disabled = false,
  leadingIcon: LI, trailingIcon: TI, children, ...rest
}, ref) => {
  return (
    <As
      ref={ref}
      disabled={disabled || loading}
      className={cn(
        'inline-flex items-center justify-center font-medium border whitespace-nowrap',
        'transition-all duration-180 ease-out select-none',
        'disabled:opacity-50 disabled:cursor-not-allowed',
        'focus-visible:shadow-focus-iris',
        sizes[size], variants[variant], className,
      )}
      {...rest}
    >
      {loading ? (
        <span className="inline-block w-3.5 h-3.5 rounded-full border-2 border-current/30 border-t-current animate-spin" />
      ) : LI ? <LI className="w-4 h-4" /> : null}
      {children}
      {TI && !loading ? <TI className="w-4 h-4" /> : null}
    </As>
  );
});
Button.displayName = 'Button';

export const IconButton = React.forwardRef(({
  size = 'md', variant = 'ghost', className = '', children, ...rest
}, ref) => {
  const sizeCls = { xs: 'w-7 h-7', sm: 'w-8 h-8', md: 'w-9 h-9', lg: 'w-11 h-11' }[size];
  return (
    <button
      ref={ref}
      className={cn(
        'inline-flex items-center justify-center rounded-lg border',
        'transition-all duration-180 ease-out',
        'focus-visible:shadow-focus-iris disabled:opacity-50 disabled:cursor-not-allowed',
        sizeCls, variants[variant], className,
      )}
      {...rest}
    >
      {children}
    </button>
  );
});
IconButton.displayName = 'IconButton';
