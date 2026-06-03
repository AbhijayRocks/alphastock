import React from 'react';
import { cn } from '../../lib/utils.js';

export const EmptyState = ({ icon: Icon, title, description, action, className }) => (
  <div className={cn('flex flex-col items-center justify-center text-center px-6 py-12 gap-3', className)}>
    {Icon && (
      <div className="relative w-12 h-12 grid place-items-center rounded-xl bg-bg-2 border border-line-muted text-ink-3 mb-1">
        <Icon className="w-5 h-5" />
        <span className="absolute inset-0 rounded-xl bg-sheen pointer-events-none" />
      </div>
    )}
    {title && <h4 className="font-display font-semibold text-md text-ink-1">{title}</h4>}
    {description && <p className="text-sm text-ink-3 max-w-sm">{description}</p>}
    {action && <div className="mt-2">{action}</div>}
  </div>
);

export const ErrorState = ({ title = 'Something went wrong', description, action, className }) => (
  <div className={cn('flex flex-col items-center justify-center text-center px-6 py-12 gap-3', className)}>
    <div className="w-12 h-12 grid place-items-center rounded-xl bg-bear/10 border border-bear/25 text-bear">
      <svg viewBox="0 0 24 24" fill="none" className="w-5 h-5"><path d="M12 9v4M12 17h.01M10.3 3.7L2.6 16a2 2 0 001.7 3h15.4a2 2 0 001.7-3l-7.7-12.3a2 2 0 00-3.4 0z" stroke="currentColor" strokeWidth="1.6" strokeLinejoin="round"/></svg>
    </div>
    <h4 className="font-display font-semibold text-md text-ink-1">{title}</h4>
    {description && <p className="text-sm text-ink-3 max-w-sm">{description}</p>}
    {action && <div className="mt-2">{action}</div>}
  </div>
);
