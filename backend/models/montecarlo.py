"""
models/montecarlo.py — Merton jump-diffusion Monte Carlo (risk layer).

WHAT THIS IS (and isn't):
  This does NOT predict direction — that's the ML models' job. It takes the
  model's predicted return as the DRIFT and simulates thousands of plausible
  forward paths around it, so we can describe the *uncertainty* honestly —
  including sudden gaps/crashes that a Gaussian band misses.

THE MODEL — Merton (1976) jump-diffusion:
  dS/S = mu dt + sigma dW + (J - 1) dN
    • sigma dW : continuous diffusion (normal day-to-day wiggle)
    • dN       : Poisson(lambda) jump arrivals (earnings, news, crashes)
    • J        : lognormal jump size  ⇒  log-jump ~ N(jump_mean, jump_std)
  The jumps are what give fat tails and skew — the realism we're adding.

HOW IT PLUGS INTO OUR STACK:
  drift   = ML predicted_return        (the "view")
  sigma   = GARCH(1,1) conditional vol (continuous risk — features/garch)
  jumps   = calibrated from history    (the discontinuous risk)
  → Monte Carlo propagates all three into a full forward-return distribution.

AVOIDING DOUBLE-COUNTING:
  GARCH already fattens multi-day tails via vol clustering. So we calibrate the
  jump component on JUMP-FILTERED returns (threshold method) and let GARCH supply
  the diffusion vol — diffusion and jumps describe different risks, not the same
  one twice.

CALIBRATION (dependency-free, numpy only):
  A return is flagged a "jump" if it exceeds k standard deviations. Jump
  intensity = jump frequency; jump mean/std from the flagged moves; diffusion vol
  from what remains.
"""

import logging
from typing import Dict, Optional

import numpy as np

logger = logging.getLogger(__name__)

TRADING_DAYS = 252
_MIN_OBS = 250
_JUMP_K = 3.5          # a move beyond k·sigma is treated as a jump
_EPS = 1e-12


def calibrate_merton(log_returns: np.ndarray) -> Optional[Dict[str, float]]:
    """
    Calibrate Merton jump-diffusion parameters from historical daily log returns.

    Returns daily-unit params, or None if the sample is too small:
        mu_d        : daily diffusion drift (informational; sim drift comes from ML)
        sigma_d     : daily diffusion vol (jump-filtered)
        lambda_d    : daily jump intensity (expected jumps per day)
        jump_mean   : mean log jump size
        jump_std    : std of log jump size
    """
    r = np.asarray(log_returns, dtype=float)
    r = r[np.isfinite(r)]
    if r.size < _MIN_OBS:
        return None

    mu, sd = float(r.mean()), float(r.std())
    if sd <= _EPS:
        return None

    # Threshold: flag jumps as |r - mean| > k·sigma
    jump_mask = np.abs(r - mu) > (_JUMP_K * sd)
    jumps = r[jump_mask]
    diffusion = r[~jump_mask]

    n = r.size
    n_jumps = int(jump_mask.sum())

    if n_jumps >= 2:
        jump_mean = float(jumps.mean())
        jump_std  = float(jumps.std())
        lambda_d  = n_jumps / n                      # jumps per day
    else:
        # Too few jumps to estimate — treat as (near) pure diffusion
        jump_mean, jump_std, lambda_d = 0.0, sd * 2.0, max(n_jumps, 0) / n

    return {
        "mu_d":      float(diffusion.mean()) if diffusion.size else mu,
        "sigma_d":   float(diffusion.std())  if diffusion.size else sd,
        "lambda_d":  float(lambda_d),
        "jump_mean": jump_mean,
        "jump_std":  float(max(jump_std, _EPS)),
        "n_jumps":   n_jumps,
    }


def _simulate_terminal_log(
    predicted_return: float,
    horizon_days: int,
    params: Dict[str, float],
    diffusion_sigma_daily: Optional[float],
    n_sims: int,
    rng: np.random.Generator,
) -> np.ndarray:
    """
    Simulate terminal (horizon-end) LOG returns, vectorized.

    Centering: the diffusion drift is set so the distribution's mean log-return
    equals ln(1 + predicted_return) — i.e. the simulation is centered on the ML
    view, with diffusion + jumps providing the spread/tails around it.
    """
    h = max(1, int(horizon_days))
    sigma_d = diffusion_sigma_daily if (diffusion_sigma_daily and diffusion_sigma_daily > 0) else params["sigma_d"]
    lam, jm, js = params["lambda_d"], params["jump_mean"], params["jump_std"]

    target_log = np.log1p(predicted_return)
    # Remove the jumps' mean contribution so they don't shift the center
    diffusion_drift = target_log - lam * h * jm

    # Diffusion: drift + sqrt(h)·sigma·Z
    z = rng.standard_normal(n_sims)
    diffusion = diffusion_drift + np.sqrt(h) * sigma_d * z

    # Jumps: N ~ Poisson(lambda·h); sum of N iid N(jm, js) = N(N·jm, sqrt(N)·js)
    n_jumps = rng.poisson(lam * h, size=n_sims)
    jump_term = n_jumps * jm + np.sqrt(n_jumps) * js * rng.standard_normal(n_sims)

    return diffusion + jump_term


def simulate_terminal_returns(
    predicted_return: float,
    horizon_days: int,
    params: Dict[str, float],
    diffusion_sigma_daily: Optional[float] = None,
    n_sims: int = 10_000,
    seed: int = 42,
) -> np.ndarray:
    """Vectorized terminal SIMPLE returns over the horizon (fast, no paths)."""
    rng = np.random.default_rng(seed)
    log_ret = _simulate_terminal_log(predicted_return, horizon_days, params,
                                     diffusion_sigma_daily, n_sims, rng)
    return np.expm1(log_ret)


def risk_metrics(returns: np.ndarray) -> Dict[str, float]:
    """
    Summarize a simulated return distribution into risk numbers.

      p05/p95  : 5th/95th percentile returns → fat-tailed prediction band
      var_95   : 95% Value-at-Risk (magnitude of the 5% worst-case loss)
      cvar_95  : Conditional VaR / expected shortfall (avg loss beyond VaR)
      prob_up  : probability the return is positive
      prob_big_drop : probability of a loss worse than 2× the downside band
    """
    r = np.asarray(returns, dtype=float)
    p05 = float(np.percentile(r, 5))
    p95 = float(np.percentile(r, 95))
    tail = r[r <= p05]
    cvar = float(tail.mean()) if tail.size else p05
    return {
        "p05":           round(p05, 5),
        "p95":           round(p95, 5),
        "var_95":        round(-p05, 5),                 # report loss as positive
        "cvar_95":       round(-cvar, 5),
        "prob_up":       round(float(np.mean(r > 0)), 4),
        "prob_big_drop": round(float(np.mean(r < 2 * p05)), 4),
        "mean":          round(float(r.mean()), 5),
        "median":        round(float(np.median(r)), 5),
    }


def simulate_price_fan(
    current_price: float,
    predicted_return: float,
    horizon_days: int,
    params: Dict[str, float],
    diffusion_sigma_daily: Optional[float] = None,
    n_sims: int = 2_000,
    seed: int = 42,
) -> Dict[str, list]:
    """
    Simulate full daily PRICE paths and return a percentile fan for charting.

    Returns dict with `steps` (0..H) and price percentile bands
    p05/p25/p50/p75/p95 — the classic Monte-Carlo cone.
    """
    h = max(1, int(horizon_days))
    sigma_d = diffusion_sigma_daily if (diffusion_sigma_daily and diffusion_sigma_daily > 0) else params["sigma_d"]
    lam, jm, js = params["lambda_d"], params["jump_mean"], params["jump_std"]

    rng = np.random.default_rng(seed)
    target_log = np.log1p(predicted_return)
    daily_drift = (target_log - lam * h * jm) / h        # spread drift across days

    # Per-step log increments: diffusion + per-day jumps
    z = rng.standard_normal((n_sims, h))
    diffusion = daily_drift + sigma_d * z
    n_jumps = rng.poisson(lam, size=(n_sims, h))
    jumps = n_jumps * jm + np.sqrt(n_jumps) * js * rng.standard_normal((n_sims, h))
    incr = diffusion + jumps

    log_paths = np.cumsum(incr, axis=1)
    prices = current_price * np.exp(log_paths)
    prices = np.hstack([np.full((n_sims, 1), current_price), prices])   # prepend S0

    pct = {q: np.percentile(prices, p, axis=0)
           for q, p in [("p05", 5), ("p25", 25), ("p50", 50), ("p75", 75), ("p95", 95)]}

    return {
        "steps": list(range(h + 1)),
        "p05":   [round(float(v), 2) for v in pct["p05"]],
        "p25":   [round(float(v), 2) for v in pct["p25"]],
        "p50":   [round(float(v), 2) for v in pct["p50"]],
        "p75":   [round(float(v), 2) for v in pct["p75"]],
        "p95":   [round(float(v), 2) for v in pct["p95"]],
    }


if __name__ == "__main__":
    # Self-test: synthetic returns with a few injected jumps
    rng = np.random.default_rng(0)
    r = rng.normal(0.0003, 0.012, 1500)
    r[rng.integers(0, 1500, 12)] += rng.normal(-0.06, 0.03, 12)   # crash jumps
    p = calibrate_merton(r)
    print("params:", {k: round(v, 5) for k, v in p.items()})
    rets = simulate_terminal_returns(0.01, 20, p, diffusion_sigma_daily=0.014, n_sims=20000)
    print("risk:", risk_metrics(rets))
    fan = simulate_price_fan(1000.0, 0.01, 20, p, diffusion_sigma_daily=0.014)
    print("fan p50 end:", fan["p50"][-1], "| p05 end:", fan["p05"][-1], "| p95 end:", fan["p95"][-1])
