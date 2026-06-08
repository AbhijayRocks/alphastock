"""
training/backtest.py — Did our model actually make money?

WHY BACKTESTING MATTERS:
  A model can have excellent RMSE (low prediction error) but still lose
  money in practice. How? If it predicts +0.5% but actual is +0.3%,
  the direction is right (good) but if transaction costs are 0.4%, you
  lose money on every trade. Backtesting catches this.

  Think of it like test-driving a car vs just reading its specs.
  RMSE = reading the specs. Backtest = actually driving it.

WHAT WE SIMULATE:
  A simple long/short strategy:
    - If model predicts positive return → BUY (go long)
    - If model predicts negative return → SELL (go short or stay cash)
    - Hold for the prediction horizon (1d, 5d, or 20d)
    - No leverage, no transaction costs first (then add them)

KEY METRICS:
  Sharpe Ratio   : return / risk. >1 = decent, >2 = great, >3 = exceptional.
                   Annualized: multiply daily Sharpe by sqrt(252).
  Max Drawdown   : worst peak-to-trough loss. -20% means at some point
                   you lost 20% from your peak. Lower (less negative) = better.
  Hit Rate       : % of trades where direction was correct.
                   50% = random, 55%+ = useful, 60%+ = very good.
  Annual Return  : what % would you have made per year following this strategy?
  Calmar Ratio   : annual return / max drawdown. Reward per unit of drawdown risk.
"""

import logging
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

from config import LOG_LEVEL, MODELS_DIR

logging.basicConfig(level=LOG_LEVEL, format="%(asctime)s | %(levelname)s | %(message)s")
logger = logging.getLogger(__name__)


def run_backtest(
    y_true: np.ndarray,
    y_pred: np.ndarray,
    dates: Optional[pd.DatetimeIndex] = None,
    transaction_cost: float = 0.001,   # 0.1% per trade (realistic for India)
    horizon_days: int = 1,
    initial_capital: float = 100_000,  # Rs 1 lakh starting capital
    volatility: Optional[np.ndarray] = None,
    target_annual_vol: float = 0.20,
    max_leverage: float = 1.0,
) -> Dict:
    """
    Simulate a long/short trading strategy using model predictions.

    Strategy rules:
      - Predict positive return → go long (buy)
      - Predict negative return → go to cash (no short for simplicity)
      - Transaction cost deducted on every position change
      - Position held for horizon_days then re-evaluated

    VOLATILITY TARGETING (when `volatility` is provided):
      Instead of a fixed full-size long, scale exposure to a constant risk
      budget: size = clip(target_annual_vol / forecast_vol, 0, max_leverage).
      You hold less when GARCH says the stock is turbulent and more when it's
      calm — this typically lifts Sharpe and cuts drawdown even when hit-rate
      is unchanged. `volatility` is the per-row annualized vol forecast.

    Args:
        y_true           : actual returns (ground truth)
        y_pred           : model's predicted returns (or centered probabilities)
        dates            : DatetimeIndex for the test period
        transaction_cost : cost per trade as fraction (0.001 = 0.1%)
        horizon_days     : holding period
        initial_capital  : starting portfolio value
        volatility       : per-row annualized vol forecast (e.g. GARCH); enables
                           volatility targeting when supplied
        target_annual_vol: risk budget for vol targeting (annualized)
        max_leverage     : cap on position size when vol-targeting

    Returns:
        dict with all backtest metrics and equity curve
    """
    n = len(y_true)
    assert len(y_pred) == n, "y_true and y_pred must have same length"

    # ── Strategy Logic ────────────────────────────────────────────────────────
    # Discrete signal: 1 = long, 0 = cash. We go long when the model is bullish.
    raw_signal = (y_pred > 0).astype(float)

    if volatility is not None:
        # Volatility targeting: scale the long position by the risk budget.
        ann_vol = np.asarray(volatility, dtype=float)
        finite = np.isfinite(ann_vol) & (ann_vol > 0)
        fallback = float(np.median(ann_vol[finite])) if finite.any() else target_annual_vol
        ann_vol = np.where(finite, ann_vol, fallback)
        size = np.clip(target_annual_vol / ann_vol, 0.0, max_leverage)
        positions = raw_signal * size
    else:
        positions = raw_signal

    # Turnover (drives transaction cost) vs discrete signal flips (trade count)
    position_changes = np.abs(np.diff(positions, prepend=0))
    signal_changes   = np.abs(np.diff(raw_signal, prepend=0))
    strategy_returns = positions * y_true - position_changes * transaction_cost

    # Equity curve: cumulative portfolio value
    equity_curve = initial_capital * np.cumprod(1 + strategy_returns)

    # Benchmark: buy and hold Nifty (just hold through everything)
    buyhold_returns  = y_true  # actual returns = buy and hold
    buyhold_equity   = initial_capital * np.cumprod(1 + buyhold_returns)

    # ── Compute Metrics ───────────────────────────────────────────────────────
    metrics = {}

    # Directional accuracy (hit rate)
    correct_direction = np.sign(y_pred) == np.sign(y_true)
    metrics["hit_rate"] = float(np.mean(correct_direction))

    # Hit rate on the days we were actually long (discrete signal)
    long_mask = raw_signal == 1
    if long_mask.sum() > 0:
        metrics["hit_rate_long"] = float(np.mean(correct_direction[long_mask]))
    else:
        metrics["hit_rate_long"] = float("nan")

    # Returns
    total_return   = float((equity_curve[-1] / initial_capital) - 1)
    trading_days   = n * horizon_days
    years          = trading_days / 252
    annual_return  = float((1 + total_return) ** (1 / max(years, 0.1)) - 1) if years > 0 else 0.0

    metrics["total_return"]  = round(total_return, 4)
    metrics["annual_return"] = round(annual_return, 4)

    # Benchmark metrics
    bh_total  = float((buyhold_equity[-1] / initial_capital) - 1)
    bh_annual = float((1 + bh_total) ** (1 / max(years, 0.1)) - 1) if years > 0 else 0.0
    metrics["benchmark_total_return"]  = round(bh_total, 4)
    metrics["benchmark_annual_return"] = round(bh_annual, 4)
    metrics["excess_return"] = round(annual_return - bh_annual, 4)

    # Sharpe Ratio
    # Annualized: mean(daily_return) / std(daily_return) * sqrt(252)
    daily_ret_std = np.std(strategy_returns)
    daily_ret_mean = np.mean(strategy_returns)
    if daily_ret_std > 0:
        sharpe = float((daily_ret_mean / daily_ret_std) * np.sqrt(252 / horizon_days))
    else:
        sharpe = 0.0
    metrics["sharpe_ratio"] = round(sharpe, 3)

    # Max Drawdown
    # Rolling max of equity curve, drawdown = (current - rolling_max) / rolling_max
    rolling_max = np.maximum.accumulate(equity_curve)
    drawdowns   = (equity_curve - rolling_max) / rolling_max
    max_drawdown = float(np.min(drawdowns))
    metrics["max_drawdown"] = round(max_drawdown, 4)

    # Calmar Ratio = annual return / abs(max drawdown)
    if max_drawdown < 0:
        metrics["calmar_ratio"] = round(annual_return / abs(max_drawdown), 3)
    else:
        metrics["calmar_ratio"] = float("inf")

    # Win/Loss ratio
    winning_trades = strategy_returns[strategy_returns > 0]
    losing_trades  = strategy_returns[strategy_returns < 0]
    if len(losing_trades) > 0 and len(winning_trades) > 0:
        avg_win  = float(np.mean(winning_trades))
        avg_loss = float(np.mean(np.abs(losing_trades)))
        metrics["win_loss_ratio"]  = round(avg_win / avg_loss, 3)
        metrics["avg_win"]         = round(avg_win, 6)
        metrics["avg_loss"]        = round(avg_loss, 6)
    else:
        metrics["win_loss_ratio"] = float("nan")

    # Trade statistics
    metrics["n_trades"]       = int(signal_changes.sum())          # discrete entries/exits
    metrics["pct_long"]       = round(float(np.mean(raw_signal)), 3)
    metrics["avg_exposure"]   = round(float(np.mean(positions)), 3)  # avg position size
    metrics["n_samples"]      = n

    # Store equity curves for plotting
    metrics["equity_curve"]   = equity_curve.tolist()
    metrics["buyhold_curve"]  = buyhold_equity.tolist()
    metrics["dates"]          = [str(d) for d in dates] if dates is not None else None

    return metrics


def evaluate_model_backtest(
    df: pd.DataFrame,
    model,
    horizon: str = "1d",
    transaction_cost: float = 0.001,
) -> Dict:
    """
    Run backtest on the test set of a trained model.

    Args:
        df              : full feature DataFrame (with targets)
        model           : trained model object (LightGBMModel etc.)
        horizon         : "1d", "5d", "20d"
        transaction_cost: cost per trade

    Returns:
        backtest metrics dict
    """
    from features.pipeline import get_train_test_split
    from training.trainer import prepare_arrays

    _, _, test_df = get_train_test_split(df, horizon=horizon)
    X_test, y_test, _ = prepare_arrays(test_df, horizon)

    y_pred = model.predict(X_test)

    horizon_days = {"1d": 1, "5d": 5, "20d": 20}.get(horizon, 1)

    metrics = run_backtest(
        y_true           = y_test,
        y_pred           = y_pred,
        dates            = test_df.index,
        transaction_cost = transaction_cost,
        horizon_days     = horizon_days,
    )

    _print_backtest_summary(metrics, model.name, horizon)
    return metrics


def compare_models_backtest(
    results_dict: Dict,
    df: pd.DataFrame,
    horizon: str = "1d",
) -> pd.DataFrame:
    """
    Compare multiple models' backtest performance in a clean table.

    Args:
        results_dict: output from run_training() containing trained models
        df          : feature DataFrame
        horizon     : prediction horizon

    Returns:
        DataFrame comparing all models side by side
    """
    rows = []

    for model_name, model_results in results_dict.get("models", {}).items():
        model = model_results.get("model")
        if model is None:
            continue

        metrics = evaluate_model_backtest(df, model, horizon)
        rows.append({
            "model":           model_name,
            "hit_rate":        f"{metrics['hit_rate']:.1%}",
            "annual_return":   f"{metrics['annual_return']:.1%}",
            "benchmark":       f"{metrics['benchmark_annual_return']:.1%}",
            "excess_return":   f"{metrics['excess_return']:.1%}",
            "sharpe_ratio":    f"{metrics['sharpe_ratio']:.2f}",
            "max_drawdown":    f"{metrics['max_drawdown']:.1%}",
            "calmar_ratio":    f"{metrics['calmar_ratio']:.2f}",
        })

    comparison_df = pd.DataFrame(rows).set_index("model")
    logger.info(f"\nModel Comparison (horizon={horizon}):\n{comparison_df.to_string()}")
    return comparison_df


def _print_backtest_summary(metrics: Dict, model_name: str, horizon: str) -> None:
    logger.info(f"\n{'='*50}")
    logger.info(f"BACKTEST: {model_name.upper()} | horizon={horizon}")
    logger.info(f"{'='*50}")
    logger.info(f"  Hit rate        : {metrics['hit_rate']:.1%}")
    logger.info(f"  Annual return   : {metrics['annual_return']:.1%}")
    logger.info(f"  Benchmark return: {metrics['benchmark_annual_return']:.1%}")
    logger.info(f"  Excess return   : {metrics['excess_return']:.1%}")
    logger.info(f"  Sharpe ratio    : {metrics['sharpe_ratio']:.2f}")
    logger.info(f"  Max drawdown    : {metrics['max_drawdown']:.1%}")
    logger.info(f"  Calmar ratio    : {metrics['calmar_ratio']:.2f}")
    logger.info(f"  Total trades    : {metrics['n_trades']}")
    logger.info(f"{'='*50}")


if __name__ == "__main__":
    # Quick test — train a model and backtest it
    from training.trainer import run_training
    from features.pipeline import load_features

    results = run_training(
        ticker          = "RELIANCE_NS",
        horizon         = "1d",
        models          = ["lightgbm"],
        run_cv          = False,
        n_optuna_trials = 10,
        save            = False,
    )

    df = load_features("RELIANCE_NS")
    model = results["models"]["lightgbm"]["model"]
    metrics = evaluate_model_backtest(df, model, horizon="1d")

    print(f"\nSharpe Ratio: {metrics['sharpe_ratio']:.2f}")
    print(f"Annual Return: {metrics['annual_return']:.1%}")
    print(f"Max Drawdown: {metrics['max_drawdown']:.1%}")
