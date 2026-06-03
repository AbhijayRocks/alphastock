"""
training/trainer.py — The training engine (v2 — with feature selection + ensemble).

WHAT CHANGED FROM V1:
  1. Feature selection BEFORE training (195 → ~80 features)
  2. Both regression AND classification models trained
  3. Ensemble combining all models automatically
  4. Purged walk-forward CV (embargo gap prevents target leakage)
  5. All 3 horizons (1d, 5d, 20d) trained in one call
  6. Sample weighting built into models (recent data matters more)
  7. Better metrics reporting with comparison tables

USAGE:
  # Train one stock, one horizon:
  from training.trainer import run_training
  results = run_training(ticker="RELIANCE_NS", horizon="1d")

  # Train one stock, all horizons:
  results = run_training(ticker="RELIANCE_NS", horizon="all")

  # Train all stocks:
  from training.trainer import run_training_all_stocks
  all_results = run_training_all_stocks()
"""

import logging
import json
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
from sklearn.model_selection import TimeSeriesSplit

from config import (
    MODELS_DIR, SEED, N_CV_SPLITS,
    TEST_RATIO, VAL_RATIO, HORIZONS, LOG_LEVEL
)
from features.pipeline import load_all_features, load_features, get_train_test_split
from features.selection import FeatureSelector
from models.lgbm_xgb import LightGBMModel, XGBoostModel, compute_metrics
from models.classifier import (
    LightGBMClassifier, XGBoostClassifier, compute_classification_metrics
)
from models.ensemble import EnsemblePredictor

logging.basicConfig(level=LOG_LEVEL, format="%(asctime)s | %(levelname)s | %(message)s")
logger = logging.getLogger(__name__)

# Silence Optuna
import optuna
optuna.logging.set_verbosity(optuna.logging.WARNING)


# ── Data Preparation ──────────────────────────────────────────────────────────

def prepare_arrays(
    df: pd.DataFrame,
    horizon: str,
    drop_target_cols: bool = True,
) -> Tuple[np.ndarray, np.ndarray, List[str]]:
    """
    Convert a feature DataFrame into numpy arrays for model training.

    Returns:
        X            : feature matrix, shape (n, n_features)
        y            : target vector, shape (n,)
        feature_names: list of feature column names
    """
    target_col = f"target_{horizon}"
    if target_col not in df.columns:
        raise ValueError(f"Target column {target_col} not in DataFrame")

    # Drop ALL target-related columns from features
    if drop_target_cols:
        target_cols = [c for c in df.columns if c.startswith("target_")]
    else:
        target_cols = [target_col]

    feature_cols = [c for c in df.columns if c not in target_cols]
    df_features = df[feature_cols].select_dtypes(include=[np.number])
    feature_names = list(df_features.columns)

    X = df_features.values.astype(np.float32)
    y = df[target_col].values.astype(np.float32)

    # Remove rows where target is NaN
    valid_mask = ~np.isnan(y)
    X = X[valid_mask]
    y = y[valid_mask]

    # Replace NaNs in X with column medians
    col_medians = np.nanmedian(X, axis=0)
    nan_mask = np.isnan(X)
    if nan_mask.any():
        X[nan_mask] = np.take(col_medians, np.where(nan_mask)[1])

    # Replace any remaining inf
    X = np.nan_to_num(X, nan=0.0, posinf=0.0, neginf=0.0)

    return X, y, feature_names


def prepare_classification_target(y: np.ndarray) -> np.ndarray:
    """Convert regression target (returns) to classification target (direction)."""
    return (y > 0).astype(np.float32)


# ── Feature Selection ─────────────────────────────────────────────────────────

def run_feature_selection(
    df: pd.DataFrame,
    horizon: str,
    top_k: int = 80,
) -> Tuple[pd.DataFrame, FeatureSelector]:
    """
    Run feature selection and return filtered DataFrame + fitted selector.
    """
    logger.info(f"Running feature selection for horizon={horizon}, top_k={top_k}...")

    selector = FeatureSelector(
        variance_threshold=0.0001,
        correlation_threshold=0.95,
        top_k=top_k,
        min_target_corr=0.005,
    )

    target_col = f"target_{horizon}"
    selector.fit(df, target_col=target_col)
    df_selected = selector.transform(df)

    logger.info(f"Feature selection: {df.shape[1]} → {df_selected.shape[1]} columns")
    return df_selected, selector


# ── Walk-Forward CV with Purging ──────────────────────────────────────────────

def walk_forward_evaluate(
    df: pd.DataFrame,
    horizon: str,
    model_class,
    n_splits: int = N_CV_SPLITS,
    n_optuna_trials: int = 20,
    is_classifier: bool = False,
    embargo_pct: float = 0.01,
) -> Dict:
    """
    Walk-forward cross-validation with purging (embargo gap).

    PURGING: After the training period, we skip `embargo` rows before the test
    period starts. This prevents information leakage from overlapping targets
    (e.g. target_5d on the last training day overlaps with the first test day).
    """
    X, y, feature_names = prepare_arrays(df, horizon)

    if is_classifier:
        y_cls = prepare_classification_target(y)
    else:
        y_cls = y

    n = len(X)
    embargo = max(1, int(n * embargo_pct))

    logger.info(f"Walk-forward CV: {n_splits} folds, {n} samples, "
                f"horizon={horizon}, embargo={embargo}")

    tscv = TimeSeriesSplit(n_splits=n_splits)
    fold_metrics = []

    for fold_idx, (train_idx, test_idx) in enumerate(tscv.split(X)):
        # Apply embargo — remove last `embargo` rows from training
        if embargo > 0:
            train_idx = train_idx[:max(1, len(train_idx) - embargo)]

        # Split train into train/val
        val_split = int(len(train_idx) * 0.85)
        train_fold_idx = train_idx[:val_split]
        val_fold_idx = train_idx[val_split:]

        if len(train_fold_idx) < 252 or len(val_fold_idx) < 30:
            logger.warning(f"Fold {fold_idx + 1}: insufficient data, skipping")
            continue

        X_train, y_train = X[train_fold_idx], y_cls[train_fold_idx]
        X_val, y_val = X[val_fold_idx], y_cls[val_fold_idx]
        X_test, y_test = X[test_idx], y_cls[test_idx]

        model = model_class(horizon=horizon, n_optuna_trials=n_optuna_trials)
        model.train(X_train, y_train, X_val, y_val, feature_names)

        test_pred = model.predict(X_test)

        if is_classifier:
            fold_result = compute_classification_metrics(y_test, test_pred)
        else:
            fold_result = compute_metrics(y_test, test_pred)

        fold_metrics.append(fold_result)
        key_metric = "accuracy" if is_classifier else "rmse"
        logger.info(f"Fold {fold_idx + 1}/{n_splits}: {key_metric}={fold_result.get(key_metric, 'N/A')}")

    if not fold_metrics:
        return {}

    # Average across folds
    avg_metrics = {}
    for key in fold_metrics[0].keys():
        values = [m[key] for m in fold_metrics if not np.isnan(m.get(key, float("nan")))]
        if values:
            avg_metrics[f"cv_{key}_mean"] = round(float(np.mean(values)), 6)
            avg_metrics[f"cv_{key}_std"] = round(float(np.std(values)), 6)

    return avg_metrics


# ── Final Model Training ─────────────────────────────────────────────────────

def train_final_model(
    df: pd.DataFrame,
    horizon: str,
    model_class,
    n_optuna_trials: int = 50,
    save_path: Optional[Path] = None,
    is_classifier: bool = False,
):
    """
    Train the final model on train+val data, evaluate on held-out test set.
    """
    train_df, val_df, test_df = get_train_test_split(df, horizon=horizon)

    X_train, y_train, feature_names = prepare_arrays(train_df, horizon)
    X_val, y_val, _ = prepare_arrays(val_df, horizon)
    X_test, y_test, _ = prepare_arrays(test_df, horizon)

    if is_classifier:
        y_train = prepare_classification_target(y_train)
        y_val = prepare_classification_target(y_val)
        y_test_cls = prepare_classification_target(y_test)

    logger.info(f"Final model: train={len(X_train)}, val={len(X_val)}, test={len(X_test)}")

    model = model_class(horizon=horizon, n_optuna_trials=n_optuna_trials)
    model.train(X_train, y_train, X_val, y_val, feature_names)

    test_pred = model.predict(X_test)

    if is_classifier:
        test_metrics = compute_classification_metrics(y_test_cls, test_pred, prefix="test")
        logger.info(f"Test: accuracy={test_metrics['test_accuracy']:.2%} | "
                     f"auc={test_metrics['test_auc']:.4f}")
    else:
        test_metrics = compute_metrics(y_test, test_pred, prefix="test")
        logger.info(f"Test: rmse={test_metrics['test_rmse']:.6f} | "
                     f"dir_acc={test_metrics['test_dir_acc']:.2%} | "
                     f"r2={test_metrics['test_r2']:.4f}")

    if save_path:
        model.save(save_path)

    return model, test_metrics, (X_val, y_val if not is_classifier else prepare_classification_target(y_val)),  (X_test, y_test if not is_classifier else y_test_cls)


# ── Main Training Pipeline ────────────────────────────────────────────────────

def run_training(
    ticker: str = "RELIANCE_NS",
    horizon: str = "1d",
    n_optuna_trials: int = 50,
    run_cv: bool = True,
    feature_selection: bool = True,
    top_k_features: int = 80,
    save: bool = True,
) -> Dict:
    """
    Train ALL model types for one stock and one horizon.

    Trains:
      1. LightGBM regressor
      2. XGBoost regressor
      3. LightGBM classifier
      4. XGBoost classifier
      5. Regression ensemble (LightGBM + XGBoost avg)
      6. Classification ensemble (LightGBM CLF + XGBoost CLF weighted avg)

    Args:
        ticker          : stock ticker (e.g. "RELIANCE_NS")
        horizon         : "1d", "5d", or "20d"
        n_optuna_trials : Optuna trials for final models
        run_cv          : whether to run walk-forward CV
        feature_selection: whether to apply feature selection
        top_k_features  : number of features to keep after selection
        save            : save models to disk

    Returns:
        dict with all results and metrics
    """
    logger.info("=" * 70)
    logger.info(f"TRAINING: {ticker} | horizon={horizon}")
    logger.info("=" * 70)

    # Load features
    try:
        df = load_features(ticker)
    except FileNotFoundError:
        logger.error(f"No features for {ticker}. Run build_all_features() first.")
        return {}

    logger.info(f"Loaded features: {df.shape}")

    # Feature selection
    selector = None
    if feature_selection:
        df, selector = run_feature_selection(df, horizon, top_k=top_k_features)
        logger.info(f"After feature selection: {df.shape}")

    results = {
        "ticker": ticker,
        "horizon": horizon,
        "n_features": df.shape[1],
        "n_samples": df.shape[0],
        "timestamp": datetime.now().isoformat(),
        "models": {},
    }

    # ── Model Definitions ─────────────────────────────────────────────────
    model_configs = [
        ("lightgbm",     LightGBMModel,       False),
        ("xgboost",      XGBoostModel,         False),
        ("lightgbm_clf", LightGBMClassifier,   True),
        ("xgboost_clf",  XGBoostClassifier,    True),
    ]

    # CV trials per fold (fewer for speed)
    cv_trials = max(10, n_optuna_trials // 3)

    for model_name, ModelClass, is_clf in model_configs:
        logger.info(f"\n{'─' * 50}")
        logger.info(f"Training {model_name.upper()}")
        logger.info(f"{'─' * 50}")

        model_results = {}

        # Walk-forward CV
        if run_cv:
            logger.info("Running walk-forward CV...")
            cv_metrics = walk_forward_evaluate(
                df, horizon, ModelClass,
                n_splits=N_CV_SPLITS,
                n_optuna_trials=cv_trials,
                is_classifier=is_clf,
            )
            model_results["cv"] = cv_metrics

        # Final model
        save_path = None
        if save:
            save_path = MODELS_DIR / ticker / horizon / model_name
            save_path.mkdir(parents=True, exist_ok=True)

        model, test_metrics, val_data, test_data = train_final_model(
            df, horizon, ModelClass,
            n_optuna_trials=n_optuna_trials,
            save_path=save_path,
            is_classifier=is_clf,
        )

        model_results["test"] = test_metrics
        model_results["model"] = model
        model_results["val_data"] = val_data
        model_results["test_data"] = test_data
        results["models"][model_name] = model_results

    # ── Build Ensembles ───────────────────────────────────────────────────
    logger.info(f"\n{'─' * 50}")
    logger.info("Building ENSEMBLES")
    logger.info(f"{'─' * 50}")

    # Regression ensemble
    results["models"]["ensemble_reg"] = _build_ensemble(
        results, model_names=["lightgbm", "xgboost"],
        task="regression", horizon=horizon, ticker=ticker, save=save,
    )

    # Classification ensemble
    results["models"]["ensemble_clf"] = _build_ensemble(
        results, model_names=["lightgbm_clf", "xgboost_clf"],
        task="classification", horizon=horizon, ticker=ticker, save=save,
    )

    # Save feature selector
    if save and selector is not None:
        selector.save(f"{ticker}_{horizon}")

    # Print summary
    _print_summary(results)

    # Save results JSON
    if save:
        _save_results_json(results, ticker, horizon)

    return results


def _build_ensemble(
    results: Dict,
    model_names: List[str],
    task: str,
    horizon: str,
    ticker: str,
    save: bool,
) -> Dict:
    """Build and evaluate an ensemble from trained models."""
    models_data = results.get("models", {})

    # Collect validation predictions for fitting ensemble weights
    val_preds = {}
    test_preds = {}
    val_scores = {}
    y_val = None
    y_test = None

    for name in model_names:
        if name not in models_data:
            continue

        model = models_data[name].get("model")
        val_data = models_data[name].get("val_data")
        test_data = models_data[name].get("test_data")

        if model is None or val_data is None or test_data is None:
            continue

        X_val, y_v = val_data
        X_test, y_t = test_data

        val_preds[name] = model.predict(X_val)
        test_preds[name] = model.predict(X_test)

        if y_val is None:
            y_val = y_v
            y_test = y_t

        # Get validation score for weighting
        test_metrics = models_data[name].get("test", {})
        if task == "classification":
            val_scores[name] = test_metrics.get("test_accuracy", 0.5)
        else:
            # For regression, use dir_acc as score (higher = better)
            val_scores[name] = test_metrics.get("test_dir_acc", 0.5)

    if len(val_preds) < 2:
        logger.warning(f"Not enough models for {task} ensemble")
        return {}

    # Fit ensemble
    ensemble = EnsemblePredictor(strategy="weighted", task=task)
    ensemble.fit(val_preds, y_val, val_scores)

    # Evaluate on test set
    ensemble_preds = ensemble.predict(test_preds)

    if task == "classification":
        test_metrics = compute_classification_metrics(y_test, ensemble_preds, prefix="test")
        logger.info(f"Ensemble CLF: accuracy={test_metrics['test_accuracy']:.2%} | "
                     f"auc={test_metrics['test_auc']:.4f}")
    else:
        test_metrics = compute_metrics(y_test, ensemble_preds, prefix="test")
        # Also compute direction accuracy for regression ensemble
        dir_pred = np.sign(ensemble_preds)
        dir_true = np.sign(y_test)
        dir_acc = np.mean(dir_pred == dir_true)
        test_metrics["test_ensemble_dir_acc"] = round(float(dir_acc), 4)
        logger.info(f"Ensemble REG: rmse={test_metrics['test_rmse']:.6f} | "
                     f"dir_acc={dir_acc:.2%}")

    # Save ensemble
    if save:
        ens_name = "ensemble_reg" if task == "regression" else "ensemble_clf"
        save_path = MODELS_DIR / ticker / horizon / ens_name
        ensemble.save(save_path)

    return {"test": test_metrics, "ensemble": ensemble}


# ── Train All Stocks ──────────────────────────────────────────────────────────

def run_training_all_stocks(
    horizon: str = "1d",
    n_optuna_trials: int = 50,
    run_cv: bool = False,
    feature_selection: bool = True,
    top_k_features: int = 80,
) -> Dict:
    """
    Train models for ALL stocks for a given horizon.

    Estimated time:
      - No CV, 50 trials:  ~2-3 hours for all stocks
      - With CV, 50 trials: ~6-8 hours

    Usage:
        from training.trainer import run_training_all_stocks
        all_results = run_training_all_stocks(horizon="1d")
    """
    logger.info("=" * 70)
    logger.info(f"TRAINING ALL STOCKS | horizon={horizon}")
    logger.info("=" * 70)

    all_features = load_all_features()
    all_results = {}
    failed = []

    for i, ticker in enumerate(all_features.keys()):
        try:
            logger.info(f"\n[{i + 1}/{len(all_features)}] Training {ticker}...")
            result = run_training(
                ticker=ticker,
                horizon=horizon,
                n_optuna_trials=n_optuna_trials,
                run_cv=run_cv,
                feature_selection=feature_selection,
                top_k_features=top_k_features,
                save=True,
            )
            all_results[ticker] = result
        except Exception as e:
            logger.error(f"{ticker}: training failed — {e}")
            failed.append(ticker)

    # Print leaderboard
    _print_leaderboard(all_results, horizon)

    logger.info(f"\nTraining complete: {len(all_results)} succeeded, {len(failed)} failed")
    if failed:
        logger.warning(f"Failed: {failed}")

    return all_results


def run_training_all_horizons(
    ticker: str = "RELIANCE_NS",
    n_optuna_trials: int = 50,
    run_cv: bool = True,
    feature_selection: bool = True,
) -> Dict:
    """Train one stock across all 3 horizons (1d, 5d, 20d)."""
    results = {}
    for horizon_name in HORIZONS.keys():
        logger.info(f"\n{'═' * 70}")
        logger.info(f"HORIZON: {horizon_name}")
        logger.info(f"{'═' * 70}")
        results[horizon_name] = run_training(
            ticker=ticker,
            horizon=horizon_name,
            n_optuna_trials=n_optuna_trials,
            run_cv=run_cv,
            feature_selection=feature_selection,
            save=True,
        )
    return results


# ── Printing ──────────────────────────────────────────────────────────────────

def _print_summary(results: Dict) -> None:
    """Print a clean performance summary table."""
    ticker = results.get("ticker", "?")
    horizon = results.get("horizon", "?")

    logger.info(f"\n{'═' * 70}")
    logger.info(f"RESULTS SUMMARY — {ticker} | horizon={horizon}")
    logger.info(f"{'═' * 70}")

    # Regression models
    reg_models = ["lightgbm", "xgboost", "ensemble_reg"]
    has_reg = any(m in results.get("models", {}) for m in reg_models)

    if has_reg:
        logger.info(f"\n{'─' * 70}")
        logger.info(f"{'REGRESSION':^70}")
        logger.info(f"{'Model':<18} {'Test RMSE':<12} {'Test MAE':<12} {'R²':<8} {'Dir Acc':<10}")
        logger.info(f"{'─' * 70}")

        for model_name in reg_models:
            test = results.get("models", {}).get(model_name, {}).get("test", {})
            if not test:
                continue
            rmse = test.get("test_rmse", test.get("test_ensemble_rmse", float("nan")))
            mae = test.get("test_mae", float("nan"))
            r2 = test.get("test_r2", float("nan"))
            dir_acc = test.get("test_dir_acc", test.get("test_ensemble_dir_acc", float("nan")))
            logger.info(f"{model_name:<18} {rmse:<12.6f} {mae:<12.6f} {r2:<8.4f} {dir_acc:<10.2%}")

    # Classification models
    clf_models = ["lightgbm_clf", "xgboost_clf", "ensemble_clf"]
    has_clf = any(m in results.get("models", {}) for m in clf_models)

    if has_clf:
        logger.info(f"\n{'─' * 70}")
        logger.info(f"{'CLASSIFICATION':^70}")
        logger.info(f"{'Model':<18} {'Accuracy':<12} {'AUC':<10} {'F1':<10} {'Precision':<12} {'Recall':<10}")
        logger.info(f"{'─' * 70}")

        for model_name in clf_models:
            test = results.get("models", {}).get(model_name, {}).get("test", {})
            if not test:
                continue
            acc = test.get("test_accuracy", float("nan"))
            auc = test.get("test_auc", float("nan"))
            f1 = test.get("test_f1", float("nan"))
            prec = test.get("test_precision", float("nan"))
            rec = test.get("test_recall", float("nan"))
            logger.info(f"{model_name:<18} {acc:<12.2%} {auc:<10.4f} {f1:<10.4f} {prec:<12.4f} {rec:<10.4f}")

    logger.info(f"{'═' * 70}")


def _print_leaderboard(all_results: Dict, horizon: str) -> None:
    """Print a leaderboard comparing all stocks."""
    rows = []
    for ticker, result in all_results.items():
        # Get best classification accuracy
        best_acc = 0.0
        for model_name in ["lightgbm_clf", "xgboost_clf", "ensemble_clf"]:
            test = result.get("models", {}).get(model_name, {}).get("test", {})
            acc = test.get("test_accuracy", 0.0)
            best_acc = max(best_acc, acc)

        # Get best regression dir acc
        best_dir = 0.0
        for model_name in ["lightgbm", "xgboost", "ensemble_reg"]:
            test = result.get("models", {}).get(model_name, {}).get("test", {})
            dir_acc = test.get("test_dir_acc", test.get("test_ensemble_dir_acc", 0.0))
            best_dir = max(best_dir, dir_acc)

        rows.append({
            "ticker": ticker,
            "best_clf_acc": best_acc,
            "best_reg_dir": best_dir,
        })

    if not rows:
        return

    rows.sort(key=lambda x: x["best_clf_acc"], reverse=True)

    logger.info(f"\n{'═' * 60}")
    logger.info(f"LEADERBOARD — horizon={horizon}")
    logger.info(f"{'═' * 60}")
    logger.info(f"{'Rank':<6} {'Ticker':<18} {'Best CLF Acc':<15} {'Best REG Dir':<15}")
    logger.info(f"{'─' * 60}")

    for i, row in enumerate(rows[:20]):
        logger.info(f"{i + 1:<6} {row['ticker']:<18} {row['best_clf_acc']:<15.2%} {row['best_reg_dir']:<15.2%}")

    logger.info(f"{'═' * 60}")


def _save_results_json(results: Dict, ticker: str, horizon: str) -> None:
    """Save results to JSON (excluding non-serializable objects)."""
    results_path = MODELS_DIR / ticker / horizon / "results.json"
    results_path.parent.mkdir(parents=True, exist_ok=True)

    serializable = {
        "ticker": results.get("ticker"),
        "horizon": results.get("horizon"),
        "n_features": results.get("n_features"),
        "n_samples": results.get("n_samples"),
        "timestamp": results.get("timestamp"),
    }

    for m_name, m_results in results.get("models", {}).items():
        if isinstance(m_results, dict):
            serializable[m_name] = {
                k: v for k, v in m_results.items()
                if k not in ("model", "val_data", "test_data", "ensemble")
            }

    with open(results_path, "w") as f:
        json.dump(serializable, f, indent=2, default=str)
    logger.info(f"Results saved to {results_path}")


# ── Entry Point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    # Quick test — train all 4 models + ensembles on Reliance for 1d horizon
    results = run_training(
        ticker="RELIANCE_NS",
        horizon="1d",
        n_optuna_trials=20,      # 20 for quick test
        run_cv=False,
        feature_selection=True,
        top_k_features=80,
        save=True,
    )
