import React, { useEffect, useRef, useState } from 'react';

// Animated number counter — eases from the last shown value to `value` over
// `duration`ms. Across remounts of the same render slot, the next instance
// starts from the previous final value (no "flash from 0") via a module cache
// keyed by `cacheKey`. Omit `cacheKey` to disable persistence.
const LAST = new Map();

export const Counter = ({
  value, from = 0, duration = 700, decimals = 0, prefix = '', suffix = '',
  format = null, className, cacheKey = null,
}) => {
  const startFrom = (() => {
    if (cacheKey && LAST.has(cacheKey)) return LAST.get(cacheKey);
    return Number.isFinite(from) ? from : 0;
  })();

  const [display, setDisplay] = useState(startFrom);
  const rafRef = useRef(null);
  const fromRef = useRef(startFrom);

  useEffect(() => {
    cancelAnimationFrame(rafRef.current);
    const start = fromRef.current;
    const target = Number.isFinite(value) ? value : 0;
    const t0 = performance.now();
    const dur = Math.max(0, duration);

    if (dur === 0) {
      setDisplay(target);
      fromRef.current = target;
      if (cacheKey) LAST.set(cacheKey, target);
      return;
    }

    const step = (t) => {
      const p = Math.min(1, (t - t0) / dur);
      const e = 1 - Math.pow(1 - p, 5);    // ease-out-quint
      const cur = start + (target - start) * e;
      setDisplay(cur);
      if (p < 1) {
        rafRef.current = requestAnimationFrame(step);
      } else {
        fromRef.current = target;
        if (cacheKey) LAST.set(cacheKey, target);
      }
    };
    rafRef.current = requestAnimationFrame(step);
    return () => cancelAnimationFrame(rafRef.current);
  }, [value, duration, cacheKey]);

  const out = format
    ? format(display)
    : `${prefix}${display.toLocaleString('en-IN', { minimumFractionDigits: decimals, maximumFractionDigits: decimals })}${suffix}`;

  return <span className={className}>{out}</span>;
};
