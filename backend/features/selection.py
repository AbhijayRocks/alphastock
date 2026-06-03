"""
features/selection.py — Intelligent feature selection for maximum model accuracy.

WHY THIS IS THE #1 MOST IMPORTANT IMPROVEMENT:
  Our pipeline generates 195 features. Most of them are NOISE — they have no
  real predictive power for stock returns. When you feed noise features to a
  GBDT model, it overfits to random patterns in the noise during training,
  then fails on unseen data (test set). This is why we got 50% accuracy.

  By selecting only the 60-80 features that actually carry signal, we:
    1. Reduce overfitting → better test accuracy
    2. Speed up training → more Optuna trials in same time
    3. Improve interpretability → know what actually drives predictions

THREE-STAGE SELECTION:
  Stage 1 — Variance Filter:
    Remove features that barely change (near-constant). If a feature has
    the same value 99% of the time, it can't help predict anything.

  Stage 2 — Correlation Filter:
    When two features are >95% correlated, they carry the same information.
    Keeping both doubles the noise without adding signal. We keep the one
    with higher target correlation.

  Stage 3 — Importance Filter:
    Train a quick LightGBM model, rank features by "gain" importance
    (how much each feature reduces the loss). Keep top K features.
    This is the most powerful filter — lets the data decide what matters.
"""

import logging
import pickle
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
import lightgbm as lgb

from config import SEED, FEATURES_DIR, LOG_LEVEL

logging.basicConfig(level=LOG_LEVEL, format="%(asctime)s | %(levelname)s | %(message)s")
logger = logging.getLogger(__name__)

SELECTION_DIR = FEATURES_DIR / "selection"
SELECTION_DIR.mkdir(parents=True, exist_ok=True)


class FeatureSelector:
    """
    Three-stage feature selection pipeline.

    Usage:
        selector = FeatureSelector(top_k=80)
        selected_features = selector.fit(df, target_col="target_1d")
        df_selected = selector.transform(df)

    Or for one-shot:
        df_selected = selector.fit_transform(df, target_col="target_1d")
    """

    def __init__(
        self,
        variance_threshold: float = 0.0001,
        correlation_threshold: float = 0.95,
        top_k: int = 80,
        min_target_corr: float = 0.005,
    ):
        """
        Args:
            variance_threshold   : features with variance below this are removed
            correlation_threshold: correlated pairs above this → drop the weaker one
            top_k                : keep this many features after importance ranking
            min_target_corr      : minimum |correlation with target| to survive
        """
        self.variance_threshold = variance_threshold
        self.correlation_threshold = correlation_threshold
        self.top_k = top_k
        self.min_target_corr = min_target_corr
        self.selected_features: Optional[List[str]] = None
        self._importance_scores: Optional[pd.Series] = None
        self._removed_log: Dict[str, List[str]] = {}

    def fit(self, df: pd.DataFrame, target_col: str = "target_1d") -> List[str]:
        """
        Run the three-stage selection and store the chosen feature names.

        Args:
            df         : full feature DataFrame (features + target columns)
            target_col : which target to optimize selection for

        Returns:
            list of selected feature column names
        """
        # Separate features from targets
        target_cols = [c for c in df.columns if c.startswith("target_")]
        feature_cols = [c for c in df.columns if c not in target_cols]

        X = df[feature_cols].select_dtypes(include=[np.number]).copy()
        y = df[target_col].copy()

        # Drop rows where target is NaN
        valid = ~y.isna()
        X = X[valid]
        y = y[valid]

        # Clean features
        X = X.replace([np.inf, -np.inf], np.nan)
        X = X.fillna(X.median())

        initial_count = len(X.columns)
        logger.info(f"Feature selection: starting with {initial_count} features")

        # ── Stage 1: Variance Filter ──────────────────────────────────────────
        keep_cols = self._variance_filter(X)
        removed = [c for c in X.columns if c not in keep_cols]
        self._removed_log["variance"] = removed
        X = X[keep_cols]
        logger.info(f"  Stage 1 (variance): {initial_count} → {len(X.columns)} "
                     f"(removed {len(removed)})")

        # ── Stage 2: Correlation Filter ───────────────────────────────────────
        pre_count = len(X.columns)
        keep_cols = self._correlation_filter(X, y)
        removed = [c for c in X.columns if c not in keep_cols]
        self._removed_log["correlation"] = removed
        X = X[keep_cols]
        logger.info(f"  Stage 2 (correlation): {pre_count} → {len(X.columns)} "
                     f"(removed {len(removed)})")

        # ── Stage 3: Target Correlation Filter ────────────────────────────────
        pre_count = len(X.columns)
        keep_cols = self._target_correlation_filter(X, y)
        removed = [c for c in X.columns if c not in keep_cols]
        self._removed_log["target_corr"] = removed
        X = X[keep_cols]
        logger.info(f"  Stage 3 (target corr): {pre_count} → {len(X.columns)} "
                     f"(removed {len(removed)})")

        # ── Stage 4: Importance Filter ────────────────────────────────────────
        pre_count = len(X.columns)
        keep_cols = self._importance_filter(X, y)
        removed = [c for c in X.columns if c not in keep_cols]
        self._removed_log["importance"] = removed
        X = X[keep_cols]
        logger.info(f"  Stage 4 (importance): {pre_count} → {len(X.columns)}")

        self.selected_features = list(X.columns)
        logger.info(f"Feature selection complete: {initial_count} → {len(self.selected_features)} features")

        return self.selected_features

    def transform(self, df: pd.DataFrame) -> pd.DataFrame:
        """Apply fitted selection to a DataFrame. Keeps selected features + target columns."""
        if self.selected_features is None:
            raise RuntimeError("Call fit() before transform()")

        target_cols = [c for c in df.columns if c.startswith("target_")]
        available = [c for c in self.selected_features if c in df.columns]

        return df[available + target_cols]

    def fit_transform(self, df: pd.DataFrame, target_col: str = "target_1d") -> pd.DataFrame:
        """Fit and transform in one call."""
        self.fit(df, target_col)
        return self.transform(df)

    # ── Stage Implementations ──────────────────────────────────────────────────

    def _variance_filter(self, X: pd.DataFrame) -> List[str]:
        """Remove features that barely change (near-constant)."""
        variances = X.var()
        keep = variances[variances > self.variance_threshold].index.tolist()
        return keep

    def _correlation_filter(self, X: pd.DataFrame, y: pd.Series) -> List[str]:
        """
        When two features correlate > threshold, drop the one less correlated
        with the target. This removes redundant information.
        """
        corr_matrix = X.corr().abs()
        target_corr = X.corrwith(y).abs().fillna(0)

        # Upper triangle of correlation matrix (avoid double-counting)
        upper = corr_matrix.where(
            np.triu(np.ones(corr_matrix.shape, dtype=bool), k=1)
        )

        to_drop = set()
        for col in upper.columns:
            high_corr_cols = upper.index[upper[col] > self.correlation_threshold].tolist()
            for idx in high_corr_cols:
                # Drop the feature with lower target correlation
                if target_corr.get(col, 0) < target_corr.get(idx, 0):
                    to_drop.add(col)
                else:
                    to_drop.add(idx)

        return [c for c in X.columns if c not in to_drop]

    def _target_correlation_filter(self, X: pd.DataFrame, y: pd.Series) -> List[str]:
        """Remove features with essentially zero correlation to the target."""
        target_corr = X.corrwith(y).abs().fillna(0)
        keep = target_corr[target_corr >= self.min_target_corr].index.tolist()
        return keep

    def _importance_filter(self, X: pd.DataFrame, y: pd.Series) -> List[str]:
        """
        Train a quick LightGBM and keep top-K features by gain importance.
        This is the most powerful filter — data-driven feature selection.
        """
        feature_names = [str(c) for c in X.columns]
        train_data = lgb.Dataset(
            X.values, label=y.values,
            feature_name=feature_names,
            free_raw_data=False,
        )

        params = {
            "objective": "regression",
            "metric": "rmse",
            "verbosity": -1,
            "num_leaves": 63,
            "learning_rate": 0.05,
            "feature_fraction": 0.7,
            "bagging_fraction": 0.7,
            "bagging_freq": 5,
            "min_child_samples": 20,
            "random_state": SEED,
            "n_jobs": -1,
        }

        model = lgb.train(
            params, train_data,
            num_boost_round=300,
            callbacks=[lgb.log_evaluation(period=-1)],
        )

        importance = pd.Series(
            model.feature_importance(importance_type="gain"),
            index=feature_names,
        ).sort_values(ascending=False)

        self._importance_scores = importance

        # Keep top K features (or all if fewer than K remain)
        k = min(self.top_k, len(importance))
        # Only keep features that were actually used (importance > 0)
        nonzero = importance[importance > 0]
        k = min(k, len(nonzero))
        top_features = nonzero.head(k).index.tolist()

        # Log top 15 for visibility
        logger.info(f"  Top 15 features by importance:")
        for i, (feat, score) in enumerate(importance.head(15).items()):
            logger.info(f"    {i+1:2d}. {feat:40s} {score:10.1f}")

        return top_features

    # ── Persistence ────────────────────────────────────────────────────────────

    def save(self, name: str = "default") -> Path:
        """Save the fitted selector to disk."""
        path = SELECTION_DIR / f"selector_{name}.pkl"
        with open(path, "wb") as f:
            pickle.dump({
                "selected_features": self.selected_features,
                "importance_scores": self._importance_scores,
                "removed_log": self._removed_log,
                "params": {
                    "variance_threshold": self.variance_threshold,
                    "correlation_threshold": self.correlation_threshold,
                    "top_k": self.top_k,
                    "min_target_corr": self.min_target_corr,
                },
            }, f)
        logger.info(f"Selector saved to {path}")
        return path

    def load(self, name: str = "default") -> "FeatureSelector":
        """Load a fitted selector from disk."""
        path = SELECTION_DIR / f"selector_{name}.pkl"
        if not path.exists():
            raise FileNotFoundError(f"No selector at {path}")
        with open(path, "rb") as f:
            data = pickle.load(f)
        self.selected_features = data["selected_features"]
        self._importance_scores = data["importance_scores"]
        self._removed_log = data["removed_log"]
        params = data["params"]
        self.variance_threshold = params["variance_threshold"]
        self.correlation_threshold = params["correlation_threshold"]
        self.top_k = params["top_k"]
        self.min_target_corr = params["min_target_corr"]
        logger.info(f"Selector loaded: {len(self.selected_features)} features")
        return self

    def get_importance(self) -> Optional[pd.Series]:
        """Return feature importance scores from the quick LightGBM."""
        return self._importance_scores

    def get_removal_summary(self) -> Dict[str, int]:
        """How many features were removed at each stage."""
        return {stage: len(removed) for stage, removed in self._removed_log.items()}


# ── Convenience Function ───────────────────────────────────────────────────────

def select_features(
    df: pd.DataFrame,
    target_col: str = "target_1d",
    top_k: int = 80,
    save_name: Optional[str] = None,
) -> Tuple[pd.DataFrame, FeatureSelector]:
    """
    One-call feature selection.

    Usage:
        df_selected, selector = select_features(df, target_col="target_5d", top_k=80)
    """
    selector = FeatureSelector(top_k=top_k)
    selector.fit(df, target_col=target_col)
    df_selected = selector.transform(df)

    if save_name:
        selector.save(save_name)

    return df_selected, selector


if __name__ == "__main__":
    # Quick test on RELIANCE_NS
    from features.pipeline import load_features

    df = load_features("RELIANCE_NS")
    print(f"Before selection: {df.shape}")

    df_selected, selector = select_features(df, target_col="target_1d", top_k=80)
    print(f"After selection: {df_selected.shape}")

    print(f"\nRemoval summary: {selector.get_removal_summary()}")

    imp = selector.get_importance()
    if imp is not None:
        print(f"\nTop 20 features:\n{imp.head(20)}")
