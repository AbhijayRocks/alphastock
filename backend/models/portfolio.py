import numpy as np
import pandas as pd
from scipy.optimize import minimize
from typing import Dict, Optional, Tuple
import logging

logger = logging.getLogger(__name__)


# ── Covariance shrinkage (Tier 3 robustness) ────────────────────────────────────

def shrink_covariance(cov: pd.DataFrame, returns_df: Optional[pd.DataFrame] = None,
                      delta: float = 0.15) -> pd.DataFrame:
    """
    Stabilize a covariance matrix by shrinking it toward a diagonal target.

    Sample/GARCH covariances are noisy and make the optimizer an "error maximizer"
    — it piles into whatever pair looks spuriously low-correlation. Shrinkage pulls
    the estimate toward a well-conditioned target, trading a little bias for a lot
    less variance. If sklearn + raw returns are available we use Ledoit-Wolf to pick
    the shrinkage intensity; otherwise a fixed delta toward the diagonal.
    """
    C = cov.copy()
    target = np.diag(np.diag(C.values))            # keep variances, zero covariances

    if returns_df is not None and returns_df.shape[0] > C.shape[0] + 2:
        try:
            from sklearn.covariance import ledoit_wolf
            _, shrink = ledoit_wolf(returns_df.dropna().values)
            delta = float(np.clip(shrink, 0.05, 0.9))
        except Exception as e:
            logger.debug(f"Ledoit-Wolf failed ({e}); using fixed delta={delta}")

    shrunk = (1 - delta) * C.values + delta * target
    return pd.DataFrame(shrunk, index=C.index, columns=C.columns)


def _cov_to_corr(cov: pd.DataFrame) -> pd.DataFrame:
    std = np.sqrt(np.diag(cov.values))
    std[std == 0] = 1e-12
    corr = cov.values / np.outer(std, std)
    return pd.DataFrame(np.clip(corr, -1, 1), index=cov.index, columns=cov.columns)


# ── Hierarchical Risk Parity (López de Prado) ───────────────────────────────────

def _ivp(cov: pd.DataFrame) -> np.ndarray:
    ivp = 1.0 / np.diag(cov.values)
    return ivp / ivp.sum()


def _cluster_var(cov: pd.DataFrame, items) -> float:
    sub = cov.loc[items, items]
    w = _ivp(sub).reshape(-1, 1)
    return float((w.T @ sub.values @ w)[0, 0])


def _quasi_diag(link) -> list:
    link = link.astype(int)
    sort_ix = pd.Series([link[-1, 0], link[-1, 1]])
    n_items = link[-1, 3]
    while sort_ix.max() >= n_items:
        sort_ix.index = range(0, sort_ix.shape[0] * 2, 2)
        df0 = sort_ix[sort_ix >= n_items]
        i, j = df0.index, df0.values - n_items
        sort_ix[i] = link[j, 0]
        sort_ix = pd.concat([sort_ix, pd.Series(link[j, 1], index=i + 1)]).sort_index()
        sort_ix.index = range(sort_ix.shape[0])
    return sort_ix.tolist()


def hierarchical_risk_parity(cov: pd.DataFrame) -> Dict[str, float]:
    """
    HRP: cluster assets by correlation, then split risk top-down through the tree.
    No matrix inversion → robust to ill-conditioned / near-singular covariances,
    and it ignores (noisy) expected returns entirely — pure diversification.
    """
    import scipy.cluster.hierarchy as sch
    from scipy.spatial.distance import squareform

    cov = pd.DataFrame(cov)
    assets = list(cov.index)
    if len(assets) == 1:
        return {assets[0]: 1.0}

    corr = _cov_to_corr(cov)
    dist = ((1 - corr) / 2.0).clip(lower=0) ** 0.5
    link = sch.linkage(squareform(dist.values, checks=False), method="single")
    order = [assets[i] for i in _quasi_diag(link)]

    w = pd.Series(1.0, index=order)
    clusters = [order]
    while clusters:
        clusters = [c[a:b] for c in clusters
                    for a, b in ((0, len(c) // 2), (len(c) // 2, len(c))) if len(c) > 1]
        for i in range(0, len(clusters), 2):
            c0, c1 = clusters[i], clusters[i + 1]
            v0, v1 = _cluster_var(cov, c0), _cluster_var(cov, c1)
            alpha = 1 - v0 / (v0 + v1)
            w[c0] *= alpha
            w[c1] *= (1 - alpha)
    return {t: float(w[t]) for t in assets}


# ── Black-Litterman (blend model views with market equilibrium) ─────────────────

def black_litterman_returns(cov: pd.DataFrame, market_weights: Dict[str, float],
                            view_returns: Dict[str, float], risk_aversion: float = 2.5,
                            tau: float = 0.05, view_confidence: float = 1.0) -> pd.Series:
    """
    Blend the market's equilibrium expected returns (implied by index weights) with
    the model's predicted returns (treated as absolute views). Produces stable,
    sensible expected returns instead of letting raw forecasts create corner bets.
    """
    cov = pd.DataFrame(cov)
    assets = list(cov.index)
    Sigma = cov.values

    w_mkt = np.array([market_weights.get(a, 0.0) for a in assets], dtype=float)
    if w_mkt.sum() <= 0:
        w_mkt = np.ones(len(assets))
    w_mkt /= w_mkt.sum()

    pi = risk_aversion * Sigma @ w_mkt                     # equilibrium excess returns
    P = np.eye(len(assets))                                # one absolute view per asset
    Q = np.array([view_returns.get(a, 0.0) for a in assets], dtype=float)

    tauSigma = tau * Sigma
    Omega = np.diag(np.diag(P @ tauSigma @ P.T)) / max(view_confidence, 1e-6)
    Omega += 1e-8 * np.eye(len(assets))

    A = np.linalg.pinv(tauSigma)
    Oinv = np.linalg.pinv(Omega)
    post = np.linalg.pinv(A + P.T @ Oinv @ P) @ (A @ pi + P.T @ Oinv @ Q)
    return pd.Series(post, index=assets)

def estimate_garch_covariance(returns_df: pd.DataFrame) -> pd.DataFrame:
    """
    Estimate the covariance matrix using Constant Conditional Correlation (CCC)
    GARCH(1,1).

    For each asset we forecast next-period conditional volatility with our own
    dependency-free GARCH(1,1) (features/garch — no `arch` library, so this runs
    on Python 3.14). Per-asset GARCH vols are then combined with the sample
    correlation matrix into the conditional covariance:

        Cov_ij = Corr_ij * Vol_i * Vol_j     (annualized)

    WHY GARCH HERE:
      Sample covariance treats every day equally and reacts slowly. GARCH vols
      respond to recent turbulence, so the optimizer sizes down assets that are
      currently volatile — more responsive, risk-aware allocations. Falls back to
      annualized sample covariance if anything goes wrong.
    """
    from features.garch import forecast_vol

    cols = list(returns_df.columns)
    if len(cols) == 0:
        return returns_df.cov() * 252

    # Single asset → variance only (correlation is trivially 1)
    if len(cols) == 1:
        v = returns_df[cols[0]].dropna().std() * np.sqrt(252)
        return pd.DataFrame([[v * v]], index=cols, columns=cols, dtype=float)

    # 1. Per-asset annualized conditional volatility via GARCH(1,1) forecast
    conditional_vols = pd.Series(index=cols, dtype=float)
    for col in cols:
        series = returns_df[col].dropna()
        vol = None
        try:
            vol = forecast_vol(series.values, horizon_days=1)   # daily, return units
        except Exception as e:
            logger.warning(f"GARCH vol failed for {col}: {e}. Using sample vol.")
        if vol is None or not np.isfinite(vol) or vol <= 0:
            vol = float(series.std())                           # realized fallback
        conditional_vols[col] = vol * np.sqrt(252)              # annualize

    # 2. Sample correlation matrix (the "constant correlation" in CCC-GARCH)
    corr = returns_df.corr().fillna(0.0).to_numpy(copy=True)
    np.fill_diagonal(corr, 1.0)

    # 3. Cov_ij = Corr_ij * Vol_i * Vol_j
    vols = conditional_vols.to_numpy()
    cov_values = corr * np.outer(vols, vols)
    return pd.DataFrame(cov_values, index=cols, columns=cols, dtype=float)


def optimize_portfolio(expected_returns: pd.Series, cov_matrix: pd.DataFrame,
                       risk_tolerance: float = 1.0, max_weight: float = 0.4) -> Dict[str, float]:
    """
    Optimize portfolio using Markowitz Mean-Variance Optimization.

    Args:
        expected_returns: Series of expected returns for each asset.
        cov_matrix: Covariance matrix of asset returns.
        risk_tolerance: Trade-off parameter between risk and return. Higher = more risk-seeking.
        max_weight: cap on any single position (anti-concentration). 0.4 = max 40%.

    Returns:
        Dict mapping ticker to optimal weight (0.0 to 1.0).
    """
    n_assets = len(expected_returns)
    tickers = expected_returns.index.tolist()

    if n_assets == 0:
        return {}
    cap = max(max_weight, 1.0 / n_assets)              # cap must allow a feasible sum-to-1
        
    # Objective function: Maximize (Expected Return - Risk_Tolerance * Variance)
    # Since scipy.optimize minimizes, we minimize: (Risk_Tolerance * Variance - Expected Return)
    def objective_function(weights):
        portfolio_return = np.sum(expected_returns * weights)
        portfolio_variance = np.dot(weights.T, np.dot(cov_matrix, weights))
        # We scale variance to make the objective more balanced
        return risk_tolerance * portfolio_variance - portfolio_return
        
    # Constraints: Weights sum to 1
    constraints = ({'type': 'eq', 'fun': lambda x: np.sum(x) - 1})
    
    # Bounds: no short selling, and no position above the concentration cap
    bounds = tuple((0, cap) for _ in range(n_assets))
    
    # Initial guess: Equal weighting
    initial_guess = np.array(n_assets * [1. / n_assets])
    
    # Optimize
    result = minimize(
        objective_function, 
        initial_guess, 
        method='SLSQP', 
        bounds=bounds, 
        constraints=constraints
    )
    
    if not result.success:
        # Fallback to equal weights if optimization fails
        return {ticker: 1.0 / n_assets for ticker in tickers}
        
    # Clean up weights (remove very small scientific notation numbers)
    optimal_weights = result.x
    optimal_weights = np.where(optimal_weights < 1e-4, 0, optimal_weights)
    
    # Re-normalize to ensure they sum exactly to 1 after cleanup
    weight_sum = np.sum(optimal_weights)
    if weight_sum > 0:
        optimal_weights = optimal_weights / weight_sum
        
    return {tickers[i]: float(optimal_weights[i]) for i in range(n_assets)}
