import React, { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react';
import { AnimatePresence, motion } from 'framer-motion';
import { cn } from '../../lib/utils.js';

const Ctx = createContext(null);
let _id = 0;

export const ToastProvider = ({ children }) => {
  const [items, setItems] = useState([]);

  const remove = useCallback((id) => setItems((xs) => xs.filter((x) => x.id !== id)), []);

  const push = useCallback((t) => {
    const id = ++_id;
    const item = { id, tone: t.tone || 'ink', title: t.title, description: t.description, duration: t.duration ?? 4200 };
    setItems((xs) => [...xs, item]);
    if (item.duration > 0) setTimeout(() => remove(id), item.duration);
  }, [remove]);

  const toast = useMemo(() => ({
    push,
    success: (t) => push({ ...t, tone: 'bull' }),
    error:   (t) => push({ ...t, tone: 'bear' }),
    info:    (t) => push({ ...t, tone: 'iris' }),
    warn:    (t) => push({ ...t, tone: 'warn' }),
  }), [push]);

  return (
    <Ctx.Provider value={toast}>
      {children}
      <div className="fixed bottom-5 right-5 z-[110] flex flex-col gap-2 items-end pointer-events-none">
        <AnimatePresence>
          {items.map((it) => (
            <motion.div
              key={it.id}
              initial={{ opacity: 0, y: 12, scale: 0.96 }}
              animate={{ opacity: 1, y: 0, scale: 1 }}
              exit={{ opacity: 0, x: 24, scale: 0.96 }}
              transition={{ duration: 0.22, ease: [0.22, 0.61, 0.36, 1] }}
              className="pointer-events-auto"
            >
              <div className={cn(
                'min-w-[280px] max-w-[380px] surface-elev px-4 py-3 flex gap-3 items-start',
                'border-l-2',
                it.tone === 'bull' && 'border-l-bull',
                it.tone === 'bear' && 'border-l-bear',
                it.tone === 'warn' && 'border-l-warn',
                it.tone === 'iris' && 'border-l-iris',
              )}>
                <div className="flex-1 min-w-0">
                  {it.title && <div className="text-sm font-semibold text-ink-1 truncate">{it.title}</div>}
                  {it.description && <div className="text-xs text-ink-3 mt-0.5">{it.description}</div>}
                </div>
                <button
                  onClick={() => remove(it.id)}
                  className="w-6 h-6 grid place-items-center rounded-md text-ink-4 hover:text-ink-1 hover:bg-bg-3"
                >
                  <svg viewBox="0 0 16 16" className="w-3.5 h-3.5"><path d="M4 4L12 12M12 4L4 12" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round"/></svg>
                </button>
              </div>
            </motion.div>
          ))}
        </AnimatePresence>
      </div>
    </Ctx.Provider>
  );
};

export const useToast = () => {
  const v = useContext(Ctx);
  if (!v) throw new Error('useToast must be used inside <ToastProvider>');
  return v;
};
