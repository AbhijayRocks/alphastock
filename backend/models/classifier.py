"""
models/classifier.py — Classification models for direction prediction.

WHY CLASSIFICATION INSTEAD OF REGRESSION?
  Our regression models predict the exact return (e.g. +0.3% tomorrow).
  But what we REALLY care about is DIRECTION: will it go UP or DOWN?

  A regression model optimizes RMSE — it wants to minimize the SIZE of
  prediction errors. But a small error in the wrong direction (predicting
  +0.1% when actual is -0.1%) is worse than a large error in the right
  direction (predicting +2% when actual is +0.5%).

  Classification models optimize directly for getting the direction right.
  They use log-loss (cross-entropy), which penalizes confident wrong
  predictions heavily. This is exactly what we want for trading.

WHAT WE OUTPUT:
  A probability between 0 and 1:
    0.0 = model is confident stock goes DOWN
    0.5 = model has no clue (uncertain)
    1.0 = model is confident stock goes UP

  We only trade when confidence is high (e.g. probability > 0.6 or < 0.4).
  This selective trading dramatically improves real-world performance.
"""

import logging
import pickle
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Union

import numpy as np
import pandas as pd
import lightgbm as lgb
import xgboost as xgb
import optuna
from sklearn.metrics import (
    accuracy_score, f1_score, roc_auc_score,
    log_loss, precision_score, recall_score
)

from models.base import BaseModel
from config import MODELS_DIR, SEED, LOG_LEVEL

logging.basicConfig(level=LOG_LEVEL, format="%(asctime)s | %(levelname)s | %(message)s")
logger = logging.getLogger(__name__)
optuna.logging.set_verbosity(optuna.logging.WARNING)


def compute_classification_metrics(
    y_true: np.ndarray,
    y_pred_proba: np.ndarray,
    prefix: str = "",
) -> Dict:
    """
    Compute all classification metrics.

    METRICS EXPLAINED:
      Accuracy : % of predictions where direction was correct. 55%+ = useful.
      AUC      : Area Under ROC Curve. Measures ranking quality. 0.5 = random,
                 0.55+ = useful, 0.60+ = very good.
      F1       : Harmonic mean of precision and recall. Balances false
                 positives and false negatives.
      Log Loss : Cross-entropy. Lower = better calibrated probabilities.
                 This is what the model actually optimizes.
      Precision: Of all "UP" predictions, how many were actually UP?
      Recall   : Of all actual UP days, how many did we catch?
    """
    y_pred = (y_pred_proba > 0.5).astype(int)

    acc = accuracy_score(y_true, y_pred)
    f1 = f1_score(y_true, y_pred, zero_division=0)
    prec = precision_score(y_true, y_pred, zero_division=0)
    rec = recall_score(y_true, y_pred, zero_division=0)

    try:
        auc = roc_auc_score(y_true, y_pred_proba)
    except Exception:
        auc = 0.5

    try:
        ll = log_loss(y_true, np.clip(y_pred_proba, 1e-7, 1 - 1e-7))
    except Exception:
        ll = float("nan")

    p = f"{prefix}_" if prefix else ""
    return {
        f"{p}accuracy":  round(float(acc), 4),
        f"{p}precision": round(float(prec), 4),
        f"{p}recall":    round(float(rec), 4),
        f"{p}f1":        round(float(f1), 4),
        f"{p}auc":       round(float(auc), 4),
        f"{p}log_loss":  round(float(ll), 6),
    }


# ── LightGBM Classifier ───────────────────────────────────────────────────────

class LightGBMClassifier(BaseModel):
    """
    LightGBM binary classifier for direction prediction.

    Predicts probability of stock going UP (return > 0).
    Optimized with Optuna for maximum directional accuracy.
    """

    def __init__(self, horizon: str = "1d", n_optuna_trials: int = 50):
        super().__init__(name="lightgbm_clf", horizon=horizon)
        self.n_optuna_trials = n_optuna_trials
        self._model: Optional[lgb.Booster] = None
        self._best_params: Dict = {}

    def _optuna_objective(
        self,
        trial: optuna.Trial,
        X_train: np.ndarray,
        y_train: np.ndarray,
        X_val: np.ndarray,
        y_val: np.ndarray,
        feature_names: List[str],
        sample_weights_train: Optional[np.ndarray] = None,
    ) -> float:
        """Optuna objective — minimizes validation log loss."""
        params = {
            "objective":        "binary",
            "metric":           "binary_logloss",
            "verbosity":        -1,
            "force_col_wise":   True,
            "random_state":     SEED,
            "n_jobs":           -1,
            "is_unbalance":     True,
            "num_leaves":        trial.suggest_int("num_leaves", 15, 150),
            "learning_rate":     trial.suggest_float("learning_rate", 0.005, 0.1, log=True),
            "feature_fraction":  trial.suggest_float("feature_fraction", 0.4, 1.0),
            "bagging_fraction":  trial.suggest_float("bagging_fraction", 0.4, 1.0),
            "bagging_freq":      trial.suggest_int("bagging_freq", 1, 10),
            "min_child_samples": trial.suggest_int("min_child_samples", 10, 150),
            "reg_alpha":         trial.suggest_float("reg_alpha", 1e-4, 10.0, log=True),
            "reg_lambda":        trial.suggest_float("reg_lambda", 1e-4, 10.0, log=True),
            "max_depth":         trial.suggest_int("max_depth", 3, 10),
            "min_gain_to_split": trial.suggest_float("min_gain_to_split", 0.0, 2.0),
            "path_smooth":       trial.suggest_float("path_smooth", 0.0, 10.0),
        }

        train_data = lgb.Dataset(
            X_train, label=y_train,
            feature_name=feature_names,
            weight=sample_weights_train,
        )
        val_data = lgb.Dataset(X_val, label=y_val, reference=train_data)

        model = lgb.train(
            params, train_data,
            num_boost_round=1500,
            valid_sets=[val_data],
            callbacks=[
                lgb.early_stopping(100, verbose=False),
                lgb.log_evaluation(period=-1),
            ],
        )

        val_pred = model.predict(X_val)
        return float(log_loss(y_val, np.clip(val_pred, 1e-7, 1 - 1e-7)))

    def train(
        self,
        X_train: np.ndarray,
        y_train: np.ndarray,
        X_val: np.ndarray,
        y_val: np.ndarray,
        feature_names: Optional[List[str]] = None,
    ) -> Dict:
        """Train LightGBM classifier with Optuna tuning."""
        if feature_names is None:
            feature_names = [f"f{i}" for i in range(X_train.shape[1])]
        self.feature_names = feature_names

        # Sample weights — recent data weighted more heavily
        # Rationale: market dynamics change; recent patterns matter more
        n = len(X_train)
        sample_weights = np.linspace(0.5, 1.0, n)  # oldest=0.5, newest=1.0

        logger.info(f"LightGBM CLF: tuning with {self.n_optuna_trials} Optuna trials...")

        study = optuna.create_study(
            direction="minimize",
            sampler=optuna.samplers.TPESampler(seed=SEED),
        )
        study.optimize(
            lambda trial: self._optuna_objective(
                trial, X_train, y_train, X_val, y_val,
                feature_names, sample_weights,
            ),
            n_trials=self.n_optuna_trials,
            show_progress_bar=False,
        )

        self._best_params = study.best_params
        logger.info(f"LightGBM CLF best val log_loss: {study.best_value:.6f}")

        # Final model with best params
        best_params = {
            "objective":      "binary",
            "metric":         "binary_logloss",
            "verbosity":      -1,
            "force_col_wise": True,
            "random_state":   SEED,
            "n_jobs":         -1,
            "is_unbalance":   True,
            **self._best_params,
        }

        train_data = lgb.Dataset(
            X_train, label=y_train,
            feature_name=feature_names,
            weight=sample_weights,
        )
        val_data = lgb.Dataset(X_val, label=y_val, reference=train_data)

        self._model = lgb.train(
            best_params, train_data,
            num_boost_round=3000,
            valid_sets=[train_data, val_data],
            valid_names=["train", "val"],
            callbacks=[
                lgb.early_stopping(100, verbose=False),
                lgb.log_evaluation(period=500),
            ],
        )

        # Compute metrics
        train_pred = self._model.predict(X_train)
        val_pred = self._model.predict(X_val)

        self.metrics = {
            **compute_classification_metrics(y_train, train_pred, "train"),
            **compute_classification_metrics(y_val, val_pred, "val"),
        }

        self.is_fitted = True
        logger.info(
            f"LightGBM CLF trained | val_acc={self.metrics['val_accuracy']:.2%} "
            f"| val_auc={self.metrics['val_auc']:.4f}"
        )
        return self.metrics

    def predict(self, X: np.ndarray) -> np.ndarray:
        """Return probabilities of going UP (0.0 to 1.0)."""
        assert self.is_fitted, "Model not trained. Call train() first."
        return self._model.predict(X)

    def predict_direction(self, X: np.ndarray, threshold: float = 0.5) -> np.ndarray:
        """Return binary direction: 1 = UP, 0 = DOWN."""
        return (self.predict(X) > threshold).astype(int)

    def get_feature_importance(self) -> Optional[pd.Series]:
        if not self.is_fitted:
            return None
        imp = self._model.feature_importance(importance_type="gain")
        return pd.Series(imp, index=self.feature_names).sort_values(ascending=False)

    def save(self, path: Union[str, Path]) -> None:
        path = Path(path)
        path.mkdir(parents=True, exist_ok=True)
        self._model.save_model(str(path / "lgbm_clf_model.txt"))
        with open(path / "lgbm_clf_meta.pkl", "wb") as f:
            pickle.dump({
                "feature_names": self.feature_names,
                "best_params":   self._best_params,
                "metrics":       self.metrics,
                "horizon":       self.horizon,
            }, f)
        logger.info(f"LightGBM CLF saved to {path}")

    def load(self, path: Union[str, Path]) -> None:
        path = Path(path)
        self._model = lgb.Booster(model_file=str(path / "lgbm_clf_model.txt"))
        with open(path / "lgbm_clf_meta.pkl", "rb") as f:
            meta = pickle.load(f)
        self.feature_names = meta["feature_names"]
        self._best_params  = meta["best_params"]
        self.metrics       = meta["metrics"]
        self.horizon       = meta["horizon"]
        self.is_fitted     = True
        logger.info(f"LightGBM CLF loaded from {path}")


# ── XGBoost Classifier ────────────────────────────────────────────────────────

class XGBoostClassifier(BaseModel):
    """
    XGBoost binary classifier for direction prediction.

    Uses GPU acceleration (CUDA) when available.
    Different tree-building algorithm than LightGBM → ensemble diversity.
    """

    def __init__(self, horizon: str = "1d", n_optuna_trials: int = 50):
        super().__init__(name="xgboost_clf", horizon=horizon)
        self.n_optuna_trials = n_optuna_trials
        self._model: Optional[xgb.Booster] = None
        self._best_params: Dict = {}

    def _use_gpu(self) -> bool:
        try:
            import torch
            return torch.cuda.is_available()
        except ImportError:
            return False

    def _optuna_objective(
        self,
        trial: optuna.Trial,
        dtrain: xgb.DMatrix,
        dval: xgb.DMatrix,
        y_val: np.ndarray,
    ) -> float:
        params = {
            "objective":        "binary:logistic",
            "eval_metric":      "logloss",
            "tree_method":      "hist",
            "device":           "cuda" if self._use_gpu() else "cpu",
            "seed":             SEED,
            "verbosity":        0,
            "scale_pos_weight": trial.suggest_float("scale_pos_weight", 0.5, 2.0),
            "learning_rate":    trial.suggest_float("learning_rate", 0.005, 0.1, log=True),
            "max_depth":        trial.suggest_int("max_depth", 3, 10),
            "min_child_weight": trial.suggest_int("min_child_weight", 1, 30),
            "gamma":            trial.suggest_float("gamma", 0.0, 2.0),
            "subsample":        trial.suggest_float("subsample", 0.4, 1.0),
            "colsample_bytree": trial.suggest_float("colsample_bytree", 0.4, 1.0),
            "reg_alpha":        trial.suggest_float("reg_alpha", 1e-4, 10.0, log=True),
            "reg_lambda":       trial.suggest_float("reg_lambda", 1e-4, 10.0, log=True),
        }

        model = xgb.train(
            params, dtrain,
            num_boost_round=1500,
            evals=[(dval, "val")],
            early_stopping_rounds=100,
            verbose_eval=False,
        )

        val_pred = model.predict(dval)
        return float(log_loss(y_val, np.clip(val_pred, 1e-7, 1 - 1e-7)))

    def train(
        self,
        X_train: np.ndarray,
        y_train: np.ndarray,
        X_val: np.ndarray,
        y_val: np.ndarray,
        feature_names: Optional[List[str]] = None,
    ) -> Dict:
        """Train XGBoost classifier with Optuna tuning."""
        if feature_names is None:
            feature_names = [f"f{i}" for i in range(X_train.shape[1])]
        self.feature_names = feature_names

        # Sample weights — recent data weighted more
        n = len(X_train)
        sample_weights = np.linspace(0.5, 1.0, n)

        dtrain = xgb.DMatrix(
            X_train, label=y_train,
            feature_names=feature_names,
            weight=sample_weights,
        )
        dval = xgb.DMatrix(X_val, label=y_val, feature_names=feature_names)

        logger.info(f"XGBoost CLF: tuning with {self.n_optuna_trials} Optuna trials...")

        study = optuna.create_study(
            direction="minimize",
            sampler=optuna.samplers.TPESampler(seed=SEED),
        )
        study.optimize(
            lambda trial: self._optuna_objective(trial, dtrain, dval, y_val),
            n_trials=self.n_optuna_trials,
            show_progress_bar=False,
        )

        self._best_params = study.best_params
        logger.info(f"XGBoost CLF best val log_loss: {study.best_value:.6f}")

        # Final model
        final_params = {
            "objective":   "binary:logistic",
            "eval_metric": "logloss",
            "tree_method": "hist",
            "device":      "cuda" if self._use_gpu() else "cpu",
            "seed":        SEED,
            "verbosity":   0,
            **self._best_params,
        }

        self._model = xgb.train(
            final_params, dtrain,
            num_boost_round=3000,
            evals=[(dtrain, "train"), (dval, "val")],
            early_stopping_rounds=100,
            verbose_eval=500,
        )

        # Metrics
        train_pred = self._model.predict(dtrain)
        val_pred = self._model.predict(dval)

        self.metrics = {
            **compute_classification_metrics(y_train, train_pred, "train"),
            **compute_classification_metrics(y_val, val_pred, "val"),
        }

        self.is_fitted = True
        logger.info(
            f"XGBoost CLF trained | val_acc={self.metrics['val_accuracy']:.2%} "
            f"| val_auc={self.metrics['val_auc']:.4f}"
        )
        return self.metrics

    def predict(self, X: np.ndarray) -> np.ndarray:
        assert self.is_fitted, "Model not trained."
        dmatrix = xgb.DMatrix(X, feature_names=self.feature_names)
        return self._model.predict(dmatrix)

    def predict_direction(self, X: np.ndarray, threshold: float = 0.5) -> np.ndarray:
        return (self.predict(X) > threshold).astype(int)

    def get_feature_importance(self) -> Optional[pd.Series]:
        if not self.is_fitted:
            return None
        scores = self._model.get_score(importance_type="gain")
        return pd.Series(scores).sort_values(ascending=False)

    def save(self, path: Union[str, Path]) -> None:
        path = Path(path)
        path.mkdir(parents=True, exist_ok=True)
        self._model.save_model(str(path / "xgb_clf_model.json"))
        with open(path / "xgb_clf_meta.pkl", "wb") as f:
            pickle.dump({
                "feature_names": self.feature_names,
                "best_params":   self._best_params,
                "metrics":       self.metrics,
                "horizon":       self.horizon,
            }, f)
        logger.info(f"XGBoost CLF saved to {path}")

    def load(self, path: Union[str, Path]) -> None:
        path = Path(path)
        self._model = xgb.Booster()
        self._model.load_model(str(path / "xgb_clf_model.json"))
        with open(path / "xgb_clf_meta.pkl", "rb") as f:
            meta = pickle.load(f)
        self.feature_names = meta["feature_names"]
        self._best_params  = meta["best_params"]
        self.metrics       = meta["metrics"]
        self.horizon       = meta["horizon"]
        self.is_fitted     = True
        logger.info(f"XGBoost CLF loaded from {path}")
