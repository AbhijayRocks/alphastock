import React, { useState, useRef, useEffect } from 'react';
import { cn } from '../../lib/utils.js';

export const Tooltip = ({ content, children, side = 'top', delay = 200, className }) => {
  const [open, setOpen] = useState(false);
  const [pos, setPos] = useState({ x: 0, y: 0 });
  const ref = useRef(null);
  const timer = useRef(null);

  const show = () => {
    timer.current = setTimeout(() => {
      if (ref.current) {
        const r = ref.current.getBoundingClientRect();
        setPos({ x: r.left + r.width / 2, y: side === 'top' ? r.top : r.bottom });
      }
      setOpen(true);
    }, delay);
  };
  const hide = () => { clearTimeout(timer.current); setOpen(false); };

  useEffect(() => () => clearTimeout(timer.current), []);

  if (!content) return children;

  return (
    <>
      <span
        ref={ref}
        onMouseEnter={show}
        onMouseLeave={hide}
        onFocus={show}
        onBlur={hide}
        className="inline-flex"
      >
        {children}
      </span>
      {open && (
        <div
          role="tooltip"
          className={cn(
            'fixed z-[100] pointer-events-none animate-fadeIn',
            'rounded-md bg-bg-3 border border-line-strong shadow-pop px-2.5 py-1.5 text-xs text-ink-1',
            className,
          )}
          style={{
            left: pos.x, top: pos.y,
            transform: side === 'top' ? 'translate(-50%, calc(-100% - 8px))' : 'translate(-50%, 8px)',
          }}
        >
          {content}
        </div>
      )}
    </>
  );
};
