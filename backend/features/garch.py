"""
features/garch.py — Dependency-free GARCH(1,1) volatility model.

WHY A HAND-ROLLED GARCH (no `arch` library):
  The `arch` package is Cython-based and won't build on Python 3.14 (same wall
  as numba/shap). GARCH(1,1) is small enough to estimate directly with
  scipy.optimize (already installed), so we avoid the dependency entirely.

WHAT GARCH BUYS US (volatility, NOT direction):
  Returns are ~unpredictable, but volatility *clusters* — calm follows calm,
  turbulence follows turbulence. GARCH(1,1) captures that autocorrelation and
  mean-reversion, giving a FORWARD-looking conditional volatility forecast.

  We use it three ways:
    1. Honest prediction intervals   (api/model_registry.predict)
    2. A forward-vol model feature    (features/pipeline)
    3. Volatility-targeted sizing      (training/backtest)

THE MODEL:
  r_t = mu + e_t,   e_t = sigma_t * z_t,   z_t ~ N(0,1)
  sigma_t^2 = omega + alpha * e_{t-1}^2 + beta * sigma_{t-1}^2

  We use VARIANCE TARGETING: omega = (1 - alpha - beta) * Var(r), which fixes
  the long-run variance to the sample variance and leaves only (alpha, beta) to
  estimate. This is faster and far more numerically stable than free omega.

CAUSALITY / LEAKAGE:
  sigma_t is the conditional variance for day t given information up to t-1, so
  using it as a feature aligned to row t introduces no look-ahead of returns.
  (The parameters alpha/beta are fit once on the whole series — a mild, standard
  simplification; GARCH parameters are very stable across sub-samples.)
"""

import logging
from typing import Dict, Optional, Tuple

import numpy as np
import pandas as pd
from scipy.optimize import minimize

logger = logging.getLogger(__name__)

# Returns are scaled by this for numerical conditioning during optimization,
# then unscaled on the way out (standard practice — see arch's own docs).
_SCALE = 100.0
_MIN_OBS = 100          # need a reasonable sample to estimate GARCH
_EPS = 1e-12


def _clean_returns(returns: pd.Series | np.ndarray) -> np.ndarray:
    """Return a finite, demeaned, ×100-scaled 1-D array of returns."""
    r = np.asarray(returns, dtype=float)
    r = r[np.isfinite(r)]
    if r.size == 0:
        return r
    r = (r - r.mean()) * _SCALE
    return r


def _garch_recursion(omega: float, alpha: float, beta: float,
                     r: np.ndarray, var0: float) -> np.ndarray:
    """Filter the conditional-variance path sigma_t^2 for scaled returns r."""
    n = r.size
    sigma2 = np.empty(n)
    sigma2[0] = var0
    r2 = r * r
    for t in range(1, n):
        sigma2[t] = omega + alpha * r2[t - 1] + beta * sigma2[t - 1]
    return np.maximum(sigma2, _EPS)


def fit_garch_11(returns: pd.Series | np.ndarray) -> Optional[Dict[str, float]]:
    """
    Fit GARCH(1,1) with variance targeting via Gaussian MLE.

    Returns a dict {omega, alpha, beta, persistence, uncond_vol, last_var} in the
    SCALED (×100) space, or None if the series is too short / degenerate.
    `last_var` is sigma^2 for the final in-sample step (used to forecast forward).
    """
    r = _clean_returns(returns)
    if r.size < _MIN_OBS:
        return None

    var = float(np.var(r))
    if var <= _EPS:
        return None

    def neg_loglik(theta: np.ndarray) -> float:
        alpha, beta = theta
        if alpha < 0 or beta < 0 or (alpha + beta) >= 0.999:
            return 1e12
        omega = (1.0 - alpha - beta) * var
        sigma2 = _garch_recursion(omega, alpha, beta, r, var)
        # 0.5 * sum( log(2π) + log(sigma2) + r^2/sigma2 )
        ll = -0.5 * np.sum(np.log(2 * np.pi) + np.log(sigma2) + (r * r) / sigma2)
        return -ll if np.isfinite(ll) else 1e12

    try:
        res = minimize(
            neg_loglik,
            x0=np.array([0.08, 0.90]),          # typical equity GARCH start
            method="L-BFGS-B",
            bounds=[(0.0, 0.5), (0.0, 0.999)],
        )
        alpha, beta = float(res.x[0]), float(res.x[1])
    except Exception as e:
        logger.debug(f"GARCH optimisation failed: {e}")
        return None

    if not np.isfinite(alpha) or not np.isfinite(beta) or (alpha + beta) >= 0.999:
        return None

    omega = (1.0 - alpha - beta) * var
    sigma2 = _garch_recursion(omega, alpha, beta, r, var)

    return {
        "omega":      omega,
        "alpha":      alpha,
        "beta":       beta,
        "persistence": alpha + beta,
        "uncond_vol": float(np.sqrt(var)),       # scaled
        "last_var":   float(sigma2[-1]),         # scaled sigma^2 of last obs
        "last_ret2":  float(r[-1] ** 2),         # scaled r_t^2 of last obs
    }


def conditional_vol_daily(returns: pd.Series) -> pd.Series:
    """
    Causal per-day conditional volatility (std of daily returns), aligned to the
    input index. Falls back to a rolling-std estimate if GARCH can't be fit.

    Used as a forward-looking volatility FEATURE.
    """
    s = pd.Series(returns).astype(float)
    valid = s.dropna()
    fit = fit_garch_11(valid.values)

    if fit is None:
        # Fallback: 20-day realized vol (still useful, just not forward-looking)
        return s.rolling(20).std()

    omega, alpha, beta = fit["omega"], fit["alpha"], fit["beta"]
    r = _clean_returns(valid.values)
    var0 = fit["uncond_vol"] ** 2
    sigma2 = _garch_recursion(omega, alpha, beta, r, var0)
    vol = np.sqrt(sigma2) / _SCALE               # unscale back to return units

    out = pd.Series(np.nan, index=s.index)
    out.loc[valid.index] = vol
    return out


def forecast_vol(returns: pd.Series | np.ndarray, horizon_days: int = 1) -> Optional[float]:
    """
    Forecast volatility (std of returns) over the next `horizon_days`.

    1-step: sigma^2_{T+1} = omega + alpha*r_T^2 + beta*sigma^2_T
    Multi-step: sqrt-of-time scaling of the 1-day forecast (standard, robust).

    Returns the volatility in RETURN units (e.g. 0.015 = 1.5% daily), or None.
    """
    fit = fit_garch_11(returns)
    if fit is None:
        r = _clean_returns(returns)
        if r.size == 0:
            return None
        sigma_1d = float(np.std(r)) / _SCALE      # fallback realized
    else:
        next_var = fit["omega"] + fit["alpha"] * fit["last_ret2"] + fit["beta"] * fit["last_var"]
        sigma_1d = float(np.sqrt(max(next_var, _EPS))) / _SCALE

    return sigma_1d * np.sqrt(max(1, horizon_days))


if __name__ == "__main__":
    # Quick self-test on a synthetic vol-clustering series
    rng = np.random.default_rng(0)
    n = 2000
    sig = np.empty(n); sig[0] = 0.01
    r = np.empty(n)
    for t in range(1, n):
        sig[t] = np.sqrt(1e-6 + 0.08 * r[t-1]**2 + 0.90 * sig[t-1]**2)
        r[t] = sig[t] * rng.standard_normal()
    s = pd.Series(r)
    fit = fit_garch_11(s.values)
    print("fit:", {k: round(v, 4) for k, v in fit.items()})
    print("1d forecast vol:", round(forecast_vol(s.values, 1), 5))
    print("5d forecast vol:", round(forecast_vol(s.values, 5), 5))
    cv = conditional_vol_daily(s)
    print("cond vol tail:", cv.dropna().tail(3).round(5).tolist())
