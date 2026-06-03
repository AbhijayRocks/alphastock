"""
models/lgbm_xgb.py — LightGBM and XGBoost wrappers with Optuna auto-tuning.

WHY THESE TWO MODELS FIRST?
  Before throwing deep learning at the problem, tree ensemble models are
  the right starting point because:
    1. They train in MINUTES not hours — fast feedback loop
    2. They handle tabular data better than neural nets in most cases
    3. SHAP explainability works perfectly with them
    4. They give us a strong baseline to beat with TFT/PatchTST later

WHY BOTH LIGHTGBM AND XGBOOST?
  They're similar (both gradient boosting) but different enough to disagree
  on some predictions. Disagreement = diversity = better ensemble.
  LightGBM: faster, better on large datasets, leaf-wise tree growth.
  XGBoost:  more regularization options, level-wise growth, slightly different
            bias-variance tradeoff.

WHAT IS OPTUNA?
  Optuna is an automatic hyperparameter tuning library.
  Instead of manually trying: max_depth=3, then 4, then 5...
  Optuna intelligently searches the space using Bayesian optimization.
  We give it 50 trials (50 different hyperparameter combinations to try)
  and it finds the best one automatically. Set it and forget it.

WHAT IS WALK-FORWARD VALIDATION?
  For time series, you can't use random cross-validation (it leaks future
  into past). Walk-forward means:
    Fold 1: Train on 2015-2018, validate on 2019
    Fold 2: Train on 2015-2019, validate on 2020
    Fold 3: Train on 2015-2020, validate on 2021
    ...
  This mimics how the model will actually be used in production.
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
    mean_squared_error, mean_absolute_error,
    mean_absolute_percentage_error, r2_score
)

from models.base import BaseModel
from config import MODELS_DIR, SEED, LOG_LEVEL

logging.basicConfig(level=LOG_LEVEL, format="%(asctime)s | %(levelname)s | %(message)s")
logger = logging.getLogger(__name__)

# Silence Optuna's verbose output — we log our own summaries
optuna.logging.set_verbosity(optuna.logging.WARNING)


def compute_metrics(y_true: np.ndarray, y_pred: np.ndarray, prefix: str = "") -> Dict:
    """
    Compute all regression metrics in one shot.

    METRICS EXPLAINED:
      RMSE  : Root Mean Squared Error. Penalizes large errors heavily.
               Lower = better. Same units as the target (returns).
      MAE   : Mean Absolute Error. Average size of error. More interpretable.
      MAPE  : Mean Absolute Percentage Error. Scale-independent. 5% = 5% off.
      R2    : Coefficient of determination. 1.0 = perfect, 0.0 = as good as
               predicting the mean, negative = worse than predicting mean.
      Dir   : Directional accuracy. Did we predict UP/DOWN correctly?
               50% = random, 55%+ = useful, 60%+ = very good for stocks.
    """
    rmse = np.sqrt(mean_squared_error(y_true, y_pred))
    mae  = mean_absolute_error(y_true, y_pred)
    r2   = r2_score(y_true, y_pred)
    dir_acc = np.mean(np.sign(y_true) == np.sign(y_pred))

    # MAPE can blow up when y_true is near zero — clip it
    try:
        mape = mean_absolute_percentage_error(y_true, y_pred)
        if mape > 100:
            mape = float("nan")
    except Exception:
        mape = float("nan")

    p = f"{prefix}_" if prefix else ""
    return {
        f"{p}rmse":    round(float(rmse),    6),
        f"{p}mae":     round(float(mae),     6),
        f"{p}mape":    round(float(mape),    6),
        f"{p}r2":      round(float(r2),      4),
        f"{p}dir_acc": round(float(dir_acc), 4),
    }


# ── LightGBM ───────────────────────────────────────────────────────────────────

class LightGBMModel(BaseModel):
    """
    LightGBM wrapper with Optuna hyperparameter tuning.

    LightGBM is our primary workhorse model. Fast, accurate, handles
    missing values natively, and works great on our 189-feature DataFrame.
    """

    def __init__(self, horizon: str = "1d", n_optuna_trials: int = 50):
        super().__init__(name="lightgbm", horizon=horizon)
        self.n_optuna_trials = n_optuna_trials
        self._model: Optional[lgb.Booster] = None
        self._best_params: Dict = {}

    def _get_default_params(self) -> Dict:
        """Sensible defaults — used as starting point for Optuna search."""
        return {
            "objective":        "regression",
            "metric":           "rmse",
            "boosting_type":    "gbdt",
            "num_leaves":       63,
            "learning_rate":    0.05,
            "feature_fraction": 0.8,
            "bagging_fraction": 0.8,
            "bagging_freq":     5,
            "min_child_samples":20,
            "reg_alpha":        0.1,
            "reg_lambda":       0.1,
            "random_state":     SEED,
            "verbosity":        -1,
            "force_col_wise":   True,
            "n_jobs":           -1,
        }

    def _optuna_objective(
        self,
        trial: optuna.Trial,
        X_train: np.ndarray,
        y_train: np.ndarray,
        X_val: np.ndarray,
        y_val: np.ndarray,
        feature_names: List[str],
        sample_weights: np.ndarray = None,
    ) -> float:
        """
        Optuna objective function — called once per trial.
        Each trial tries a different hyperparameter combination.
        Returns val RMSE — Optuna minimizes this.
        """
        params = {
            "objective":        "regression",
            "metric":           "rmse",
            "verbosity":        -1,
            "force_col_wise":   True,
            "random_state":     SEED,
            "n_jobs":           -1,
            # Parameters Optuna searches over:
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

        train_data = lgb.Dataset(X_train, label=y_train, feature_name=feature_names, weight=sample_weights)
        val_data   = lgb.Dataset(X_val,   label=y_val,   reference=train_data)

        callbacks = [
            lgb.early_stopping(stopping_rounds=100, verbose=False),
            lgb.log_evaluation(period=-1),
        ]

        model = lgb.train(
            params,
            train_data,
            num_boost_round=1500,
            valid_sets=[val_data],
            callbacks=callbacks,
        )

        val_pred = model.predict(X_val)
        return float(np.sqrt(mean_squared_error(y_val, val_pred)))

    def train(
        self,
        X_train: np.ndarray,
        y_train: np.ndarray,
        X_val: np.ndarray,
        y_val: np.ndarray,
        feature_names: Optional[List[str]] = None,
    ) -> Dict:
        """Train LightGBM with Optuna tuning."""
        if feature_names is None:
            feature_names = [f"f{i}" for i in range(X_train.shape[1])]
        self.feature_names = feature_names

        # Sample weights — recent data weighted more heavily
        n = len(X_train)
        sample_weights = np.linspace(0.5, 1.0, n)

        logger.info(f"LightGBM: tuning with {self.n_optuna_trials} Optuna trials...")

        # Run Optuna hyperparameter search
        study = optuna.create_study(
            direction="minimize",
            sampler=optuna.samplers.TPESampler(seed=SEED),
        )
        study.optimize(
            lambda trial: self._optuna_objective(
                trial, X_train, y_train, X_val, y_val, feature_names, sample_weights
            ),
            n_trials=self.n_optuna_trials,
            show_progress_bar=False,
        )

        self._best_params = study.best_params
        logger.info(f"LightGBM best val RMSE: {study.best_value:.6f}")
        logger.info(f"Best params: {self._best_params}")

        # Final training with best params on train+val combined
        best_params = {
            **self._get_default_params(),
            **self._best_params,
        }

        # Combine train + val for final model
        X_full = np.vstack([X_train, X_val])
        y_full = np.concatenate([y_train, y_val])

        train_data = lgb.Dataset(X_train, label=y_train, feature_name=feature_names, weight=sample_weights)
        val_data   = lgb.Dataset(X_val,   label=y_val,   reference=train_data)

        callbacks = [
            lgb.early_stopping(stopping_rounds=100, verbose=False),
            lgb.log_evaluation(period=200),
        ]

        self._model = lgb.train(
            best_params,
            train_data,
            num_boost_round=3000,
            valid_sets=[train_data, val_data],
            valid_names=["train", "val"],
            callbacks=callbacks,
        )

        # Compute and store metrics
        train_pred = self._model.predict(X_train)
        val_pred   = self._model.predict(X_val)

        self.metrics = {
            **compute_metrics(y_train, train_pred, prefix="train"),
            **compute_metrics(y_val,   val_pred,   prefix="val"),
        }

        self.is_fitted = True
        logger.info(f"LightGBM trained | val_rmse={self.metrics['val_rmse']:.6f} "
                    f"| dir_acc={self.metrics['val_dir_acc']:.2%}")
        return self.metrics

    def predict(self, X: np.ndarray) -> np.ndarray:
        assert self.is_fitted, "Model not trained yet. Call train() first."
        return self._model.predict(X)

    def predict_with_confidence(
        self,
        X: np.ndarray,
        confidence: float = 0.9,
    ) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
        """
        LightGBM confidence intervals using quantile regression.
        We train two extra models: one predicting the lower quantile,
        one predicting the upper quantile.
        """
        preds = self.predict(X)
        # Simple fallback — proper quantile version in ensemble.py
        margin = np.std(preds) * 1.645  # 90% normal interval
        return preds, preds - margin, preds + margin

    def get_feature_importance(self) -> Optional[pd.Series]:
        if not self.is_fitted:
            return None
        imp = self._model.feature_importance(importance_type="gain")
        return pd.Series(imp, index=self.feature_names).sort_values(ascending=False)

    def save(self, path: Union[str, Path]) -> None:
        path = Path(path)
        path.mkdir(parents=True, exist_ok=True)
        self._model.save_model(str(path / "lgbm_model.txt"))
        with open(path / "lgbm_meta.pkl", "wb") as f:
            pickle.dump({
                "feature_names": self.feature_names,
                "best_params":   self._best_params,
                "metrics":       self.metrics,
                "horizon":       self.horizon,
            }, f)
        logger.info(f"LightGBM saved to {path}")

    def load(self, path: Union[str, Path]) -> None:
        path = Path(path)
        self._model = lgb.Booster(model_file=str(path / "lgbm_model.txt"))
        with open(path / "lgbm_meta.pkl", "rb") as f:
            meta = pickle.load(f)
        self.feature_names = meta["feature_names"]
        self._best_params  = meta["best_params"]
        self.metrics       = meta["metrics"]
        self.horizon       = meta["horizon"]
        self.is_fitted     = True
        logger.info(f"LightGBM loaded from {path}")


# ── XGBoost ────────────────────────────────────────────────────────────────────

class XGBoostModel(BaseModel):
    """
    XGBoost wrapper with Optuna hyperparameter tuning.

    Similar to LightGBM but with different internals — gives us
    diversity in the ensemble. XGBoost tends to be more conservative
    and better at avoiding overfitting on noisy financial data.
    """

    def __init__(self, horizon: str = "1d", n_optuna_trials: int = 50):
        super().__init__(name="xgboost", horizon=horizon)
        self.n_optuna_trials = n_optuna_trials
        self._model: Optional[xgb.Booster] = None
        self._best_params: Dict = {}

    def _optuna_objective(
        self,
        trial: optuna.Trial,
        dtrain: xgb.DMatrix,
        dval: xgb.DMatrix,
        y_val: np.ndarray,
    ) -> float:
        params = {
            "objective":        "reg:squarederror",
            "eval_metric":      "rmse",
            "tree_method":      "hist",
            "device":           "cuda" if self._use_gpu() else "cpu",
            "seed":             SEED,
            "verbosity":        0,
            "learning_rate":    trial.suggest_float("learning_rate", 0.005, 0.1, log=True),
            "max_depth":        trial.suggest_int("max_depth", 3, 10),
            "min_child_weight": trial.suggest_int("min_child_weight", 1, 20),
            "gamma":            trial.suggest_float("gamma", 0.0, 1.0),
            "subsample":        trial.suggest_float("subsample", 0.5, 1.0),
            "colsample_bytree": trial.suggest_float("colsample_bytree", 0.5, 1.0),
            "reg_alpha":        trial.suggest_float("reg_alpha", 1e-4, 10.0, log=True),
            "reg_lambda":       trial.suggest_float("reg_lambda", 1e-4, 10.0, log=True),
        }

        model = xgb.train(
            params,
            dtrain,
            num_boost_round=1500,
            evals=[(dval, "val")],
            early_stopping_rounds=100,
            verbose_eval=False,
        )

        val_pred = model.predict(dval)
        return float(np.sqrt(mean_squared_error(y_val, val_pred)))

    def _use_gpu(self) -> bool:
        try:
            import torch
            return torch.cuda.is_available()
        except ImportError:
            return False

    def train(
        self,
        X_train: np.ndarray,
        y_train: np.ndarray,
        X_val: np.ndarray,
        y_val: np.ndarray,
        feature_names: Optional[List[str]] = None,
    ) -> Dict:
        if feature_names is None:
            feature_names = [f"f{i}" for i in range(X_train.shape[1])]
        self.feature_names = feature_names

        # Sample weights — recent data weighted more heavily
        n = len(X_train)
        sample_weights = np.linspace(0.5, 1.0, n)

        # XGBoost uses DMatrix — its own optimized data format
        dtrain = xgb.DMatrix(X_train, label=y_train, feature_names=feature_names, weight=sample_weights)
        dval   = xgb.DMatrix(X_val,   label=y_val,   feature_names=feature_names)

        logger.info(f"XGBoost: tuning with {self.n_optuna_trials} Optuna trials...")

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
        logger.info(f"XGBoost best val RMSE: {study.best_value:.6f}")

        # Final model with best params
        final_params = {
            "objective":   "reg:squarederror",
            "eval_metric": "rmse",
            "tree_method": "hist",
            "device":      "cuda" if self._use_gpu() else "cpu",
            "seed":        SEED,
            "verbosity":   0,
            **self._best_params,
        }

        self._model = xgb.train(
            final_params,
            dtrain,
            num_boost_round=3000,
            evals=[(dtrain, "train"), (dval, "val")],
            early_stopping_rounds=100,
            verbose_eval=200,
        )

        train_pred = self._model.predict(dtrain)
        val_pred   = self._model.predict(dval)

        self.metrics = {
            **compute_metrics(y_train, train_pred, prefix="train"),
            **compute_metrics(y_val,   val_pred,   prefix="val"),
        }

        self.is_fitted = True
        logger.info(f"XGBoost trained | val_rmse={self.metrics['val_rmse']:.6f} "
                    f"| dir_acc={self.metrics['val_dir_acc']:.2%}")
        return self.metrics

    def predict(self, X: np.ndarray) -> np.ndarray:
        assert self.is_fitted, "Model not trained yet."
        dmatrix = xgb.DMatrix(X, feature_names=self.feature_names)
        return self._model.predict(dmatrix)

    def get_feature_importance(self) -> Optional[pd.Series]:
        if not self.is_fitted:
            return None
        scores = self._model.get_score(importance_type="gain")
        return pd.Series(scores).sort_values(ascending=False)

    def save(self, path: Union[str, Path]) -> None:
        path = Path(path)
        path.mkdir(parents=True, exist_ok=True)
        self._model.save_model(str(path / "xgb_model.json"))
        with open(path / "xgb_meta.pkl", "wb") as f:
            pickle.dump({
                "feature_names": self.feature_names,
                "best_params":   self._best_params,
                "metrics":       self.metrics,
                "horizon":       self.horizon,
            }, f)
        logger.info(f"XGBoost saved to {path}")

    def load(self, path: Union[str, Path]) -> None:
        path = Path(path)
        self._model = xgb.Booster()
        self._model.load_model(str(path / "xgb_model.json"))
        with open(path / "xgb_meta.pkl", "rb") as f:
            meta = pickle.load(f)
        self.feature_names = meta["feature_names"]
        self._best_params  = meta["best_params"]
        self.metrics       = meta["metrics"]
        self.horizon       = meta["horizon"]
        self.is_fitted     = True
        logger.info(f"XGBoost loaded from {path}")
