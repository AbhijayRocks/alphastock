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
import time
import threading
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

        # Live price cache — refreshed from yfinance so the dashboard shows
        # today's market data instead of the last-ingested close. Refreshes run
        # in a background thread once the cache is stale, so requests are always
        # served instantly from cache (never blocked on a slow yfinance call).
        self._price_cache: Dict[str, Dict[str, float]] = {}
        self._price_cache_ts: float = 0.0
        self._price_cache_ttl: float = 120.0   # seconds
        self._price_lock = threading.Lock()
        self._price_refreshing: bool = False

        # GARCH 1-day conditional-vol forecast per ticker (return units), cached
        # because fitting GARCH(1,1) costs ~50-200ms. Used for prediction bands.
        self._garch_vol_1d: Dict[str, Optional[float]] = {}

        # Merton jump-diffusion parameters per ticker (calibrated once, cached).
        # Used by the Monte-Carlo risk layer for fat-tailed bands + VaR/CVaR.
        self._merton_params: Dict[str, Optional[Dict]] = {}

        # Cross-sectional long/short signal board cache {horizon: (ts, result)}.
        self._signals_cache: Dict[str, tuple] = {}

        # Market-pulse cache {horizon: (ts, result)} — aggregate model conviction
        # + live breadth for the dashboard hero. Short TTL so it tracks the tape.
        self._pulse_cache: Dict[str, tuple] = {}
        self._pulse_cache_ttl: float = 120.0

        # Fundamentals snapshot (P/E, ROE, market cap, …) keyed by ticker stem.
        # Loaded once from the raw parquet and reused (refreshes on data reload).
        self._fundamentals_cache: Optional[Dict[str, Dict]] = None

        # Screener snapshot {horizon: (ts, rows)} — one rich row per stock (model
        # + technicals + fundamentals + cross-sectional signal). Short TTL.
        self._screen_cache: Dict[str, tuple] = {}
        self._screen_cache_ttl: float = 120.0

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

        # Warm the live-price cache in the background so the first /prices request
        # is served instantly with real market data (works even with 0 models).
        self._refresh_prices_async()

        # Warm the cross-sectional signal board too (panel build ~20s) so the first
        # /signals request doesn't block. Best-effort; ignored if no model trained.
        def _warm_signals():
            for hz in ("5d", "1d", "20d"):
                try:
                    self.cross_sectional_signals(hz)
                except Exception:
                    pass
        threading.Thread(target=_warm_signals, daemon=True).start()

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
        """
        Load a recent tail of features per stock into memory for live prediction.

        Only the most recent `_FEATURE_ROWS` rows are kept resident — enough for
        live predict/explain, GARCH/Merton calibration, and the default history
        window — which keeps the registry inside Render's 512 MB free tier (the
        full panels are ~360 MB). Backtest and the cross-sectional panel read the
        full parquet from disk on demand (features.pipeline.load_features /
        load_all_features), so they are unaffected by this RAM cap. Override the
        window with ALPHASTOCK_FEATURE_ROWS (0 = load full history).
        """
        import os
        pipeline_dir = FEATURES_DIR / "pipeline"
        if not pipeline_dir.exists():
            logger.warning("Pipeline features directory not found")
            return

        rows = int(os.getenv("ALPHASTOCK_FEATURE_ROWS", "750"))

        loaded = 0
        for ticker in self.available_tickers:
            path = pipeline_dir / f"{ticker}.parquet"
            if not path.exists():
                continue
            try:
                df = pd.read_parquet(path, engine="pyarrow")
                df.index = pd.to_datetime(df.index)
                if rows > 0:
                    df = df.tail(rows)
                # Drop target columns — we only want features
                feature_cols = [c for c in df.columns if not c.startswith("target_")]
                self._features[ticker] = df[feature_cols]
                loaded += 1
            except Exception as e:
                logger.warning(f"Feature load failed for {ticker}: {e}")

        logger.info(f"Loaded features for {loaded} stocks (last {rows or 'all'} rows each)")

    def reload_live_data(self) -> int:
        """
        Hot-reload the latest feature panels from disk and drop derived caches,
        so a running server picks up a fresh daily data refresh without a restart.

        Re-reads the per-stock pipeline parquets into memory, then clears the
        regime / signals / GARCH / Merton caches (all derived from the feature
        data) and re-warms the live-price cache. Safe to call from a background
        thread. Returns the number of stocks whose features were reloaded.
        """
        logger.info("Hot-reloading latest features + clearing derived caches...")
        self._load_latest_features()

        # Everything below is derived from the feature/price data — invalidate so
        # the next request recomputes against the freshly loaded panels.
        self._regime_cache = {}
        self._signals_cache = {}
        self._pulse_cache = {}
        self._fundamentals_cache = None
        self._screen_cache = {}
        self._garch_vol_1d = {}
        self._merton_params = {}

        # Re-warm live prices immediately (blocking is fine off the request path).
        try:
            self._refresh_prices()
        except Exception as e:  # noqa: BLE001
            logger.warning(f"Price re-warm after reload failed: {e}")

        n = len(self._features)
        logger.info(f"Hot-reload complete: {n} stocks refreshed.")
        return n

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

    # ── Feature Alignment & Ensemble Evaluation ─────────────────────────────────

    def _align_features(self, rows: pd.DataFrame, feature_names: List[str]) -> np.ndarray:
        """
        Align one or more feature rows to exactly the columns a model expects.
        Missing columns are filled with 0.0; NaN/inf are scrubbed.
        Works for a single latest row or a full batch (e.g. a backtest test set).
        """
        aligned = pd.DataFrame(index=rows.index, columns=feature_names)
        for col in feature_names:
            if col in rows.columns:
                aligned[col] = rows[col]
            else:
                aligned[col] = 0.0
        X = aligned.values.astype(np.float32)
        return np.nan_to_num(X, nan=0.0, posinf=0.0, neginf=0.0)

    def _predict_member_proba(
        self, ticker: str, horizon: str, model_name: str, rows: pd.DataFrame
    ) -> Optional[np.ndarray]:
        """
        Batch UP-probabilities for a single classifier member, aligned to that
        member's own trained feature set. Returns an array (len == len(rows)) or None.
        """
        bundle = self._models.get(ticker, {}).get(horizon, {}).get(model_name)
        if bundle is None:
            return None

        mtype  = bundle.get("type", "")
        meta   = bundle.get("meta", {})
        fnames = meta.get("feature_names", list(rows.columns))
        X      = self._align_features(rows, fnames)

        try:
            if mtype == "lgbm_clf":
                return np.asarray(bundle["model"].predict(X), dtype=float)
            elif mtype == "xgb_clf":
                import xgboost as xgb
                dmatrix = xgb.DMatrix(pd.DataFrame(X, columns=fnames))
                return np.asarray(bundle["model"].predict(dmatrix), dtype=float)
        except Exception as e:
            logger.warning(f"Member predict failed ({model_name}): {e}")
        return None

    def _predict_ensemble_proba(
        self, ticker: str, horizon: str, rows: pd.DataFrame
    ) -> Optional[np.ndarray]:
        """
        Actually evaluate the classification ensemble: run each member model,
        then combine with the saved weights (or the stacking meta-learner).
        Returns an array of UP-probabilities (len == len(rows)) or None.
        """
        bundle = self._models.get(ticker, {}).get(horizon, {}).get("ensemble_clf")
        if bundle is None:
            return None

        data       = bundle.get("ensemble_data", {})
        members    = data.get("model_names", []) or []
        weights    = data.get("weights", {}) or {}
        strategy   = data.get("strategy", "weighted")
        meta_model = data.get("meta_model")

        # Collect each member's predictions on these rows
        preds = {}
        for m in members:
            p = self._predict_member_proba(ticker, horizon, m, rows)
            if p is not None:
                preds[m] = p

        if not preds:
            return None

        # Stacking: feed member probabilities into the fitted meta-learner
        if strategy == "stacking" and meta_model is not None:
            try:
                X_stack = np.column_stack([preds[m] for m in members if m in preds])
                return meta_model.predict_proba(X_stack)[:, 1]
            except Exception as e:
                logger.warning(f"Stacking meta-model failed, averaging instead: {e}")

        # Weighted (or simple) average, normalized over the members that ran
        out   = np.zeros(len(next(iter(preds.values()))), dtype=float)
        total = 0.0
        for m, p in preds.items():
            w = weights.get(m, 1.0 / len(preds))
            out   += w * p
            total += w
        if total > 0:
            out /= total
        return out

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

        # Predict UP-probability for the latest row
        latest_row = feature_df.iloc[-1:]

        if model_bundle.get("type") == "ensemble":
            # Actually evaluate the ensemble (run members + combine), not a 0.5 stub
            ens = self._predict_ensemble_proba(ticker, horizon, latest_row)
            prob = float(ens[-1]) if ens is not None else 0.5
        else:
            meta          = model_bundle.get("meta", {})
            feature_names = meta.get("feature_names", list(feature_df.columns))
            X_latest      = self._align_features(latest_row, feature_names)
            prob          = self._run_model_predict(model_bundle, X_latest, model_name, feature_names)

        # Get current price
        current_price = self._get_current_price(ticker)

        # Expected return from regression model (if available)
        predicted_return = self._get_regression_prediction(ticker, horizon)

        # Confidence band + tail risk. Preferred: Monte-Carlo Merton jump-diffusion
        # (fat-tailed, asymmetric, with VaR/CVaR). Fallbacks: GARCH normal band,
        # then a crude heuristic.
        mc = self._montecarlo_risk(ticker, horizon, predicted_return)
        var_95 = cvar_95 = prob_up = None
        if mc is not None:
            lower, upper = mc["p05"], mc["p95"]
            var_95, cvar_95, prob_up = mc["var_95"], mc["cvar_95"], mc["prob_up"]
        else:
            sigma_h = self._garch_band(ticker, horizon)
            margin = 1.645 * sigma_h if sigma_h is not None else abs(predicted_return) * 0.3 + 0.005
            lower  = predicted_return - margin
            upper  = predicted_return + margin

        # Regime
        regime = self._regime_cache.get("regime", "unknown")

        return {
            "probability":       float(prob),
            "predicted_return":  float(predicted_return),
            "confidence_lower":  float(lower),
            "confidence_upper":  float(upper),
            "var_95":            var_95,
            "cvar_95":           cvar_95,
            "prob_up":           prob_up,
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

    def _get_regression_prediction(self, ticker: str, horizon: str) -> float:
        """Get regression model prediction for expected return."""
        feature_df = self._features[ticker]
        for reg_model_name in ["lightgbm", "xgboost"]:
            reg_bundle = self._models.get(ticker, {}).get(horizon, {}).get(reg_model_name)
            if reg_bundle is None:
                continue
            try:
                reg_meta          = reg_bundle.get("meta", {})
                reg_feature_names = reg_meta.get("feature_names", list(feature_df.columns))

                X_reg = self._align_features(feature_df.iloc[-1:], reg_feature_names)

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
        """Get the latest market price for a ticker (live, with stored fallback)."""
        live = self._fetch_live_prices()
        if ticker in live:
            return float(live[ticker]["price"])
        # Fallback: last close from the stored feature parquet
        try:
            feature_df = self._features.get(ticker)
            if feature_df is not None and "close" in feature_df.columns:
                return float(feature_df["close"].iloc[-1])
        except Exception:
            pass
        return 0.0

    def _garch_band(self, ticker: str, horizon: str) -> Optional[float]:
        """
        GARCH(1,1) volatility forecast (return units) over the horizon, used for
        prediction intervals. The 1-day forecast is fit once per ticker and
        cached; horizon scaling is sqrt-of-time. Returns None if unavailable.
        """
        if ticker not in self._garch_vol_1d:
            sigma_1d = None
            try:
                feature_df = self._features.get(ticker)
                if feature_df is not None and "close" in feature_df.columns:
                    from features.garch import forecast_vol
                    log_ret = np.log(feature_df["close"] / feature_df["close"].shift(1))
                    sigma_1d = forecast_vol(log_ret, horizon_days=1)
            except Exception as e:
                logger.debug(f"GARCH band failed for {ticker}: {e}")
            self._garch_vol_1d[ticker] = sigma_1d

        sigma_1d = self._garch_vol_1d[ticker]
        if sigma_1d is None:
            return None
        horizon_days = {"1d": 1, "5d": 5, "20d": 20}.get(horizon, 1)
        return float(sigma_1d) * np.sqrt(horizon_days)

    # ── Monte Carlo (Merton jump-diffusion) risk layer ──────────────────────────

    def _merton_calibrate(self, ticker: str) -> Optional[Dict]:
        """Calibrate (and cache) Merton jump-diffusion params from price history."""
        if ticker not in self._merton_params:
            params = None
            try:
                feature_df = self._features.get(ticker)
                if feature_df is not None and "close" in feature_df.columns:
                    from models.montecarlo import calibrate_merton
                    log_ret = np.log(feature_df["close"] / feature_df["close"].shift(1)).dropna()
                    params = calibrate_merton(log_ret.values)
            except Exception as e:
                logger.debug(f"Merton calibration failed for {ticker}: {e}")
            self._merton_params[ticker] = params
        return self._merton_params[ticker]

    def _montecarlo_risk(self, ticker: str, horizon: str, predicted_return: float) -> Optional[Dict]:
        """
        Monte-Carlo a Merton jump-diffusion forward-return distribution centered on
        the ML prediction, using the GARCH vol for diffusion. Returns risk metrics
        (fat-tailed band p05/p95, VaR/CVaR, P(up)) or None.
        """
        params = self._merton_calibrate(ticker)
        if params is None:
            return None
        try:
            from models.montecarlo import simulate_terminal_returns, risk_metrics
            horizon_days = {"1d": 1, "5d": 5, "20d": 20}.get(horizon, 1)
            sigma_1d = self._garch_band(ticker, "1d")    # daily GARCH vol for diffusion
            rets = simulate_terminal_returns(
                predicted_return, horizon_days, params,
                diffusion_sigma_daily=sigma_1d, n_sims=10_000,
            )
            return risk_metrics(rets)
        except Exception as e:
            logger.debug(f"Monte Carlo risk failed for {ticker}: {e}")
            return None

    def simulate(self, ticker: str, horizon: str, n_sims: int = 2_000) -> Dict:
        """
        Build a Monte-Carlo price fan (percentile cone) for the analysis chart,
        plus the terminal risk metrics. Uses live price as the starting point.
        """
        params = self._merton_calibrate(ticker)
        if params is None:
            raise ValueError(f"Cannot calibrate Monte Carlo model for {ticker}")

        from models.montecarlo import simulate_price_fan, simulate_terminal_returns, risk_metrics

        horizon_days     = {"1d": 1, "5d": 5, "20d": 20}.get(horizon, 1)
        current_price    = self._get_current_price(ticker)
        predicted_return = self._get_regression_prediction(ticker, horizon)
        sigma_1d         = self._garch_band(ticker, "1d")

        fan = simulate_price_fan(
            current_price, predicted_return, horizon_days, params,
            diffusion_sigma_daily=sigma_1d, n_sims=n_sims,
        )
        rets    = simulate_terminal_returns(predicted_return, horizon_days, params,
                                            diffusion_sigma_daily=sigma_1d, n_sims=10_000)
        metrics = risk_metrics(rets)

        return {
            "ticker":           ticker,
            "horizon":          horizon,
            "current_price":    float(current_price),
            "predicted_return": float(predicted_return),
            "n_sims":           n_sims,
            "n_jumps_history":  int(params.get("n_jumps", 0)),
            "fan":              fan,
            "metrics":          metrics,
        }

    # ── Live Prices ──────────────────────────────────────────────────────────────

    @staticmethod
    def _to_yf_symbol(ticker: str) -> str:
        """Convert a file-stem ticker (e.g. RELIANCE_NS) to a yfinance symbol."""
        return ticker.replace("_NS", ".NS").replace("M_M", "M&M")

    @staticmethod
    def _to_stem(symbol: str) -> str:
        """Convert a yfinance symbol (e.g. M&M.NS) to a file-stem ticker (M_M_NS)."""
        return symbol.replace(".", "_").replace("&", "_").replace("^", "")

    def _price_universe(self) -> Dict[str, str]:
        """
        {yfinance_symbol: file_stem} for the prices we serve. Prefer the trained
        tickers; if none are trained yet, fall back to the full Nifty-50 universe
        so the dashboard still shows real live prices (not demo data).
        """
        if self.available_tickers:
            stems = sorted(self.available_tickers)
        else:
            from data_pipeline.nifty50 import get_all_tickers
            stems = [self._to_stem(sym) for sym in get_all_tickers()]
        return {self._to_yf_symbol(stem): stem for stem in stems}

    def _fetch_live_prices(self) -> Dict[str, Dict[str, float]]:
        """
        Return cached live prices, refreshing in the background when stale.

        - Fresh cache  → return immediately.
        - Stale cache  → kick off a background refresh, return the stale cache now
                         (so the request never waits on a slow yfinance call).
        - Empty cache  → do a one-time blocking fetch (startup / first request).
        """
        now = time.time()
        if self._price_cache and (now - self._price_cache_ts) < self._price_cache_ttl:
            return self._price_cache

        if self._price_cache:
            self._refresh_prices_async()
            return self._price_cache

        # Cold cache — block once so the first caller gets real data
        self._refresh_prices()
        return self._price_cache

    def _refresh_prices_async(self) -> None:
        """Start a background price refresh unless one is already running."""
        with self._price_lock:
            if self._price_refreshing:
                return
            self._price_refreshing = True
        threading.Thread(target=self._refresh_prices, daemon=True).start()

    def _refresh_prices(self) -> None:
        """Download fresh prices and update the cache (safe to call from a thread)."""
        try:
            prices = self._download_live_prices()
            if prices:
                self._price_cache = prices
                self._price_cache_ts = time.time()
        finally:
            self._price_refreshing = False

    def _download_live_prices(self) -> Dict[str, Dict[str, float]]:
        """Batch-download latest price + 1-day % change from yfinance. Never raises."""
        symbol_map = self._price_universe()
        if not symbol_map:
            return {}

        try:
            import yfinance as yf
            raw = yf.download(
                tickers=list(symbol_map.keys()),
                period="5d",
                interval="1d",
                auto_adjust=True,
                progress=False,
                group_by="ticker",
                threads=True,
            )
        except Exception as e:
            logger.warning(f"Live price fetch failed: {e} — using stored close")
            return {}

        prices: Dict[str, Dict[str, float]] = {}
        single = len(symbol_map) == 1
        for sym, stem in symbol_map.items():
            try:
                sub = raw if single else raw[sym]
                if "Close" in sub.columns:
                    closes = sub["Close"].dropna()
                else:
                    closes = sub.iloc[:, 0].dropna()
                if len(closes) == 0:
                    continue
                current = float(closes.iloc[-1])
                prev = float(closes.iloc[-2]) if len(closes) >= 2 else current
                pct = ((current - prev) / prev * 100) if prev else 0.0
                prices[stem] = {"price": round(current, 2), "pct_change": round(pct, 2)}
            except Exception:
                continue
        return prices

    # ── Explain ────────────────────────────────────────────────────────────────

    def explain(self, ticker: str, horizon: str, top_n: int = 15) -> Dict:
        """
        Real SHAP feature attributions for the latest prediction.

        Uses the tree model's NATIVE TreeSHAP — LightGBM `pred_contrib=True` and
        XGBoost `pred_contribs=True` — which return exact per-feature SHAP
        contributions *with sign*, without the heavy `shap`/`numba` stack (so it
        works on Python 3.14). A positive contribution pushes the prediction
        toward UP, negative toward DOWN. Falls back to gain importance only if the
        native computation fails.
        """
        # Prefer the classifier (direction is what users care about), else regressor
        bundle = (self._models.get(ticker, {}).get(horizon, {}).get("lightgbm_clf")
                  or self._models.get(ticker, {}).get(horizon, {}).get("lightgbm")
                  or self._models.get(ticker, {}).get(horizon, {}).get("xgboost_clf")
                  or self._models.get(ticker, {}).get(horizon, {}).get("xgboost"))
        if bundle is None:
            raise ValueError(f"No tree model for {ticker}/{horizon}")

        feature_df    = self._features[ticker]
        meta          = bundle.get("meta", {})
        feature_names = meta.get("feature_names", list(feature_df.columns))
        X_latest      = self._align_features(feature_df.iloc[-1:], feature_names)
        mtype         = bundle.get("type", "")

        try:
            model = bundle["model"]
            if mtype.startswith("lgbm"):
                # LightGBM TreeSHAP → shape (n, n_features + 1); last col = base value
                contribs = np.asarray(model.predict(X_latest, pred_contrib=True))
            else:
                import xgboost as xgb
                dmatrix  = xgb.DMatrix(pd.DataFrame(X_latest, columns=feature_names))
                contribs = np.asarray(model.predict(dmatrix, pred_contribs=True))

            shap_arr = contribs[0, :len(feature_names)]     # drop base/bias column

            feat_imp = sorted(zip(feature_names, shap_arr),
                              key=lambda x: abs(x[1]), reverse=True)[:top_n]
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

        except Exception as e:
            logger.warning(f"Native SHAP failed: {e} — using gain-importance fallback")
            return self._fallback_importance(bundle, feature_names, top_n)

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
        _, y_test, _ = prepare_arrays(test_df, horizon)

        # Use best available model for backtest
        model_bundle = None
        model_name   = None
        for m_name in ["ensemble_clf", "lightgbm_clf", "xgboost_clf", "lightgbm"]:
            bundle = self._models.get(ticker, {}).get(horizon, {}).get(m_name)
            if bundle is not None:
                model_bundle = bundle
                model_name   = m_name
                break

        if model_bundle is None:
            raise ValueError(f"No model for backtest: {ticker}/{horizon}")

        # Predict over the test rows, each model aligned to its own feature set.
        # IMPORTANT: classifier output is a probability (0..1). The backtest
        # strategy treats `y_pred > 0` as a long signal, so classifier
        # probabilities must be centered (prob - 0.5) → >0 means "model says UP".
        # Regression models already output signed returns and are used as-is.
        model_type = model_bundle.get("type", "")

        if model_name == "ensemble_clf":
            proba = self._predict_ensemble_proba(ticker, horizon, test_df)
            if proba is None:  # fall back to a member classifier
                proba = self._predict_member_proba(ticker, horizon, "lightgbm_clf", test_df)
            if proba is None:
                raise ValueError(f"Ensemble backtest produced no predictions: {ticker}/{horizon}")
            y_pred = proba - 0.5
        elif model_name in ("lightgbm_clf", "xgboost_clf"):
            proba = self._predict_member_proba(ticker, horizon, model_name, test_df)
            if proba is None:
                raise ValueError(f"Classifier backtest produced no predictions: {ticker}/{horizon}")
            y_pred = proba - 0.5
        else:
            # Regression model — signed expected returns
            meta       = model_bundle.get("meta", {})
            feat_names = meta.get("feature_names", list(self._features[ticker].columns))
            X_test_aligned = self._align_features(test_df, feat_names)
            if model_type == "lgbm":
                y_pred = np.asarray(model_bundle["model"].predict(X_test_aligned), dtype=float)
            else:
                import xgboost as xgb
                dmatrix = xgb.DMatrix(pd.DataFrame(X_test_aligned, columns=feat_names))
                y_pred = np.asarray(model_bundle["model"].predict(dmatrix), dtype=float)

        # GARCH forward-vol per test row enables volatility-targeted sizing
        vol = test_df["garch_vol"].values if "garch_vol" in test_df.columns else None

        horizon_days = {"1d": 1, "5d": 5, "20d": 20}.get(horizon, 1)
        metrics = run_backtest(
            y_true           = y_test,
            y_pred           = y_pred,
            dates            = test_df.index,
            transaction_cost = transaction_cost,
            horizon_days     = horizon_days,
            volatility       = vol,
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

    # ── Cross-sectional long/short signals ──────────────────────────────────────

    def cross_sectional_signals(self, horizon: str = "5d") -> Dict:
        """
        Live market-neutral long/short board from the cross-sectional model
        (rank + meta-labeling). Cached for an hour; enriched with name/sector/price.
        """
        cached = self._signals_cache.get(horizon)
        if cached and (time.time() - cached[0]) < 3600:
            return cached[1]

        from training.cross_sectional import generate_signals, load_production
        prod = load_production(horizon)
        if prod is None:
            raise ValueError(f"No cross-sectional model trained for {horizon}")

        sig = generate_signals(horizon, prod=prod)

        live = self._fetch_live_prices()
        for s in sig["longs"] + sig["shorts"]:
            meta = self.get_stock_meta(s["ticker"])
            s["company_name"] = meta.get("name")
            s["sector"] = meta.get("sector")
            px = live.get(s["ticker"])
            s["price"] = float(px["price"]) if px else self._get_current_price(s["ticker"])

        self._signals_cache[horizon] = (time.time(), sig)
        return sig

    # ── Market pulse (dashboard hero) ────────────────────────────────────────────

    def _direction_proba(self, ticker: str, horizon: str) -> Optional[float]:
        """
        Cheap UP-probability for the latest bar — classifier only, no Monte-Carlo
        / GARCH. Used to aggregate conviction across the universe.
        """
        models = self._models.get(ticker, {}).get(horizon, {})
        if not models or ticker not in self._features:
            return None
        latest = self._features[ticker].iloc[-1:]
        try:
            if "ensemble_clf" in models:
                ens = self._predict_ensemble_proba(ticker, horizon, latest)
                if ens is not None:
                    return float(ens[-1])
            for name in ("lightgbm_clf", "xgboost_clf"):
                bundle = models.get(name)
                if bundle is None:
                    continue
                feat_names = bundle.get("meta", {}).get("feature_names", list(latest.columns))
                X = self._align_features(latest, feat_names)
                return float(self._run_model_predict(bundle, X, name, feat_names))
        except Exception as e:  # noqa: BLE001
            logger.debug(f"pulse proba failed for {ticker}/{horizon}: {e}")
        return None

    _CONVICTION_LABELS = (
        (56, "Bullish"), (53, "Mildly Bullish"), (48, "Neutral"),
        (45, "Cautious"), (0, "Bearish"),
    )
    _REGIME_STANCE = {
        "bull": "Risk-On", "bear": "Risk-Off", "sideways": "Neutral",
        "crisis": "Defensive", "unknown": "—",
    }

    def market_pulse(self, horizon: str = "5d") -> Dict:
        """
        Dashboard hero payload — one fast call that fuses:
          • aggregate model conviction across the whole NIFTY-50 (0-100 index =
            mean classifier P(up) at `horizon`, plus how many names tilt up),
          • live market breadth (advancers/decliners) from cached quotes,
          • leading / lagging sector by today's average move,
          • current market regime + the desk stance it implies.

        Classifier-only (no Monte-Carlo), cached ~120s, so it's cheap enough to
        sit on the landing page. Never raises.
        """
        cached = self._pulse_cache.get(horizon)
        if cached and (time.time() - cached[0]) < self._pulse_cache_ttl:
            return cached[1]

        # ── Live breadth + sector aggregation ────────────────────────────────
        prices = self.get_all_prices()
        adv = dec = unch = 0
        sector_moves: Dict[str, List[float]] = {}
        for ticker, px in prices.items():
            chg = float(px.get("pct_change", 0.0) or 0.0)
            if chg > 0:
                adv += 1
            elif chg < 0:
                dec += 1
            else:
                unch += 1
            sector = self.get_stock_meta(ticker).get("sector") or "Other"
            sector_moves.setdefault(sector, []).append(chg)

        total_moving = adv + dec
        pct_advancing = round(100 * adv / total_moving, 1) if total_moving else 0.0

        sector_avg = {s: sum(v) / len(v) for s, v in sector_moves.items() if v}
        leading = lagging = None
        if sector_avg:
            lead_name = max(sector_avg, key=sector_avg.get)
            lag_name  = min(sector_avg, key=sector_avg.get)
            leading = {"sector": lead_name, "avg_change": round(sector_avg[lead_name], 2)}
            lagging = {"sector": lag_name,  "avg_change": round(sector_avg[lag_name], 2)}

        # ── Aggregate model conviction ───────────────────────────────────────
        probs = [p for p in (self._direction_proba(t, horizon) for t in self.available_tickers)
                 if p is not None]
        if probs:
            avg_prob   = sum(probs) / len(probs)
            tilted_up  = sum(1 for p in probs if p > 0.5)
            conviction = round(avg_prob * 100)
        else:
            avg_prob, tilted_up, conviction = 0.5, 0, 50

        label = next(lbl for thr, lbl in self._CONVICTION_LABELS if conviction >= thr)

        # ── Regime context ───────────────────────────────────────────────────
        regime_info = self.get_current_regime()
        regime = regime_info.get("regime", "unknown")
        stance = self._REGIME_STANCE.get(regime, "—")

        result = {
            "horizon": horizon,
            "conviction": int(conviction),
            "conviction_label": label,
            "avg_prob_up": round(avg_prob, 4),
            "tilted_up": int(tilted_up),
            "universe": len(probs),
            "breadth": {
                "advancers": adv,
                "decliners": dec,
                "unchanged": unch,
                "pct_advancing": pct_advancing,
            },
            "leading_sector": leading,
            "lagging_sector": lagging,
            "regime": regime,
            "stance": stance,
        }
        self._pulse_cache[horizon] = (time.time(), result)
        return result

    # ── Fundamentals (screener) ──────────────────────────────────────────────────

    def get_fundamentals(self) -> Dict[str, Dict]:
        """
        Per-stock fundamentals for the screener, keyed by ticker stem (e.g.
        "RELIANCE_NS"), normalized to clean display units so the frontend just
        renders:
          market_cap_cr (₹ crore) · pe · forward_pe · pb · roe % · roa % ·
          de (ratio) · revenue_growth % · earnings_growth % · dividend_yield % ·
          beta

        Source is the raw fundamentals snapshot (yfinance), which mixes units —
        ROE/ROA/growth are fractions, dividend yield & debt/equity are percents,
        market cap is absolute INR — so we convert here, once, and cache.
        """
        if self._fundamentals_cache is not None:
            return self._fundamentals_cache

        import math
        from config import FEATURES_DIR

        out: Dict[str, Dict] = {}
        try:
            path = FEATURES_DIR / "raw" / "fundamentals.parquet"
            if not path.exists():
                self._fundamentals_cache = {}
                return out

            df = pd.read_parquet(path)

            def num(value, scale=1.0, nd=2):
                try:
                    f = float(value) * scale
                except (TypeError, ValueError):
                    return None
                if math.isnan(f) or math.isinf(f):
                    return None
                return round(f, nd)

            for ticker, row in df.iterrows():
                stem = str(ticker).replace(".NS", "_NS").replace("&", "_").replace("-", "_")
                out[stem] = {
                    "market_cap_cr":   num(row.get("market_cap"), 1 / 1e7, 0),  # INR → ₹ crore
                    "pe":              num(row.get("pe_ratio")),
                    "forward_pe":      num(row.get("forward_pe")),
                    "pb":              num(row.get("pb_ratio")),
                    "roe":             num(row.get("roe"), 100),               # fraction → %
                    "roa":             num(row.get("roa"), 100),
                    "de":              num(row.get("debt_to_equity"), 1 / 100),  # % → ratio
                    "revenue_growth":  num(row.get("revenue_growth"), 100),
                    "earnings_growth": num(row.get("earnings_growth"), 100),
                    "dividend_yield":  num(row.get("dividend_yield")),          # already %
                    "beta":            num(row.get("beta")),
                }
            self._fundamentals_cache = out
        except Exception as e:  # noqa: BLE001
            logger.warning(f"fundamentals load failed: {e}")
            self._fundamentals_cache = {}
        return self._fundamentals_cache

    # ── Screener (one rich row per stock) ────────────────────────────────────────

    # Screener technical fields → source feature column (from the latest bar).
    _SCREEN_TECH_FIELDS = {
        "rsi_14":        "rsi_14",
        "macd_hist":     "macd_hist",
        "vs_sma_50":     "price_vs_sma_50",     # (close-SMA50)/SMA50; >0 = above
        "vs_sma_200":    "price_vs_sma_200",
        "from_52w_high": "pct_from_52w_high",    # <0 = below the high
        "from_52w_low":  "pct_from_52w_low",
        "ret_5d":        "return_5d",
        "ret_20d":       "return_20d",
        "ret_60d":       "return_60d",
        "rvol":          "rvol_20d",             # volume vs 20d average
        "garch_vol":     "garch_vol",            # conditional daily vol
    }

    def screen(self, horizon: str = "5d") -> List[Dict]:
        """
        One rich row per stock for the screener — model direction/probability,
        expected return, key technicals (from the latest feature bar),
        fundamentals, and the cross-sectional long/short side. Classifier-only
        (no Monte-Carlo), cached ~120s, so the whole board is one fast call
        instead of 50 /predict round-trips.
        """
        cached = self._screen_cache.get(horizon)
        if cached and (time.time() - cached[0]) < self._screen_cache_ttl:
            return cached[1]

        import math

        def clean(value, nd=4):
            try:
                f = float(value)
            except (TypeError, ValueError):
                return None
            if math.isnan(f) or math.isinf(f):
                return None
            return round(f, nd)

        prices = self.get_all_prices()
        funds  = self.get_fundamentals()
        regime = self.get_current_regime().get("regime", "unknown")

        # Cross-sectional long/short side per ticker (best-effort; may be absent).
        sig_map: Dict[str, Dict] = {}
        try:
            sig = self.cross_sectional_signals(horizon)
            for s in sig.get("longs", []):
                sig_map[s["ticker"]] = {"side": "LONG", "rank": s.get("rank"), "confidence": s.get("confidence")}
            for s in sig.get("shorts", []):
                sig_map[s["ticker"]] = {"side": "SHORT", "rank": s.get("rank"), "confidence": s.get("confidence")}
        except Exception as e:  # noqa: BLE001
            logger.debug(f"screen: signals unavailable for {horizon}: {e}")

        rows: List[Dict] = []
        for ticker in sorted(self.available_tickers):
            feat = self._features.get(ticker)
            if feat is None or len(feat) == 0:
                continue
            last = feat.iloc[-1]

            prob = self._direction_proba(ticker, horizon)
            if prob is None:
                prob = 0.5
            pred_ret = self._get_regression_prediction(ticker, horizon)
            dist = abs(prob - 0.5)
            strength = "strong" if dist >= 0.15 else "moderate" if dist >= 0.08 else "weak"

            px = prices.get(ticker, {})
            price = px.get("price")
            if price is None:
                price = self._get_current_price(ticker)
            meta = self.get_stock_meta(ticker)

            rows.append({
                "ticker":           ticker,
                "company_name":     meta.get("name"),
                "sector":           meta.get("sector"),
                "current_price":    clean(price, 2),
                "pct_change":       clean(px.get("pct_change"), 2),
                "direction":        "UP" if prob > 0.5 else "DOWN",
                "probability":      round(float(prob), 4),
                "predicted_return": clean(pred_ret),
                "signal_strength":  strength,
                "technicals":       {k: clean(last.get(src)) for k, src in self._SCREEN_TECH_FIELDS.items()},
                "fundamentals":     funds.get(ticker),
                "signal":           sig_map.get(ticker),
                "regime":           regime,
            })

        self._screen_cache[horizon] = (time.time(), rows)
        return rows

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
        """
        Return the latest market price and 1-day pct_change for all loaded
        tickers. Uses live yfinance quotes (cached), falling back to the stored
        feature close for any ticker the live fetch couldn't cover.
        """
        live = self._fetch_live_prices()
        prices = dict(live)  # start from live quotes

        # Fill any gaps (tickers missing from the live fetch) with stored close
        for ticker, df in self._features.items():
            if ticker in prices:
                continue
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
