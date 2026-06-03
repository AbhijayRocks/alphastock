"""
training/train_all.py — One-command training for the entire AlphaStock pipeline.

RUN THIS TO TRAIN EVERYTHING:
  python -m training.train_all

WHAT IT DOES:
  1. Loads pre-built features for all 50 Nifty stocks
  2. For each stock, for each horizon (1d, 5d, 20d):
     a. Runs feature selection (195 → ~80 features)
     b. Trains LightGBM regressor (with Optuna tuning)
     c. Trains XGBoost regressor (with Optuna tuning)
     d. Trains LightGBM classifier (direction prediction)
     e. Trains XGBoost classifier (direction prediction)
     f. Builds weighted ensemble for regression
     g. Builds weighted ensemble for classification
     h. Saves all models to disk
  3. Prints leaderboard: which stocks are most/least predictable
  4. Saves comprehensive results JSON

ESTIMATED TIME:
  - Single stock, single horizon, 50 trials:  ~2-3 minutes
  - Single stock, all 3 horizons, 50 trials:  ~8-10 minutes
  - All 50 stocks, single horizon, 50 trials: ~2-3 hours
  - All 50 stocks, all 3 horizons, 50 trials: ~6-9 hours

QUICK TEST:
  python -m training.train_all --quick
  (trains only RELIANCE_NS with 20 Optuna trials)
"""

import sys
import time
import logging
import json
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

from config import MODELS_DIR, HORIZONS, LOG_LEVEL
from training.trainer import (
    run_training, run_training_all_stocks,
    run_training_all_horizons,
)
from features.pipeline import load_all_features

logging.basicConfig(level=LOG_LEVEL, format="%(asctime)s | %(levelname)s | %(message)s")
logger = logging.getLogger(__name__)


def train_everything(
    n_optuna_trials: int = 50,
    run_cv: bool = False,
    feature_selection: bool = True,
    top_k_features: int = 80,
    horizons: list = None,
    tickers: list = None,
) -> dict:
    """
    Master training function — trains all models for all stocks for all horizons.

    Args:
        n_optuna_trials : Optuna trials per model (50 = good, 100 = thorough)
        run_cv          : run walk-forward CV (slower but gives honest metrics)
        feature_selection: apply 3-stage feature selection
        top_k_features  : features to keep after selection
        horizons        : list of horizons to train (default: all 3)
        tickers         : list of tickers to train (default: all available)

    Returns:
        nested dict: {horizon: {ticker: results}}
    """
    if horizons is None:
        horizons = list(HORIZONS.keys())

    start_time = time.time()

    logger.info("=" * 70)
    logger.info("ALPHA STOCK — FULL TRAINING PIPELINE")
    logger.info("=" * 70)
    logger.info(f"  Horizons        : {horizons}")
    logger.info(f"  Optuna trials   : {n_optuna_trials}")
    logger.info(f"  Walk-forward CV : {run_cv}")
    logger.info(f"  Feature select  : {feature_selection} (top {top_k_features})")
    logger.info(f"  Start time      : {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    logger.info("=" * 70)

    # Load available features
    all_features = load_all_features()
    if tickers is None:
        tickers = list(all_features.keys())
    logger.info(f"  Stocks to train : {len(tickers)}")

    all_results = {}

    for horizon in horizons:
        logger.info(f"\n{'═' * 70}")
        logger.info(f"HORIZON: {horizon}")
        logger.info(f"{'═' * 70}")

        horizon_results = {}
        failed = []

        for i, ticker in enumerate(tickers):
            try:
                logger.info(f"\n[{i + 1}/{len(tickers)}] {ticker} | horizon={horizon}")
                result = run_training(
                    ticker=ticker,
                    horizon=horizon,
                    n_optuna_trials=n_optuna_trials,
                    run_cv=run_cv,
                    feature_selection=feature_selection,
                    top_k_features=top_k_features,
                    save=True,
                )
                horizon_results[ticker] = result

            except Exception as e:
                logger.error(f"{ticker}: FAILED — {e}")
                failed.append(ticker)

        all_results[horizon] = horizon_results

        # Print horizon summary
        _print_horizon_summary(horizon_results, horizon, failed)

    # Final summary
    elapsed = time.time() - start_time
    _print_final_summary(all_results, elapsed)

    # Save master results
    _save_master_results(all_results)

    return all_results


def train_quick_test(ticker: str = "RELIANCE_NS") -> dict:
    """
    Quick test — train one stock with minimal settings.
    Useful to verify the pipeline works before running the full training.
    """
    logger.info("=" * 70)
    logger.info(f"QUICK TEST: {ticker}")
    logger.info("=" * 70)

    results = {}
    for horizon in HORIZONS.keys():
        results[horizon] = run_training(
            ticker=ticker,
            horizon=horizon,
            n_optuna_trials=20,
            run_cv=False,
            feature_selection=True,
            top_k_features=80,
            save=True,
        )

    return results


def _print_horizon_summary(results: dict, horizon: str, failed: list) -> None:
    """Print summary for one horizon across all stocks."""
    if not results:
        return

    logger.info(f"\n{'═' * 70}")
    logger.info(f"HORIZON {horizon} — SUMMARY ({len(results)} stocks)")
    logger.info(f"{'═' * 70}")

    # Collect best metrics per stock
    clf_accs = []
    reg_dirs = []

    for ticker, result in results.items():
        best_clf = 0.0
        best_reg = 0.0

        for m in ["lightgbm_clf", "xgboost_clf", "ensemble_clf"]:
            test = result.get("models", {}).get(m, {}).get("test", {})
            best_clf = max(best_clf, test.get("test_accuracy", 0.0))

        for m in ["lightgbm", "xgboost", "ensemble_reg"]:
            test = result.get("models", {}).get(m, {}).get("test", {})
            best_reg = max(best_reg, test.get("test_dir_acc",
                          test.get("test_ensemble_dir_acc", 0.0)))

        clf_accs.append(best_clf)
        reg_dirs.append(best_reg)

    logger.info(f"  Classification accuracy:")
    logger.info(f"    Mean:   {np.mean(clf_accs):.2%}")
    logger.info(f"    Best:   {np.max(clf_accs):.2%}")
    logger.info(f"    Worst:  {np.min(clf_accs):.2%}")
    logger.info(f"    Std:    {np.std(clf_accs):.2%}")

    logger.info(f"  Regression directional accuracy:")
    logger.info(f"    Mean:   {np.mean(reg_dirs):.2%}")
    logger.info(f"    Best:   {np.max(reg_dirs):.2%}")
    logger.info(f"    Worst:  {np.min(reg_dirs):.2%}")

    if failed:
        logger.warning(f"  Failed stocks: {failed}")


def _print_final_summary(all_results: dict, elapsed: float) -> None:
    """Print the final summary across all horizons."""
    hours = elapsed / 3600
    mins = (elapsed % 3600) / 60

    logger.info(f"\n{'═' * 70}")
    logger.info("TRAINING COMPLETE")
    logger.info(f"{'═' * 70}")
    logger.info(f"  Total time: {int(hours)}h {int(mins)}m")

    for horizon, results in all_results.items():
        n_stocks = len(results)
        if n_stocks == 0:
            continue

        clf_accs = []
        for ticker, result in results.items():
            for m in ["ensemble_clf", "lightgbm_clf", "xgboost_clf"]:
                test = result.get("models", {}).get(m, {}).get("test", {})
                acc = test.get("test_accuracy", 0.0)
                if acc > 0:
                    clf_accs.append(acc)
                    break

        if clf_accs:
            logger.info(f"  {horizon}: {n_stocks} stocks | "
                         f"mean clf acc={np.mean(clf_accs):.2%} | "
                         f"best={np.max(clf_accs):.2%}")

    logger.info(f"{'═' * 70}")


def _save_master_results(all_results: dict) -> None:
    """Save a master summary JSON."""
    summary_path = MODELS_DIR / "training_summary.json"

    summary = {
        "timestamp": datetime.now().isoformat(),
        "horizons": {},
    }

    for horizon, results in all_results.items():
        horizon_summary = {}
        for ticker, result in results.items():
            ticker_summary = {}
            for m_name, m_data in result.get("models", {}).items():
                if isinstance(m_data, dict) and "test" in m_data:
                    ticker_summary[m_name] = m_data["test"]
            horizon_summary[ticker] = ticker_summary

        summary["horizons"][horizon] = horizon_summary

    with open(summary_path, "w") as f:
        json.dump(summary, f, indent=2, default=str)
    logger.info(f"Master results saved to {summary_path}")


# ── CLI Entry Point ───────────────────────────────────────────────────────────

if __name__ == "__main__":
    args = sys.argv[1:]

    if "--quick" in args or "-q" in args:
        # Quick test mode
        ticker = "RELIANCE_NS"
        for arg in args:
            if arg not in ("--quick", "-q") and not arg.startswith("-"):
                ticker = arg
                break
        train_quick_test(ticker)

    elif "--single" in args or "-s" in args:
        # Single stock, all horizons
        ticker = "RELIANCE_NS"
        for arg in args:
            if arg not in ("--single", "-s") and not arg.startswith("-"):
                ticker = arg
                break
        train_quick_test(ticker)

    elif "--horizon" in args:
        # All stocks, single horizon
        idx = args.index("--horizon")
        horizon = args[idx + 1] if idx + 1 < len(args) else "1d"
        n_trials = 50
        if "--trials" in args:
            t_idx = args.index("--trials")
            n_trials = int(args[t_idx + 1])

        train_everything(
            horizons=[horizon],
            n_optuna_trials=n_trials,
        )

    else:
        # DEFAULT: train everything
        n_trials = 50
        if "--trials" in args:
            t_idx = args.index("--trials")
            n_trials = int(args[t_idx + 1])

        train_everything(
            n_optuna_trials=n_trials,
            run_cv=False,
            feature_selection=True,
        )
