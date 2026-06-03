import numpy as np
import pandas as pd
from scipy.optimize import minimize
from typing import Dict, Tuple
import logging

logger = logging.getLogger(__name__)

def estimate_garch_covariance(returns_df: pd.DataFrame) -> pd.DataFrame:
    """
    Estimate covariance matrix using Constant Conditional Correlation (CCC) GARCH(1,1).
    For each asset, we fit a GARCH(1,1) model to get today's conditional volatility.
    We then combine this with the historical correlation matrix to construct the 
    conditional covariance matrix.
    """
    try:
        from arch import arch_model
    except ImportError:
        logger.warning("arch package not installed. Falling back to sample covariance.")
        return returns_df.cov() * 252

    n_assets = len(returns_df.columns)
    conditional_vols = pd.Series(index=returns_df.columns, dtype=float)
    
    # 1. Estimate univariate GARCH(1,1) for each asset
    for col in returns_df.columns:
        # arch_model expects percentage returns (scaled by 100) for better convergence
        scaled_returns = returns_df[col].dropna() * 100
        if len(scaled_returns) < 50:
            conditional_vols[col] = scaled_returns.std() / 100
            continue
            
        try:
            am = arch_model(scaled_returns, vol='Garch', p=1, o=0, q=1, dist='Normal')
            res = am.fit(disp='off', show_warning=False)
            # Get the forecasted volatility for the next step (T+1)
            forecasts = res.forecast(horizon=1)
            # Convert variance back to standard deviation and unscale
            next_vol = np.sqrt(forecasts.variance.iloc[-1, 0]) / 100
            # Annualize it
            conditional_vols[col] = next_vol * np.sqrt(252)
        except Exception as e:
            logger.warning(f"GARCH fit failed for {col}: {e}. Using sample volatility.")
            conditional_vols[col] = returns_df[col].std() * np.sqrt(252)

    # 2. Calculate sample correlation matrix (Constant Conditional Correlation)
    corr_matrix = returns_df.corr()
    
    # 3. Construct the CCC-GARCH covariance matrix: Cov_ij = Corr_ij * Vol_i * Vol_j
    cov_matrix = pd.DataFrame(index=returns_df.columns, columns=returns_df.columns, dtype=float)
    for i in returns_df.columns:
        for j in returns_df.columns:
            cov_matrix.loc[i, j] = corr_matrix.loc[i, j] * conditional_vols[i] * conditional_vols[j]
            
    return cov_matrix


def optimize_portfolio(expected_returns: pd.Series, cov_matrix: pd.DataFrame, risk_tolerance: float = 1.0) -> Dict[str, float]:
    """
    Optimize portfolio using Markowitz Mean-Variance Optimization.
    
    Args:
        expected_returns: Series of expected returns for each asset.
        cov_matrix: Covariance matrix of asset returns.
        risk_tolerance: Trade-off parameter between risk and return. Higher = more risk-seeking.
        
    Returns:
        Dict mapping ticker to optimal weight (0.0 to 1.0).
    """
    n_assets = len(expected_returns)
    tickers = expected_returns.index.tolist()
    
    if n_assets == 0:
        return {}
        
    # Objective function: Maximize (Expected Return - Risk_Tolerance * Variance)
    # Since scipy.optimize minimizes, we minimize: (Risk_Tolerance * Variance - Expected Return)
    def objective_function(weights):
        portfolio_return = np.sum(expected_returns * weights)
        portfolio_variance = np.dot(weights.T, np.dot(cov_matrix, weights))
        # We scale variance to make the objective more balanced
        return risk_tolerance * portfolio_variance - portfolio_return
        
    # Constraints: Weights sum to 1
    constraints = ({'type': 'eq', 'fun': lambda x: np.sum(x) - 1})
    
    # Bounds: Weights between 0 and 1 (no short selling)
    bounds = tuple((0, 1) for _ in range(n_assets))
    
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
