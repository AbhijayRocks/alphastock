"""
models/ensemble.py — Combine multiple models for better predictions.

WHY ENSEMBLE?
  "The wisdom of crowds" — when you ask multiple experts and average their
  opinions, you almost always get a better answer than any single expert.

  LightGBM and XGBoost use different tree-building algorithms:
    LightGBM: leaf-wise growth (deeper, narrower trees)
    XGBoost:  level-wise growth (shallower, wider trees)

  They make DIFFERENT errors on different data points. When we average
  their predictions, the errors partially cancel out → better accuracy.

  In practice, ensembling 2-4 diverse models adds 1-5% accuracy. This is
  one of the most reliable techniques in ML — every Kaggle winner uses it.

THREE STRATEGIES:
  1. Simple Average   : equal weight to each model (baseline)
  2. Weighted Average : weight by validation performance (smart default)
  3. Stacking         : train a meta-learner on model outputs (most powerful)
"""

import logging
import pickle
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
from sklearn.linear_model import RidgeCV, LogisticRegressionCV

from config import SEED, MODELS_DIR, LOG_LEVEL

logging.basicConfig(level=LOG_LEVEL, format="%(asctime)s | %(levelname)s | %(message)s")
logger = logging.getLogger(__name__)


class EnsemblePredictor:
    """
    Combines predictions from multiple models.

    Works for both regression (return prediction) and classification
    (direction probability) tasks.

    Usage:
        ensemble = EnsemblePredictor(strategy="weighted", task="classification")
        ensemble.fit(
            model_predictions={"lgbm": lgbm_preds, "xgb": xgb_preds},
            y_true=y_val,
            val_scores={"lgbm": 0.58, "xgb": 0.55},  # accuracy scores
        )
        final_preds = ensemble.predict({"lgbm": lgbm_test, "xgb": xgb_test})
    """

    def __init__(
        self,
        strategy: str = "weighted",
        task: str = "classification",
    ):
        """
        Args:
            strategy: "simple", "weighted", or "stacking"
            task    : "regression" or "classification"
        """
        assert strategy in ("simple", "weighted", "stacking")
        assert task in ("regression", "classification")

        self.strategy = strategy
        self.task = task
        self.weights: Optional[Dict[str, float]] = None
        self._meta_model = None
        self.model_names: List[str] = []
        self.is_fitted = False

    def fit(
        self,
        model_predictions: Dict[str, np.ndarray],
        y_true: np.ndarray,
        val_scores: Optional[Dict[str, float]] = None,
    ) -> None:
        """
        Fit the ensemble combiner.

        Args:
            model_predictions: {model_name: prediction_array} on VALIDATION set
            y_true           : ground truth for validation set
            val_scores       : {model_name: performance_score} (higher=better)
        """
        self.model_names = list(model_predictions.keys())

        if len(self.model_names) < 2:
            logger.warning("Ensemble with <2 models — will just pass through single model")
            self.weights = {self.model_names[0]: 1.0} if self.model_names else {}
            self.is_fitted = True
            return

        if self.strategy == "simple":
            self.weights = {
                name: 1.0 / len(self.model_names)
                for name in self.model_names
            }

        elif self.strategy == "weighted":
            if val_scores is None:
                # Fall back to simple average
                self.weights = {
                    name: 1.0 / len(self.model_names)
                    for name in self.model_names
                }
            else:
                # Softmax weighting — better models get exponentially more weight
                scores = np.array([
                    val_scores.get(name, 0.5) for name in self.model_names
                ])
                # Temperature-scaled softmax (temperature=5 for moderate differentiation)
                exp_scores = np.exp((scores - scores.mean()) * 5)
                normalized = exp_scores / exp_scores.sum()
                self.weights = {
                    name: float(w)
                    for name, w in zip(self.model_names, normalized)
                }

            logger.info(f"Ensemble weights: {self.weights}")

        elif self.strategy == "stacking":
            # Stack predictions as features → train a meta-learner
            X_stack = np.column_stack([
                model_predictions[name] for name in self.model_names
            ])

            if self.task == "classification":
                self._meta_model = LogisticRegressionCV(
                    Cs=[0.01, 0.1, 1.0, 10.0],
                    cv=3,
                    random_state=SEED,
                    max_iter=1000,
                )
                self._meta_model.fit(X_stack, y_true)
                logger.info(f"Stacking meta-learner (LogisticCV) fitted, "
                            f"C={self._meta_model.C_[0]:.4f}")
            else:
                self._meta_model = RidgeCV(
                    alphas=[0.01, 0.1, 1.0, 10.0, 100.0],
                    cv=3,
                )
                self._meta_model.fit(X_stack, y_true)
                logger.info(f"Stacking meta-learner (RidgeCV) fitted, "
                            f"alpha={self._meta_model.alpha_:.4f}")

        self.is_fitted = True

    def predict(self, model_predictions: Dict[str, np.ndarray]) -> np.ndarray:
        """
        Combine predictions from multiple models into final prediction.

        Args:
            model_predictions: {model_name: prediction_array} on TEST set

        Returns:
            combined prediction array
        """
        assert self.is_fitted, "Call fit() first"

        if self.strategy in ("simple", "weighted"):
            result = np.zeros(len(next(iter(model_predictions.values()))))
            total_weight = 0.0

            for name in self.model_names:
                if name in model_predictions:
                    w = self.weights.get(name, 0)
                    result += w * model_predictions[name]
                    total_weight += w

            # Normalize in case some models are missing
            if total_weight > 0 and total_weight != 1.0:
                result /= total_weight

            return result

        elif self.strategy == "stacking":
            X_stack = np.column_stack([
                model_predictions[name] for name in self.model_names
            ])
            if self.task == "classification":
                return self._meta_model.predict_proba(X_stack)[:, 1]
            else:
                return self._meta_model.predict(X_stack)

    def predict_direction(
        self,
        model_predictions: Dict[str, np.ndarray],
        threshold: float = 0.5,
    ) -> np.ndarray:
        """For classification: return binary direction (1=UP, 0=DOWN)."""
        proba = self.predict(model_predictions)
        return (proba > threshold).astype(int)

    # ── Persistence ────────────────────────────────────────────────────────────

    def save(self, path: Path) -> None:
        path = Path(path)
        path.mkdir(parents=True, exist_ok=True)
        with open(path / "ensemble.pkl", "wb") as f:
            pickle.dump({
                "strategy":    self.strategy,
                "task":        self.task,
                "weights":     self.weights,
                "meta_model":  self._meta_model,
                "model_names": self.model_names,
            }, f)
        logger.info(f"Ensemble saved to {path / 'ensemble.pkl'}")

    def load(self, path: Path) -> None:
        path = Path(path)
        with open(path / "ensemble.pkl", "rb") as f:
            data = pickle.load(f)
        self.strategy    = data["strategy"]
        self.task        = data["task"]
        self.weights     = data["weights"]
        self._meta_model = data["meta_model"]
        self.model_names = data["model_names"]
        self.is_fitted   = True
        logger.info(f"Ensemble loaded: strategy={self.strategy}, models={self.model_names}")

    def __repr__(self) -> str:
        status = "fitted" if self.is_fitted else "not fitted"
        return (f"EnsemblePredictor(strategy={self.strategy}, task={self.task}, "
                f"models={self.model_names}, {status})")
