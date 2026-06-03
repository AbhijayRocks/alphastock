import React, { useEffect, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { motion, AnimatePresence } from 'framer-motion';
import { useAuth } from '../../context/AuthContext.jsx';
import { useToast } from '../ui/Toast.jsx';
import { IconUser, IconSettings, IconLogout, IconChevronDown } from './Icons.jsx';
import { cn } from '../../lib/utils.js';

const initials = (name = '', email = '') => {
  const src = (name || email || '?').trim();
  const parts = src.split(/[\s@.]+/).filter(Boolean);
  if (parts.length >= 2) return (parts[0][0] + parts[1][0]).toUpperCase();
  return src.slice(0, 2).toUpperCase();
};

export const UserMenu = () => {
  const { user, logout } = useAuth();
  const toast = useToast();
  const navigate = useNavigate();
  const [open, setOpen] = useState(false);
  const ref = useRef(null);

  useEffect(() => {
    if (!open) return;
    const onClick = (e) => { if (ref.current && !ref.current.contains(e.target)) setOpen(false); };
    const onKey = (e) => { if (e.key === 'Escape') setOpen(false); };
    document.addEventListener('mousedown', onClick);
    document.addEventListener('keydown', onKey);
    return () => { document.removeEventListener('mousedown', onClick); document.removeEventListener('keydown', onKey); };
  }, [open]);

  if (!user) return null;

  const name = user.display_name || user.email?.split('@')[0];

  const doLogout = () => {
    setOpen(false);
    logout();
    toast.info({ title: 'Signed out', description: 'See you next session.' });
  };

  return (
    <div className="relative" ref={ref}>
      <button
        onClick={() => setOpen((v) => !v)}
        className="inline-flex items-center gap-2 h-8 pl-1 pr-2 rounded-lg border border-line-muted bg-bg-1 hover:bg-bg-2 hover:border-line-strong transition-all duration-180"
        aria-label="Account menu"
        aria-expanded={open}
      >
        <span className="w-6 h-6 rounded-md bg-gradient-to-br from-alpha-soft to-alpha-deep grid place-items-center text-2xs font-bold text-bg-0">
          {initials(user.display_name, user.email)}
        </span>
        <span className="hidden md:block text-xs font-semibold text-ink-2 max-w-[120px] truncate">{name}</span>
        <IconChevronDown className={cn('w-3.5 h-3.5 text-ink-4 transition-transform', open && 'rotate-180')} />
      </button>

      <AnimatePresence>
        {open && (
          <motion.div
            initial={{ opacity: 0, y: -6, scale: 0.97 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: -6, scale: 0.97 }}
            transition={{ duration: 0.16, ease: [0.22, 0.61, 0.36, 1] }}
            className="absolute right-0 mt-2 w-60 surface-elev p-1.5 z-50 origin-top-right"
          >
            <div className="px-3 py-2.5 flex items-center gap-2.5">
              <span className="w-9 h-9 rounded-lg bg-gradient-to-br from-alpha-soft to-alpha-deep grid place-items-center text-xs font-bold text-bg-0 shrink-0">
                {initials(user.display_name, user.email)}
              </span>
              <div className="min-w-0">
                <div className="text-sm font-semibold text-ink-1 truncate">{name}</div>
                <div className="text-2xs text-ink-4 truncate">{user.email}</div>
              </div>
            </div>

            <div className="hairline my-1" />

            <button
              onClick={() => { setOpen(false); navigate('/settings'); }}
              className="w-full flex items-center gap-2.5 px-3 h-9 rounded-md text-sm text-ink-2 hover:text-ink-1 hover:bg-bg-2 transition-colors"
            >
              <IconUser className="w-4 h-4 text-ink-4" /> Profile
            </button>
            <button
              onClick={() => { setOpen(false); navigate('/settings'); }}
              className="w-full flex items-center gap-2.5 px-3 h-9 rounded-md text-sm text-ink-2 hover:text-ink-1 hover:bg-bg-2 transition-colors"
            >
              <IconSettings className="w-4 h-4 text-ink-4" /> Settings
            </button>

            <div className="hairline my-1" />

            <button
              onClick={doLogout}
              className="w-full flex items-center gap-2.5 px-3 h-9 rounded-md text-sm text-bear hover:bg-bear/10 transition-colors"
            >
              <IconLogout className="w-4 h-4" /> Sign out
            </button>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
};
