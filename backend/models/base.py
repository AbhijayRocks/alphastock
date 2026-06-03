"""
models/base.py — Abstract base class every model must implement.

WHY THIS EXISTS:
  We have multiple models: LightGBM, XGBoost, TFT, PatchTST.
  Without a common interface, every file that uses models needs to know
  WHICH model it's talking to and call different methods.

  With a base class, the trainer, API, and dashboard just call:
    model.train(X, y)
    model.predict(X)
    model.save(path)
    model.load(path)
  ...and it works for ANY model. Swap LightGBM for TFT? Zero code changes
  in the trainer. This is called polymorphism — one of the most powerful
  ideas in software engineering.

ANALOGY:
  Think of it like a job contract. Every employee (model) must be able to:
  show up (load), do work (train), deliver results (predict), and clock out
  (save). HOW they do it is their own business.
"""

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Dict, Optional, Tuple, Union

import numpy as np
import pandas as pd


class BaseModel(ABC):
    """
    Abstract base class for all prediction models.
    Every model in models/ must inherit from this and implement all methods.
    """

    def __init__(self, name: str, horizon: str = "1d"):
        """
        Args:
            name   : human-readable model name e.g. "lightgbm", "xgboost"
            horizon: prediction horizon e.g. "1d", "5d", "20d"
        """
        self.name    = name
        self.horizon = horizon
        self.is_fitted = False
        self.feature_names: Optional[list] = None
        self.metrics: Dict = {}   # stores train/val/test metrics after fitting

    @abstractmethod
    def train(
        self,
        X_train: np.ndarray,
        y_train: np.ndarray,
        X_val: np.ndarray,
        y_val: np.ndarray,
        feature_names: Optional[list] = None,
    ) -> Dict:
        """
        Train the model.

        Args:
            X_train      : training features, shape (n_train, n_features)
            y_train      : training targets, shape (n_train,)
            X_val        : validation features
            y_val        : validation targets
            feature_names: list of feature column names (for SHAP, logging)

        Returns:
            dict of training metrics: {"train_rmse": ..., "val_rmse": ..., etc.}
        """
        pass

    @abstractmethod
    def predict(self, X: np.ndarray) -> np.ndarray:
        """
        Generate predictions.

        Args:
            X: features, shape (n_samples, n_features)

        Returns:
            predictions, shape (n_samples,)
        """
        pass

    @abstractmethod
    def save(self, path: Union[str, Path]) -> None:
        """Save model artifacts to disk."""
        pass

    @abstractmethod
    def load(self, path: Union[str, Path]) -> None:
        """Load model artifacts from disk."""
        pass

    def predict_with_confidence(
        self,
        X: np.ndarray,
        confidence: float = 0.9,
    ) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
        """
        Generate predictions with confidence intervals.

        Default implementation uses a simple percentile-based approach.
        Deep learning models override this with proper uncertainty estimation.

        Returns:
            (predictions, lower_bound, upper_bound)
        """
        preds = self.predict(X)
        # Simple symmetric interval using historical prediction error
        # Subclasses with proper uncertainty (quantile regression, MC dropout)
        # should override this
        margin = np.abs(preds) * 0.1   # 10% margin as fallback
        return preds, preds - margin, preds + margin

    def get_feature_importance(self) -> Optional[pd.Series]:
        """
        Return feature importances as a named Series.
        Models that support this (tree models, attention models) override it.
        Returns None if not supported.
        """
        return None

    def __repr__(self) -> str:
        status = "fitted" if self.is_fitted else "not fitted"
        return f"{self.__class__.__name__}(name={self.name}, horizon={self.horizon}, {status})"
