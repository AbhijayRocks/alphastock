"""
training/validation.py — Honest performance statistics (Tier 0 trust).

The whole point: stop fooling ourselves. A Sharpe from one backtest, picked as
the best of many tries, is biased high. These tools quantify how much to trust it.

  • Information Coefficient (IC) : per-date rank-corr of prediction vs realized
                                   cross-sectional return — the core alpha metric.
  • Probabilistic Sharpe (PSR)   : P(true SR > benchmark), adjusted for skew/kurtosis.
  • Deflated Sharpe (DSR)        : PSR where the benchmark is the EXPECTED MAX Sharpe
                                   under N trials — i.e. penalizes selection bias.

References: Bailey & López de Prado (2014), "The Deflated Sharpe Ratio".
"""

import logging
from typing import Dict, List, Optional

import numpy as np
import pandas as pd
from scipy import stats

logger = logging.getLogger(__name__)
_EULER = 0.5772156649015329


# ── Information Coefficient ─────────────────────────────────────────────────────

def information_coefficient(
    pred: pd.Series, actual: pd.Series, dates: pd.Index, method: str = "spearman"
) -> Dict[str, float]:
    """
    Cross-sectional IC: for each date, correlation between predicted and realized
    returns across stocks. Reports mean IC, IC information-ratio, and t-stat.

    Rule of thumb (daily equity): mean |IC| ~0.02-0.05 is real signal; IC-IR > 0.5
    annualized is good. The t-stat tells you if it's distinguishable from zero.
    """
    df = pd.DataFrame({"pred": np.asarray(pred), "actual": np.asarray(actual), "date": np.asarray(dates)})
    ics = []
    for _, g in df.groupby("date"):
        if g["pred"].nunique() < 3 or g["actual"].nunique() < 3:
            continue
        ic = g["pred"].corr(g["actual"], method=method)
        if np.isfinite(ic):
            ics.append(ic)

    if not ics:
        return {"ic_mean": float("nan"), "ic_std": float("nan"), "ic_ir": float("nan"),
                "ic_tstat": float("nan"), "ic_hit": float("nan"), "n_dates": 0}

    ics = np.array(ics)
    mean, std = float(ics.mean()), float(ics.std(ddof=1)) if len(ics) > 1 else float("nan")
    ir = mean / std if std and np.isfinite(std) and std > 0 else float("nan")
    tstat = ir * np.sqrt(len(ics)) if np.isfinite(ir) else float("nan")
    return {
        "ic_mean":  round(mean, 5),
        "ic_std":   round(std, 5) if np.isfinite(std) else float("nan"),
        "ic_ir":    round(ir, 4) if np.isfinite(ir) else float("nan"),
        "ic_tstat": round(tstat, 3) if np.isfinite(tstat) else float("nan"),
        "ic_hit":   round(float((ics > 0).mean()), 4),   # % of days IC positive
        "n_dates":  len(ics),
    }


# ── Sharpe-ratio statistics ─────────────────────────────────────────────────────

def _sharpe_moments(returns: np.ndarray):
    r = np.asarray(returns, dtype=float)
    r = r[np.isfinite(r)]
    n = r.size
    if n < 8 or r.std(ddof=1) == 0:
        return None
    sr = r.mean() / r.std(ddof=1)                      # per-period Sharpe
    skew = float(stats.skew(r))
    kurt = float(stats.kurtosis(r, fisher=False))      # non-excess kurtosis
    return sr, skew, kurt, n


def probabilistic_sharpe_ratio(returns: np.ndarray, sr_benchmark: float = 0.0) -> float:
    """
    P(true per-period Sharpe > sr_benchmark), correcting for skew & fat tails.
    """
    m = _sharpe_moments(returns)
    if m is None:
        return float("nan")
    sr, skew, kurt, n = m
    denom = np.sqrt(1 - skew * sr + (kurt - 1) / 4.0 * sr ** 2)
    if denom <= 0:
        return float("nan")
    z = (sr - sr_benchmark) * np.sqrt(n - 1) / denom
    return float(stats.norm.cdf(z))


def expected_max_sharpe(sr_trials_std: float, n_trials: int) -> float:
    """
    Expected maximum per-period Sharpe from `n_trials` independent strategies whose
    SR estimates have std `sr_trials_std` (the benchmark for the Deflated Sharpe).
    """
    if n_trials < 2 or sr_trials_std <= 0:
        return 0.0
    z1 = stats.norm.ppf(1 - 1.0 / n_trials)
    z2 = stats.norm.ppf(1 - 1.0 / (n_trials * np.e))
    return sr_trials_std * ((1 - _EULER) * z1 + _EULER * z2)


def deflated_sharpe_ratio(
    returns: np.ndarray, n_trials: int, sr_trials_std: Optional[float] = None
) -> Dict[str, float]:
    """
    Deflated Sharpe Ratio: PSR evaluated against the expected-max Sharpe from
    `n_trials`. DSR > 0.95 means the strategy's Sharpe is very unlikely to be a
    fluke of having tried many configurations.

    If `sr_trials_std` (the spread of SR across the trials you ran) is unknown, we
    approximate it from the single backtest's higher moments — conservative.
    """
    m = _sharpe_moments(returns)
    if m is None:
        return {"sharpe_per_period": float("nan"), "psr_vs_0": float("nan"),
                "sr_benchmark": float("nan"), "dsr": float("nan")}
    sr, skew, kurt, n = m

    if sr_trials_std is None:
        # Approximate SR estimation error (Lo, 2002) as the trial spread proxy
        sr_trials_std = np.sqrt((1 - skew * sr + (kurt - 1) / 4.0 * sr ** 2) / (n - 1))

    sr0 = expected_max_sharpe(sr_trials_std, n_trials)
    return {
        "sharpe_per_period": round(sr, 4),
        "psr_vs_0":          round(probabilistic_sharpe_ratio(returns, 0.0), 4),
        "sr_benchmark":      round(float(sr0), 4),
        "dsr":               round(probabilistic_sharpe_ratio(returns, sr0), 4),
        "n_trials":          n_trials,
    }


def annualize_sharpe(per_period_sharpe: float, periods_per_year: float) -> float:
    """Scale a per-period Sharpe to annualized."""
    return float(per_period_sharpe * np.sqrt(periods_per_year))
