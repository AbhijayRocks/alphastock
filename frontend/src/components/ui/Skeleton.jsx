import React from 'react';
import { cn } from '../../lib/utils.js';

export const Skeleton = ({ className, ...rest }) => (
  <div className={cn('skeleton', className)} {...rest} />
);

export const SkeletonText = ({ lines = 3, className }) => (
  <div className={cn('space-y-2', className)}>
    {Array.from({ length: lines }).map((_, i) => (
      <Skeleton key={i} className={cn('h-3', i === lines - 1 ? 'w-2/3' : 'w-full')} />
    ))}
  </div>
);

export const SkeletonStat = () => (
  <div className="surface px-5 py-4">
    <Skeleton className="h-3 w-20 mb-3" />
    <Skeleton className="h-7 w-32 mb-2" />
    <Skeleton className="h-3 w-24" />
  </div>
);

export const SkeletonRow = ({ cols = 6 }) => (
  <div className="grid items-center gap-3 px-4 py-3 border-b border-line-faint" style={{ gridTemplateColumns: `repeat(${cols}, minmax(0,1fr))` }}>
    {Array.from({ length: cols }).map((_, i) => (
      <Skeleton key={i} className="h-3 w-full" />
    ))}
  </div>
);
