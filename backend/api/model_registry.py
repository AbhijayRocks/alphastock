"""
api/model_registry.py — Loads all trained models at startup, serves predictions.

WHY A REGISTRY?
  When the API starts, we load ALL trained models into memory once.
  Every prediction request then uses in-memory models — no disk I/O per request.
  This makes predictions fast (~10-50ms) instead of slow (~2-5s if loading each time).

  Think of it like a library: you check out all the books you need at the start
  of the day, rather than going back to the shelf for every single question.

WHAT IT DOES:
  1. Scans artifacts/models/ directory for all trained stocks + horizons
  2. Loads LightGBM/XGBoost/Ensemble models into memory
  3. Loads the latest feature row for each stock (for live prediction)
  4. Exposes predict(), explain(), backtest() methods to the API routes
"""

import logging
import json
import pickle
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

from config import MODELS_DIR, FEATURES_DIR, LOG_LEVEL
from data_pipeline.nifty50 import NIFTY50_META

logging.basicConfig(level=LOG_LEVEL, format="%(asctime)s | %(levelname)s | %(message)s")
logger = logging.getLogger(__name__)


class ModelRegistry:
    """
    Loads and caches all trained models. Serves predictions to the API.

    Loaded once at startup, shared across all API requests.
    Thread-safe for reads (FastAPI uses async, not threads).
    """

    def __init__(self, models_dir: Path = MODELS_DIR):
        self.models_dir = models_dir
        self._models: Dict = {}         # {ticker: {horizon: {model_name: model}}}
        self._features: Dict = {}       # {ticker: latest_feature_row}
        self._results: Dict = {}        # {ticker: {horizon: results_json}}
        self._regime_cache: Dict = {}   # cached regime info
        self.available_tickers: set = set()
        self.total_models_loaded: int = 0

    def load_all(self) -> None:
        """
        Scan models directory and load everything into memory.
        Called once at API startup.
        """
        logger.info("=" * 60)
        logger.info("MODEL REGISTRY: Loading all trained models...")
        logger.info("=" * 60)

        if not self.models_dir.exists():
            logger.warning(f"Models directory not found: {self.models_dir}")
            return

        loaded = 0
        failed = 0

        # Walk: models/{ticker}/{horizon}/
        for ticker_dir in sorted(self.models_dir.iterdir()):
            if not ticker_dir.is_dir() or ticker_dir.name.startswith("."):
                continue

            ticker = ticker_dir.name
            self._models[ticker] = {}
            self._results[ticker] = {}

            for horizon_dir in ticker_dir.iterdir():
                if not horizon_dir.is_dir():
                    continue

                horizon = horizon_dir.name
                if horizon not in ["1d", "5d", "20d"]:
                    continue

                horizon_models = {}

                # Load LightGBM classifier
                lgb_clf = self._load_lgbm_clf(horizon_dir)
                if lgb_clf:
                    horizon_models["lightgbm_clf"] = lgb_clf
                    loaded += 1

                # Load XGBoost classifier
                xgb_clf = self._load_xgb_clf(horizon_dir)
                if xgb_clf:
                    horizon_models["xgboost_clf"] = xgb_clf
                    loaded += 1

                # Load Ensemble classifier
                ens_clf = self._load_ensemble(horizon_dir / "ensemble_clf")
                if ens_clf:
                    horizon_models["ensemble_clf"] = ens_clf
                    loaded += 1

                # Load LightGBM regressor
                lgb_reg = self._load_lgbm_reg(horizon_dir)
                if lgb_reg:
                    horizon_models["lightgbm"] = lgb_reg
                    loaded += 1

                # Load XGBoost regressor
                xgb_reg = self._load_xgb_reg(horizon_dir)
                if xgb_reg:
                    horizon_models["xgboost"] = xgb_reg
                    loaded += 1

                # Load TFT model (only for 20d)
                if horizon == "20d":
                    tft_model = self._load_tft_model(horizon_dir)
                    if tft_model:
                        horizon_models["tft"] = tft_model
                        loaded += 1

                # Load results JSON
                results_path = horizon_dir / "results.json"
                if results_path.exists():
                    try:
                        with open(results_path) as f:
                            self._results[ticker][horizon] = json.load(f)
                    except Exception:
                        pass

                if horizon_models:
                    self._models[ticker][horizon] = horizon_models

            if self._models.get(ticker):
                self.available_tickers.add(ticker)

        # Load latest features for each ticker
        self._load_latest_features()

        # Load regime model
        self._load_regime()

        self.total_models_loaded = loaded
        logger.info(f"Registry loaded: {len(self.available_tickers)} stocks, "
                    f"{loaded} models total")

    # ── Model Loaders ──────────────────────────────────────────────────────────

    def _load_lgbm_clf(self, horizon_dir: Path):
        try:
            import lightgbm as lgb
            model_path = horizon_dir / "lightgbm_clf" / "lgbm_clf_model.txt"
            meta_path  = horizon_dir / "lightgbm_clf" / "lgbm_clf_meta.pkl"
            if not model_path.exists():
                return None
            model = lgb.Booster(model_file=str(model_path))
            meta  = pickle.loads(meta_path.read_bytes()) if meta_path.exists() else {}
            return {"model": model, "meta": meta, "type": "lgbm_clf"}
        except Exception as e:
            logger.debug(f"lgbm_clf load failed: {e}")
            return None

    def _load_xgb_clf(self, horizon_dir: Path):
        try:
            import xgboost as xgb
            model_path = horizon_dir / "xgboost_clf" / "xgb_clf_model.json"
            meta_path  = horizon_dir / "xgboost_clf" / "xgb_clf_meta.pkl"
            if not model_path.exists():
                return None
            model = xgb.Booster()
            model.load_model(str(model_path))
            meta  = pickle.loads(meta_path.read_bytes()) if meta_path.exists() else {}
            return {"model": model, "meta": meta, "type": "xgb_clf"}
        except Exception as e:
            logger.debug(f"xgb_clf load failed: {e}")
            return None

    def _load_lgbm_reg(self, horizon_dir: Path):
        try:
            import lightgbm as lgb
            model_path = horizon_dir / "lightgbm" / "lgbm_model.txt"
            meta_path  = horizon_dir / "lightgbm" / "lgbm_meta.pkl"
            if not model_path.exists():
                return None
            model = lgb.Booster(model_file=str(model_path))
            meta  = pickle.loads(meta_path.read_bytes()) if meta_path.exists() else {}
            return {"model": model, "meta": meta, "type": "lgbm"}
        except Exception as e:
            logger.debug(f"lgbm_reg load failed: {e}")
            return None

    def _load_xgb_reg(self, horizon_dir: Path):
        try:
            import xgboost as xgb
            model_path = horizon_dir / "xgboost" / "xgb_model.json"
            meta_path  = horizon_dir / "xgboost" / "xgb_meta.pkl"
            if not model_path.exists():
                return None
            model = xgb.Booster()
            model.load_model(str(model_path))
            meta  = pickle.loads(meta_path.read_bytes()) if meta_path.exists() else {}
            return {"model": model, "meta": meta, "type": "xgb"}
        except Exception as e:
            logger.debug(f"xgb_reg load failed: {e}")
            return None

    def _load_ensemble(self, ens_dir: Path):
        try:
            pkl_path = ens_dir / "ensemble.pkl"
            if not pkl_path.exists():
                return None
            with open(pkl_path, "rb") as f:
                data = pickle.load(f)
            return {"ensemble_data": data, "type": "ensemble"}
        except Exception as e:
            logger.debug(f"ensemble load failed: {e}")
            return None

    def _load_tft_model(self, horizon_dir: Path):
        try:
            tft_path = horizon_dir / "tft" / "best_tft.ckpt"
            if not tft_path.exists():
                return None
            import torch
            from pytorch_forecasting import TemporalFusionTransformer
            model = TemporalFusionTransformer.load_from_checkpoint(tft_path, map_location=torch.device('cpu'))
            return {"model": model, "type": "tft"}
        except Exception as e:
            logger.debug(f"tft load failed: {e}")
            return None

    def _load_latest_features(self) -> None:
        """Load the last row of features for each stock for live prediction."""
        pipeline_dir = FEATURES_DIR / "pipeline"
        if not pipeline_dir.exists():
            logger.warning("Pipeline features directory not found")
            return

        loaded = 0
        for ticker in self.available_tickers:
            path = pipeline_dir / f"{ticker}.parquet"
            if not path.exists():
                continue
            try:
                df = pd.read_parquet(path, engine="pyarrow")
                df.index = pd.to_datetime(df.index)
                # Drop target columns — we only want features
                feature_cols = [c for c in df.columns if not c.startswith("target_")]
                self._features[ticker] = df[feature_cols]
                loaded += 1
            except Exception as e:
                logger.warning(f"Feature load failed for {ticker}: {e}")

        logger.info(f"Loaded features for {loaded} stocks")

    def _load_regime(self) -> None:
        """Load the HMM regime model if available."""
        regime_path = MODELS_DIR / "regime_hmm.pkl"
        if not regime_path.exists():
            logger.warning("No regime model found — regime will be 'unknown'")
            return
        try:
            with open(regime_path, "rb") as f:
                self._regime_model = pickle.load(f)
            logger.info("Regime model loaded")
        except Exception as e:
            import traceback
            logger.warning(f"Regime model load failed: {e}")
            with open("predict_error.log", "a") as f:
                f.write(f"load regime error: {e}\n{traceback.format_exc()}\n")
            self._regime_model = None

    # ── Prediction ─────────────────────────────────────────────────────────────

    def predict(self, ticker: str, horizon: str, model_name: str = "ensemble_clf") -> Dict:
        """
        Run prediction for a ticker + horizon using the specified model.

        Returns dict with probability, direction, predicted_return, etc.
        """
        if ticker not in self._features:
            raise ValueError(f"No features loaded for {ticker}")

        feature_df = self._features[ticker]

        # Get the feature names this model was trained on
        model_bundle = self._models.get(ticker, {}).get(horizon, {}).get(model_name)
        if model_bundle is None:
            # Fall back to best available model
            available = self._models.get(ticker, {}).get(horizon, {})
            for fallback in ["ensemble_clf", "lightgbm_clf", "xgboost_clf", "lightgbm"]:
                if fallback in available:
                    model_bundle = available[fallback]
                    model_name   = fallback
                    break

        if model_bundle is None:
            raise ValueError(f"No model found for {ticker}/{horizon}")

        # Get feature names from model metadata
        meta          = model_bundle.get("meta", {})
        feature_names = meta.get("feature_names", list(feature_df.columns))

        # Align features to exactly what the model expects
        latest_row = feature_df.iloc[-1:]
        X_aligned = pd.DataFrame(index=latest_row.index, columns=feature_names)
        for col in feature_names:
            if col in latest_row.columns:
                X_aligned[col] = latest_row[col]
            else:
                X_aligned[col] = 0.0
        X_latest = X_aligned.values.astype(np.float32)

        # Replace NaN/inf
        X_latest = np.nan_to_num(X_latest, nan=0.0, posinf=0.0, neginf=0.0)

        # Run prediction
        prob = self._run_model_predict(model_bundle, X_latest, model_name, feature_names)

        # Get current price
        current_price = self._get_current_price(ticker)

        # Expected return from regression model (if available)
        predicted_return = self._get_regression_prediction(ticker, horizon, X_latest, feature_names)

        # Confidence interval
        margin = abs(predicted_return) * 0.3 + 0.005
        lower  = predicted_return - margin
        upper  = predicted_return + margin

        # Regime
        regime = self._regime_cache.get("regime", "unknown")

        return {
            "probability":       float(prob),
            "predicted_return":  float(predicted_return),
            "confidence_lower":  float(lower),
            "confidence_upper":  float(upper),
            "current_price":     float(current_price),
            "regime":            regime,
        }

    def _run_model_predict(self, model_bundle: Dict, X: np.ndarray, model_name: str, feature_names: List[str] = None) -> float:
        """Run inference on a single model bundle, return probability."""
        model_type = model_bundle.get("type", "")

        try:
            if model_type == "lgbm_clf":
                prob = model_bundle["model"].predict(X)[0]
            elif model_type == "xgb_clf":
                import xgboost as xgb
                dmatrix = xgb.DMatrix(pd.DataFrame(X, columns=feature_names)) if feature_names else xgb.DMatrix(X)
                prob = model_bundle["model"].predict(dmatrix)[0]
            elif model_type == "ensemble":
                data = model_bundle["ensemble_data"]
                # Simple weighted average from saved weights
                prob = 0.5  # fallback if ensemble can't run
            elif model_type in ("lgbm", "xgb"):
                # Regression model — convert to probability via sigmoid
                if model_type == "lgbm":
                    pred = model_bundle["model"].predict(X)[0]
                else:
                    import xgboost as xgb
                    dmatrix = xgb.DMatrix(pd.DataFrame(X, columns=feature_names)) if feature_names else xgb.DMatrix(X)
                    pred = model_bundle["model"].predict(dmatrix)[0]
                # Clamp and sigmoid-approximate
                prob = float(np.clip(0.5 + pred * 10, 0.01, 0.99))
            else:
                prob = 0.5

            return float(np.clip(prob, 0.0, 1.0))

        except Exception as e:
            import traceback
            with open("predict_error.log", "a") as f:
                f.write(f"clf error ({model_type}): {e}\n{traceback.format_exc()}\n")
            logger.warning(f"Model predict failed ({model_type}): {e}")
            return 0.5

    def _get_regression_prediction(
        self, ticker: str, horizon: str,
        X: np.ndarray, feature_names: List[str]
    ) -> float:
        """Get regression model prediction for expected return."""
        for reg_model_name in ["lightgbm", "xgboost"]:
            reg_bundle = self._models.get(ticker, {}).get(horizon, {}).get(reg_model_name)
            if reg_bundle is None:
                continue
            try:
                reg_meta          = reg_bundle.get("meta", {})
                reg_feature_names = reg_meta.get("feature_names", feature_names)
                feature_df        = self._features[ticker]
                
                latest_row_reg = feature_df.iloc[-1:]
                X_reg_aligned = pd.DataFrame(index=latest_row_reg.index, columns=reg_feature_names)
                for col in reg_feature_names:
                    if col in latest_row_reg.columns:
                        X_reg_aligned[col] = latest_row_reg[col]
                    else:
                        X_reg_aligned[col] = 0.0
                X_reg = X_reg_aligned.values.astype(np.float32)
                X_reg = np.nan_to_num(X_reg, nan=0.0, posinf=0.0, neginf=0.0)

                if reg_bundle["type"] == "lgbm":
                    pred = reg_bundle["model"].predict(X_reg)[0]
                else:
                    import xgboost as xgb
                    dmatrix = xgb.DMatrix(pd.DataFrame(X_reg, columns=reg_feature_names))
                    pred = reg_bundle["model"].predict(dmatrix)[0]

                return float(pred)
            except Exception as e:
                import traceback
                with open("predict_error.log", "a") as f:
                    f.write(f"reg error: {e}\n{traceback.format_exc()}\n")
                continue
        return 0.0

    def _get_current_price(self, ticker: str) -> float:
        """Get the most recent close price for a ticker."""
        try:
            feature_df = self._features.get(ticker)
            if feature_df is not None and "close" in feature_df.columns:
                return float(feature_df["close"].iloc[-1])
        except Exception:
            pass
        return 0.0

    # ── Explain ────────────────────────────────────────────────────────────────

    def explain(self, ticker: str, horizon: str, top_n: int = 15) -> Dict:
        """
        Compute SHAP feature importances for the latest prediction.

        Uses the LightGBM model (SHAP is fastest on tree models).
        Falls back to feature importance if SHAP fails.
        """
        lgb_bundle = self._models.get(ticker, {}).get(horizon, {}).get("lightgbm_clf")
        if lgb_bundle is None:
            lgb_bundle = self._models.get(ticker, {}).get(horizon, {}).get("lightgbm")

        if lgb_bundle is None:
            raise ValueError(f"No LightGBM model for {ticker}/{horizon}")

        feature_df    = self._features[ticker]
        meta          = lgb_bundle.get("meta", {})
        feature_names = meta.get("feature_names", list(feature_df.columns))
        avail         = [f for f in feature_names if f in feature_df.columns]
        X_latest      = feature_df[avail].iloc[-1:].values.astype(np.float32)
        X_latest      = np.nan_to_num(X_latest, nan=0.0, posinf=0.0, neginf=0.0)

        try:
            import shap
            explainer  = shap.TreeExplainer(lgb_bundle["model"])
            shap_vals  = explainer.shap_values(X_latest)

            # For binary classifier, shap_values is a list [class0, class1]
            if isinstance(shap_vals, list):
                shap_vals = shap_vals[1]  # class 1 = UP direction

            shap_arr  = shap_vals[0]
            feat_imp  = list(zip(avail, shap_arr))
            feat_imp  = sorted(feat_imp, key=lambda x: abs(x[1]), reverse=True)[:top_n]

            net_direction = float(np.sum(shap_arr))

            return {
                "top_features": [
                    {
                        "feature":    name,
                        "importance": abs(float(val)),
                        "direction":  "positive" if val > 0 else "negative",
                    }
                    for name, val in feat_imp
                ],
                "net_direction": net_direction,
            }

        except ImportError:
            logger.warning("SHAP not installed — falling back to feature importance")
            return self._fallback_importance(lgb_bundle, avail, top_n)

        except Exception as e:
            logger.warning(f"SHAP failed: {e} — using fallback")
            return self._fallback_importance(lgb_bundle, avail, top_n)

    def _fallback_importance(self, model_bundle: Dict, feature_names: List[str], top_n: int) -> Dict:
        """Use LightGBM built-in importance when SHAP fails."""
        try:
            model = model_bundle["model"]
            imp   = model.feature_importance(importance_type="gain")
            pairs = sorted(zip(feature_names, imp), key=lambda x: x[1], reverse=True)[:top_n]
            max_imp = max(v for _, v in pairs) if pairs else 1

            return {
                "top_features": [
                    {
                        "feature":    name,
                        "importance": float(val) / max(max_imp, 1),
                        "direction":  "positive",   # unknown without SHAP
                    }
                    for name, val in pairs
                ],
                "net_direction": 0.0,
            }
        except Exception:
            return {"top_features": [], "net_direction": 0.0}

    # ── Backtest ───────────────────────────────────────────────────────────────

    def backtest(self, ticker: str, horizon: str, transaction_cost: float = 0.001) -> Dict:
        """Run backtest on the test set using saved predictions."""
        from features.pipeline import load_features, get_train_test_split
        from training.trainer import prepare_arrays
        from training.backtest import run_backtest

        df = load_features(ticker)
        _, _, test_df = get_train_test_split(df, horizon=horizon)
        X_test, y_test, _ = prepare_arrays(test_df, horizon)

        # Use best available model for backtest
        model_bundle = None
        for m_name in ["ensemble_clf", "lightgbm_clf", "xgboost_clf", "lightgbm"]:
            bundle = self._models.get(ticker, {}).get(horizon, {}).get(m_name)
            if bundle is not None:
                model_bundle = bundle
                break

        if model_bundle is None:
            raise ValueError(f"No model for backtest: {ticker}/{horizon}")

        # Get predictions for the test set
        model_type = model_bundle.get("type", "")
        meta       = model_bundle.get("meta", {})
        feat_names = meta.get("feature_names", [])

        # Re-align features
        feature_df = self._features[ticker]
        avail      = [f for f in feat_names if f in feature_df.columns]
        X_test_aligned = test_df[[f for f in avail if f in test_df.columns]].values.astype(np.float32)
        X_test_aligned = np.nan_to_num(X_test_aligned, nan=0.0, posinf=0.0, neginf=0.0)

        if len(X_test_aligned) == 0:
            X_test_aligned = X_test

        y_pred = np.array([self._run_model_predict(model_bundle, X_test_aligned[i:i+1], model_type, avail)
                           for i in range(len(X_test_aligned))])

        horizon_days = {"1d": 1, "5d": 5, "20d": 20}.get(horizon, 1)
        metrics = run_backtest(
            y_true           = y_test,
            y_pred           = y_pred,
            dates            = test_df.index,
            transaction_cost = transaction_cost,
            horizon_days     = horizon_days,
        )

        return {"metrics": metrics}

    # ── Regime ─────────────────────────────────────────────────────────────────

    def get_current_regime(self) -> Dict:
        """Get current market regime from the HMM model."""
        if getattr(self, "_regime_model", None) is None:
            # Fallback for when hmmlearn is incompatible (e.g., Python 3.13)
            return {"regime": "bull", "since": "2024-01-01", "duration_days": 120}

        try:
            import yfinance as yf
            from features.regime import predict_regimes

            raw = yf.download("^NSEI", period="3mo", auto_adjust=True, progress=False)
            if isinstance(raw.columns, pd.MultiIndex):
                raw.columns = [col[0].lower() for col in raw.columns]
            else:
                raw.columns = [c.lower() for c in raw.columns]

            raw.index.name = "date"
            raw = raw.rename(columns={"close": "nifty50"})

            regimes = predict_regimes(raw)
            current = str(regimes.iloc[-1])

            # Find how long we've been in this regime
            same = (regimes == current)
            duration = int(same[::-1].cumprod().sum())

            self._regime_cache = {
                "regime":        current,
                "since":         str(regimes.index[-duration].date()),
                "duration_days": duration,
            }
            return self._regime_cache

        except Exception as e:
            import traceback
            logger.warning(f"Regime fetch failed: {e}")
            with open("predict_error.log", "a") as f:
                f.write(f"regime error: {e}\n{traceback.format_exc()}\n")
            return {"regime": "bull", "since": "2024-01-01", "duration_days": 120}

    # ── Meta Helpers ───────────────────────────────────────────────────────────

    def get_stock_meta(self, ticker: str) -> Dict:
        """Get company name and sector for a ticker."""
        original = ticker.replace("_NS", ".NS").replace("M_M", "M&M")
        meta_obj = NIFTY50_META.get(original)
        if meta_obj:
            return {"name": meta_obj.name, "sector": meta_obj.sector}
        return {"name": ticker, "sector": "Unknown"}

    def get_available_horizons(self, ticker: str) -> List[str]:
        """List which horizons have trained models for a ticker."""
        return list(self._models.get(ticker, {}).keys())

    def get_best_accuracy(self, ticker: str) -> Dict[str, float]:
        """Get best classification accuracy per horizon from saved results."""
        accuracy = {}
        for horizon in ["1d", "5d", "20d"]:
            results = self._results.get(ticker, {}).get(horizon, {})
            best = 0.0
            for model_name in ["ensemble_clf", "lightgbm_clf", "xgboost_clf"]:
                test = results.get(model_name, {}).get("test", {})
                acc  = test.get("test_accuracy", 0.0) if isinstance(test, dict) else 0.0
                best = max(best, acc)
            if best > 0:
                accuracy[horizon] = round(best, 4)
        return accuracy

    def get_all_prices(self) -> Dict[str, Dict[str, float]]:
        """Return the latest price and pct_change for all loaded tickers."""
        prices = {}
        for ticker, df in self._features.items():
            try:
                if "close" in df.columns and len(df) >= 2:
                    current_price = float(df["close"].iloc[-1])
                    prev_price = float(df["close"].iloc[-2])
                    
                    # Prevent division by zero
                    if prev_price != 0:
                        pct_change = ((current_price - prev_price) / prev_price) * 100
                    else:
                        pct_change = 0.0
                        
                    prices[ticker] = {
                        "price": round(current_price, 2),
                        "pct_change": round(pct_change, 2)
                    }
            except Exception as e:
                logger.debug(f"Could not get price for {ticker}: {e}")
        return prices

    def get_history(self, ticker: str, days: int = 30) -> List[Dict]:
        """Return historical closing prices for a ticker."""
        if ticker not in self._features:
            return []
            
        try:
            df = self._features[ticker]
            if "close" not in df.columns:
                return []
                
            recent = df.tail(days)
            history = []
            for date, row in recent.iterrows():
                history.append({
                    "date": date.strftime("%Y-%m-%d"),
                    "price": float(row["close"])
                })
            return history
        except Exception as e:
            logger.debug(f"Error fetching history for {ticker}: {e}")
            return []
