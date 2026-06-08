"""
training/labeling.py — Triple-barrier labeling (López de Prado).

WHY (vs fixed-horizon return sign):
  Fixed-horizon labels ("return 5 days from now") ignore the PATH — they treat a
  stock that ran +8% then collapsed to +0.5% the same as one that drifted to
  +0.5%. Real trading exits at a take-profit, a stop-loss, or a time limit. The
  triple-barrier method labels each entry by WHICH of three barriers it hits first:

    • upper (take-profit)  = +pt · σ · √H     → realized return at touch
    • lower (stop-loss)    = −sl · σ · √H     → realized return at touch
    • vertical (time-out)  = at H days        → realized return at H

  The barriers are VOLATILITY-SCALED (σ from recent realized vol), so a calm stock
  and a wild one get fair, comparable targets. We return the realized return at the
  first touch — a cleaner, less noisy regression/ranking target than the raw
  fixed-horizon return.
"""

from typing import Optional

import numpy as np
import pandas as pd


def triple_barrier_full(
    close: pd.Series,
    horizon: int = 5,
    pt: float = 1.0,
    sl: float = 1.0,
    vol_window: int = 20,
    vol: Optional[pd.Series] = None,
) -> pd.DataFrame:
    """
    Triple-barrier labels: realized return at first touch + HOLDING PERIOD (days
    until the touch). The holding period feeds sample-uniqueness weighting — a
    label that resolves in 1 day overlaps with fewer others than one held the full
    horizon, so it carries more independent information.

    Returns a DataFrame with columns ['target_tb', 'tb_days'] indexed like `close`.
    """
    c = close.to_numpy(dtype=float)
    n = c.size
    if vol is None:
        dv = close.pct_change().rolling(vol_window).std().to_numpy()
    else:
        dv = np.asarray(vol, dtype=float)

    ret = np.full(n, np.nan)
    days = np.full(n, np.nan)
    H = int(horizon)
    sqrtH = np.sqrt(H)

    for i in range(n - 1):
        sig = dv[i]
        if not np.isfinite(sig) or sig <= 0:
            continue
        up, dn = pt * sig * sqrtH, -sl * sig * sqrtH
        end = min(i + H, n - 1)
        ci = c[i]
        touched, held = np.nan, end - i
        for j in range(i + 1, end + 1):
            r = c[j] / ci - 1.0
            if r >= up or r <= dn:
                touched, held = r, j - i
                break
        if np.isnan(touched):
            touched = c[end] / ci - 1.0          # vertical (time) barrier
        ret[i] = touched
        days[i] = held

    return pd.DataFrame({"target_tb": ret, "tb_days": days}, index=close.index)


def triple_barrier_return(close: pd.Series, horizon: int = 5, pt: float = 1.0,
                          sl: float = 1.0, vol_window: int = 20,
                          vol: Optional[pd.Series] = None) -> pd.Series:
    """Realized return at the first barrier touch (back-compat wrapper)."""
    return triple_barrier_full(close, horizon, pt, sl, vol_window, vol)["target_tb"]


if __name__ == "__main__":
    rng = np.random.default_rng(0)
    px = pd.Series(100 * np.cumprod(1 + rng.normal(0.0003, 0.015, 500)))
    tb = triple_barrier_return(px, horizon=5, pt=1.0, sl=1.0)
    print("triple-barrier target: mean", round(float(tb.mean()), 5),
          "| std", round(float(tb.std()), 5), "| n", int(tb.notna().sum()))
