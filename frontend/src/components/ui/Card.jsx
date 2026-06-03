import React from 'react';
import { cn } from '../../lib/utils.js';

export const Card = React.forwardRef(({
  className = '', interactive = false, glow = null, as: As = 'div', children, ...rest
}, ref) => {
  const glowCls = glow === 'alpha' ? 'before:bg-alpha-radial'
                : glow === 'iris'  ? 'before:bg-iris-radial' : '';
  return (
    <As
      ref={ref}
      className={cn(
        'relative isolate surface',
        glow && 'overflow-hidden before:absolute before:inset-0 before:opacity-60 before:pointer-events-none',
        glowCls,
        interactive && 'transition-all duration-220 ease-out hover:border-line-strong hover:shadow-elev',
        className,
      )}
      {...rest}
    >
      <div className="relative z-10 h-full">{children}</div>
    </As>
  );
});
Card.displayName = 'Card';

export const CardHeader = ({ className, eyebrow, title, subtitle, action, children }) => (
  <div className={cn('flex items-start justify-between gap-4 px-5 pt-4 pb-3', className)}>
    <div className="min-w-0 flex-1">
      {eyebrow && <div className="eyebrow mb-1.5">{eyebrow}</div>}
      {title && <h3 className="font-display font-semibold text-md text-ink-1 truncate">{title}</h3>}
      {subtitle && <p className="text-xs text-ink-3 mt-0.5">{subtitle}</p>}
      {children}
    </div>
    {action && <div className="flex items-center gap-2 shrink-0">{action}</div>}
  </div>
);

export const CardBody = ({ className, children, padding = true }) => (
  <div className={cn(padding && 'px-5 pb-5', className)}>{children}</div>
);

export const CardDivider = ({ className }) => (
  <div className={cn('hairline mx-5', className)} />
);
