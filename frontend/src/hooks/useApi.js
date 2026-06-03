import { useCallback, useEffect, useRef, useState } from 'react';

// Tiny data-fetching hook. Returns {data, error, loading, refetch}.
// `fn` is a () => Promise<T>. Re-runs when deps change.
export function useApi(fn, deps = [], { enabled = true } = {}) {
  const [state, setState] = useState({ data: null, error: null, loading: enabled });
  const seq = useRef(0);

  const run = useCallback(async () => {
    const my = ++seq.current;
    setState((s) => ({ ...s, loading: true, error: null }));
    try {
      const data = await fn();
      if (my !== seq.current) return;
      setState({ data, error: null, loading: false });
    } catch (error) {
      if (my !== seq.current) return;
      setState({ data: null, error, loading: false });
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps);

  useEffect(() => {
    if (!enabled) { setState({ data: null, error: null, loading: false }); return; }
    run();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [enabled, ...deps]);

  return { ...state, refetch: run };
}

// Lightweight key-shortcut listener.
// keys: 'mod+k', 'g d', '?', '/'
export function useHotkey(combo, handler, { enabled = true } = {}) {
  useEffect(() => {
    if (!enabled) return;
    const combos = Array.isArray(combo) ? combo : [combo];
    const parsed = combos.map((c) => c.split(/\s+/).map((seg) => seg.split('+').map((s) => s.toLowerCase())));
    let chord = [];
    let chordTimer = null;

    const matchSingle = (segs, e) => {
      const keys = segs.map((s) => s);
      const target = keys[keys.length - 1];
      const mods   = keys.slice(0, -1);
      const need = {
        mod:   mods.includes('mod') || mods.includes('cmd') || mods.includes('ctrl'),
        shift: mods.includes('shift'),
        alt:   mods.includes('alt'),
      };
      const key = e.key.toLowerCase();
      if (need.mod && !(e.metaKey || e.ctrlKey)) return false;
      if (!need.mod && (e.metaKey || e.ctrlKey)) return false;
      if (need.shift && !e.shiftKey) return false;
      if (need.alt && !e.altKey) return false;
      return key === target;
    };

    const onKey = (e) => {
      if (e.target?.matches?.('input,textarea,[contenteditable="true"]')) {
        if (e.key !== 'Escape') return;
      }
      for (const segs of parsed) {
        if (segs.length === 1) {
          if (matchSingle(segs[0], e)) { e.preventDefault(); handler(e); return; }
        } else {
          // chord like ['g','d'] — first part is a literal key
          const first = segs[0][0];
          if (chord.length === 0 && e.key.toLowerCase() === first && !e.metaKey && !e.ctrlKey) {
            chord = [first];
            clearTimeout(chordTimer);
            chordTimer = setTimeout(() => { chord = []; }, 900);
            return;
          }
          if (chord.length === 1 && chord[0] === first) {
            const next = segs[1][0];
            if (e.key.toLowerCase() === next && !e.metaKey && !e.ctrlKey) {
              e.preventDefault(); handler(e); chord = []; clearTimeout(chordTimer); return;
            }
            chord = []; clearTimeout(chordTimer);
          }
        }
      }
    };
    window.addEventListener('keydown', onKey);
    return () => { window.removeEventListener('keydown', onKey); clearTimeout(chordTimer); };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [combo, handler, enabled]);
}

// Local prefers-reduced-motion
export function usePrefersReducedMotion() {
  const [v, setV] = useState(false);
  useEffect(() => {
    const m = window.matchMedia('(prefers-reduced-motion: reduce)');
    const on = () => setV(m.matches);
    on(); m.addEventListener?.('change', on);
    return () => m.removeEventListener?.('change', on);
  }, []);
  return v;
}
