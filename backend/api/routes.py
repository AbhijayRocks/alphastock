"""
api/routes.py — All API endpoint handlers.

ENDPOINTS:
  POST /api/predict   → run model prediction for a stock + horizon
  POST /api/explain   → get SHAP feature importances
  POST /api/backtest  → run trading simulation
  GET  /api/models    → list all available stocks + models
  GET  /api/regime    → current market regime
  GET  /api/health    → health check

HOW FASTAPI ROUTING WORKS:
  Each function decorated with @router.get() or @router.post() becomes
  an API endpoint. FastAPI automatically:
  - Parses the request body into the Pydantic schema
  - Validates all fields
  - Returns 422 if validation fails
  - Serializes the return value to JSON
  - Documents everything at /docs
"""

import logging
from datetime import datetime
from typing import Dict

import numpy as np
from fastapi import APIRouter, HTTPException

from api.schemas import (
    PredictRequest, PredictResponse, PredictionDetail,
    ExplainRequest, ExplainResponse, FeatureImportance,
    BacktestRequest, BacktestResponse, BacktestMetrics,
    ModelsResponse, ModelInfo, HealthResponse,
    PricesResponse, HistoryResponse,
    PortfolioOptimizeRequest, PortfolioOptimizeResponse,
    SimulateRequest, SimulateResponse, SimulateFan,
    SignalsResponse, SignalItem,
)
from api.model_registry import ModelRegistry
from models.portfolio import (
    optimize_portfolio, estimate_garch_covariance,
    shrink_covariance, hierarchical_risk_parity, black_litterman_returns,
)
import pandas as pd
from config import LOG_LEVEL

logging.basicConfig(level=LOG_LEVEL, format="%(asctime)s | %(levelname)s | %(message)s")
logger = logging.getLogger(__name__)

router = APIRouter()

# Global registry — loaded once at startup in main.py
registry: ModelRegistry = None


def set_registry(reg: ModelRegistry):
    """Called from main.py to inject the loaded registry."""
    global registry
    registry = reg


def _check_registry():
    if registry is None:
        raise HTTPException(status_code=503, detail="Model registry not loaded yet")


# ── Predict ────────────────────────────────────────────────────────────────────

@router.post("/predict", response_model=PredictResponse)
async def predict(request: PredictRequest):
    """
    Get a stock price direction prediction.

    Returns the model's prediction (UP/DOWN), probability, expected return,
    and confidence interval for the requested horizon.
    """
    _check_registry()

    ticker   = request.ticker.upper()
    horizon  = request.horizon
    model_id = request.model

    # Validate ticker
    if ticker not in registry.available_tickers:
        raise HTTPException(
            status_code=404,
            detail=f"No trained model found for {ticker}. "
                   f"Available: {sorted(registry.available_tickers)[:5]}..."
        )

    # Validate horizon
    if horizon not in ["1d", "5d", "20d"]:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid horizon '{horizon}'. Must be one of: 1d, 5d, 20d"
        )

    try:
        result = registry.predict(ticker, horizon, model_id)
    except Exception as e:
        logger.error(f"Prediction failed for {ticker}/{horizon}: {e}")
        raise HTTPException(status_code=500, detail=str(e))

    # Determine signal strength from probability
    prob = result["probability"]
    dist_from_center = abs(prob - 0.5)
    if dist_from_center >= 0.15:
        signal_strength = "strong"
    elif dist_from_center >= 0.08:
        signal_strength = "moderate"
    else:
        signal_strength = "weak"

    # Get meta info
    meta = registry.get_stock_meta(ticker)

    return PredictResponse(
        ticker       = ticker,
        company_name = meta.get("name", ticker),
        sector       = meta.get("sector", "Unknown"),
        horizon      = horizon,
        current_price= result.get("current_price", 0.0),
        prediction   = PredictionDetail(
            direction        = "UP" if prob > 0.5 else "DOWN",
            probability      = round(prob, 4),
            predicted_return = round(result.get("predicted_return", 0.0), 4),
            confidence_lower = round(result.get("confidence_lower", 0.0), 4),
            confidence_upper = round(result.get("confidence_upper", 0.0), 4),
            signal_strength  = signal_strength,
            var_95           = result.get("var_95"),
            cvar_95          = result.get("cvar_95"),
            prob_up          = result.get("prob_up"),
        ),
        regime       = result.get("regime", "unknown"),
        model_used   = model_id,
        last_updated = datetime.now().isoformat(),
    )


# ── Explain ────────────────────────────────────────────────────────────────────

@router.post("/explain", response_model=ExplainResponse)
async def explain(request: ExplainRequest):
    """
    Get SHAP-based feature importance for the latest prediction.

    Returns the top N features that drove the model's prediction,
    with their contribution direction (positive = pushed toward UP).
    """
    _check_registry()

    ticker  = request.ticker.upper()
    horizon = request.horizon
    top_n   = request.top_n

    if ticker not in registry.available_tickers:
        raise HTTPException(status_code=404, detail=f"No model for {ticker}")

    try:
        shap_result = registry.explain(ticker, horizon, top_n)
    except Exception as e:
        logger.error(f"Explain failed for {ticker}/{horizon}: {e}")
        raise HTTPException(status_code=500, detail=str(e))

    features = [
        FeatureImportance(
            feature    = f["feature"],
            importance = round(f["importance"], 6),
            direction  = f["direction"],
        )
        for f in shap_result["top_features"]
    ]

    # Build plain-English interpretation. Now that SHAP gives real signs, cite the
    # drivers that actually push in the net direction (not just the largest by size).
    bias_up   = shap_result.get("net_direction", 0) > 0
    direction = "upward" if bias_up else "downward"
    want      = "positive" if bias_up else "negative"
    drivers   = [f.feature for f in features if f.direction == want][:3] or [f.feature for f in features[:3]]
    interpretation = (
        f"The model leans {direction}, driven mainly by: {', '.join(drivers)}. "
        f"These features pushed the prediction {direction} the hardest."
    )

    return ExplainResponse(
        ticker         = ticker,
        horizon        = horizon,
        top_features   = features,
        interpretation = interpretation,
    )


# ── Backtest ───────────────────────────────────────────────────────────────────

@router.post("/backtest", response_model=BacktestResponse)
async def backtest(request: BacktestRequest):
    """
    Run a simulated trading strategy using model predictions.

    Simulates buying when model predicts UP and going to cash when DOWN.
    Returns performance metrics: Sharpe ratio, max drawdown, annual return etc.
    """
    _check_registry()

    ticker   = request.ticker.upper()
    horizon  = request.horizon
    tc       = request.transaction_cost

    if ticker not in registry.available_tickers:
        raise HTTPException(status_code=404, detail=f"No model for {ticker}")

    try:
        bt_result = registry.backtest(ticker, horizon, tc)
    except Exception as e:
        logger.error(f"Backtest failed for {ticker}/{horizon}: {e}")
        raise HTTPException(status_code=500, detail=str(e))

    metrics = bt_result["metrics"]

    # Plain-English summary
    sharpe    = metrics["sharpe_ratio"]
    ann_ret   = metrics["annual_return"]
    bench_ret = metrics["benchmark_annual_return"]
    hit_rate  = metrics["hit_rate"]

    if sharpe > 1.5:
        quality = "strong"
    elif sharpe > 0.8:
        quality = "decent"
    else:
        quality = "weak"

    outperform = "outperforms" if ann_ret > bench_ret else "underperforms"
    summary = (
        f"The {quality} strategy achieves {ann_ret:.1%} annual return "
        f"with a Sharpe ratio of {sharpe:.2f}. "
        f"It {outperform} the buy-and-hold benchmark ({bench_ret:.1%}) "
        f"with a {hit_rate:.1%} directional accuracy."
    )

    return BacktestResponse(
        ticker  = ticker,
        horizon = horizon,
        metrics = BacktestMetrics(**metrics),
        summary = summary,
    )


# ── Cross-sectional Long/Short Signals ──────────────────────────────────────────

@router.get("/signals", response_model=SignalsResponse)
async def signals(horizon: str = "5d"):
    """
    Market-neutral long/short board from the cross-sectional ranking model
    (rank + meta-labeling). Top quintile = LONG, bottom = SHORT, as of the latest
    data, with rank score and meta confidence per name.
    """
    _check_registry()
    if horizon not in ["1d", "5d", "20d"]:
        raise HTTPException(status_code=400, detail=f"Invalid horizon '{horizon}'")

    try:
        sig = registry.cross_sectional_signals(horizon)
    except Exception as e:
        # Model not trained yet / unavailable → 503 so the frontend can fall back
        logger.warning(f"Signals unavailable for {horizon}: {e}")
        raise HTTPException(status_code=503, detail=f"Cross-sectional signals unavailable: {e}")

    summary = (
        f"Market-neutral board as of {sig['as_of']} ({horizon}): "
        f"long {len(sig['longs'])} / short {len(sig['shorts'])} of {sig['n_universe']} names. "
        f"Ranked by the cross-sectional model and sized by meta-label confidence."
    )
    return SignalsResponse(
        horizon=sig["horizon"], as_of=sig["as_of"], n_universe=sig["n_universe"],
        longs=[SignalItem(**s) for s in sig["longs"]],
        shorts=[SignalItem(**s) for s in sig["shorts"]],
        summary=summary,
    )


# ── Monte Carlo Simulation ──────────────────────────────────────────────────────

@router.post("/simulate", response_model=SimulateResponse)
async def simulate(request: SimulateRequest):
    """
    Monte-Carlo a Merton jump-diffusion forward-price distribution.

    Returns a percentile "fan" of simulated price paths (for the fan chart) plus
    tail-risk metrics (VaR, CVaR, P(up)). The simulation is centered on the ML
    predicted return, uses the GARCH conditional vol for diffusion, and adds
    historically-calibrated jumps for realistic gap/crash risk.
    """
    _check_registry()

    ticker  = request.ticker.upper()
    horizon = request.horizon

    if ticker not in registry.available_tickers:
        raise HTTPException(status_code=404, detail=f"No model for {ticker}")
    if horizon not in ["1d", "5d", "20d"]:
        raise HTTPException(status_code=400, detail=f"Invalid horizon '{horizon}'")

    try:
        sim = registry.simulate(ticker, horizon, n_sims=request.n_sims)
    except Exception as e:
        logger.error(f"Simulation failed for {ticker}/{horizon}: {e}")
        raise HTTPException(status_code=500, detail=str(e))

    m = sim["metrics"]
    summary = (
        f"{sim['n_sims']:,} Monte-Carlo paths (Merton jump-diffusion, "
        f"{sim['n_jumps_history']} historical jumps). Over {horizon}, the 90% "
        f"range is [{m['p05']:+.1%}, {m['p95']:+.1%}] with {m['prob_up']:.0%} "
        f"probability of a gain; 95% VaR {m['var_95']:.1%}, CVaR {m['cvar_95']:.1%}."
    )

    return SimulateResponse(
        ticker           = ticker,
        horizon          = horizon,
        current_price    = sim["current_price"],
        predicted_return = sim["predicted_return"],
        n_sims           = sim["n_sims"],
        n_jumps_history  = sim["n_jumps_history"],
        fan              = SimulateFan(**sim["fan"]),
        metrics          = m,
        summary          = summary,
    )


# ── Models List ────────────────────────────────────────────────────────────────

@router.get("/models", response_model=ModelsResponse)
async def list_models():
    """
    List all stocks with trained models.

    Returns company names, sectors, available horizons,
    and best accuracy per horizon for each stock.
    """
    _check_registry()

    stocks = []
    for ticker in sorted(registry.available_tickers):
        meta     = registry.get_stock_meta(ticker)
        horizons = registry.get_available_horizons(ticker)
        accuracy = registry.get_best_accuracy(ticker)

        stocks.append(ModelInfo(
            ticker              = ticker,
            company_name        = meta.get("name", ticker),
            sector              = meta.get("sector", "Unknown"),
            horizons_available  = horizons,
            best_accuracy       = accuracy,
        ))

    return ModelsResponse(
        total_stocks = len(stocks),
        stocks       = stocks,
    )


# ── Prices and History ─────────────────────────────────────────────────────────

@router.get("/prices", response_model=PricesResponse)
async def get_prices():
    """
    Get current prices and 1-day percentage changes for all loaded stocks.
    """
    _check_registry()
    try:
        prices = registry.get_all_prices()
        return PricesResponse(prices=prices)
    except Exception as e:
        logger.error(f"Failed to fetch prices: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/history/{ticker}", response_model=HistoryResponse)
async def get_history(ticker: str, days: int = 30):
    """
    Get historical closing prices for a specific ticker.
    """
    _check_registry()
    ticker = ticker.upper()

    if ticker not in registry.available_tickers:
        raise HTTPException(status_code=404, detail=f"No data for {ticker}")

    try:
        history = registry.get_history(ticker, days=days)
        return HistoryResponse(ticker=ticker, history=history)
    except Exception as e:
        logger.error(f"Failed to fetch history for {ticker}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ── Portfolio Optimization ─────────────────────────────────────────────────────

@router.post("/optimize_portfolio", response_model=PortfolioOptimizeResponse)
async def optimize_portfolio_route(request: PortfolioOptimizeRequest):
    """
    Optimize portfolio allocation using Markowitz Efficient Frontier.
    Uses AI model predicted returns as expected returns.
    """
    _check_registry()
    
    tickers = [t.upper() for t in request.tickers]
    valid_tickers = [t for t in tickers if t in registry.available_tickers]
    
    if not valid_tickers:
        raise HTTPException(status_code=400, detail="No valid tickers provided with trained models.")
        
    try:
        expected_returns = {}
        histories = {}
        
        # Gather predictions and history for each valid ticker
        for ticker in valid_tickers:
            # Get expected return from model
            pred = registry.predict(ticker, request.horizon)
            expected_returns[ticker] = pred.get("predicted_return", 0.0)

            # Get history for covariance matrix. ~250 trading days gives GARCH(1,1)
            # enough sample to fit (it needs 100+ obs) for a stable covariance.
            hist = registry.get_history(ticker, days=250)
            if hist:
                histories[ticker] = pd.Series(
                    {pt["date"]: pt["price"] for pt in hist}, name=ticker
                )

        if not expected_returns or not histories:
            raise ValueError("Failed to gather predictions or history")

        # Build a date-aligned price frame. Tickers can have different history
        # lengths/dates, so we align on the date index (outer join) instead of
        # assuming equal-length lists (which would raise a ValueError) and avoid
        # mixing returns from mismatched calendar dates.
        price_df = pd.DataFrame(histories).sort_index().ffill().dropna(how="any")
        returns_df = price_df.pct_change().dropna(how="any")

        if returns_df.shape[0] < 2 or returns_df.shape[1] == 0:
            raise ValueError("Not enough overlapping price history to optimize")

        # GARCH conditional covariance, then SHRINK it for stability (Tier 3).
        cov_matrix = estimate_garch_covariance(returns_df)
        cov_matrix = shrink_covariance(cov_matrix, returns_df)

        er_series = pd.Series(expected_returns).reindex(cov_matrix.columns).fillna(0.0)

        # Choose the allocation method (robust default = Black-Litterman)
        method = (request.method or "black_litterman").lower()
        if method == "hrp":
            allocations = hierarchical_risk_parity(cov_matrix)
            method_label = "Hierarchical Risk Parity (diversification-first)"
        elif method == "mvo":
            allocations = optimize_portfolio(er_series, cov_matrix,
                                             risk_tolerance=request.risk_tolerance)
            method_label = "Mean-Variance Optimization"
        else:  # black_litterman
            from data_pipeline.nifty50 import NIFTY50_META
            mkt = {}
            for t in cov_matrix.columns:
                sym = t.replace("_NS", ".NS").replace("M_M", "M&M")
                meta = NIFTY50_META.get(sym)
                mkt[t] = meta.nifty_weight if meta else 1.0
            bl_returns = black_litterman_returns(cov_matrix, mkt, er_series.to_dict(),
                                                 view_confidence=request.risk_tolerance)
            allocations = optimize_portfolio(bl_returns, cov_matrix,
                                             risk_tolerance=request.risk_tolerance)
            method = "black_litterman"
            method_label = "Black-Litterman (model views blended with market equilibrium)"

        top_allocation = max(allocations.items(), key=lambda x: x[1])
        summary = (
            f"Optimized {len(valid_tickers)} assets over a {request.horizon} horizon using "
            f"{method_label}, on a shrunk GARCH covariance with a 40% position cap. "
            f"Largest weighting: {top_allocation[1]:.1%} in {top_allocation[0]}."
        )

        return PortfolioOptimizeResponse(
            horizon=request.horizon,
            risk_tolerance=request.risk_tolerance,
            method=method,
            allocations=allocations,
            summary=summary
        )
    except Exception as e:
        logger.error(f"Portfolio optimization failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ── Regime ─────────────────────────────────────────────────────────────────────

@router.get("/regime")
async def get_regime():
    """
    Get the current market regime.

    Returns the HMM-detected market regime: bull, bear, sideways, or crisis.
    Updated on each prediction call using the latest Nifty index data.
    """
    _check_registry()

    try:
        regime_info = registry.get_current_regime()
        return {
            "regime":      regime_info["regime"],
            "description": _regime_description(regime_info["regime"]),
            "since":       regime_info.get("since", "unknown"),
            "duration_days": regime_info.get("duration_days", 0),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


def _regime_description(regime: str) -> str:
    descriptions = {
        "bull":     "Markets trending upward with low volatility. Momentum strategies work well.",
        "bear":     "Markets trending downward with elevated fear. Capital preservation is key.",
        "sideways": "No clear trend. Range-bound choppy action. Breakout strategies preferred.",
        "crisis":   "Extreme volatility and panic. All correlations spike. High uncertainty.",
    }
    return descriptions.get(regime, "Unknown market state.")


# ── Health ─────────────────────────────────────────────────────────────────────

@router.get("/health", response_model=HealthResponse)
async def health():
    """Health check — confirms API is running and models are loaded."""
    if registry is None:
        return HealthResponse(
            status           = "degraded",
            models_loaded    = 0,
            stocks_available = 0,
        )

    return HealthResponse(
        status           = "healthy",
        models_loaded    = registry.total_models_loaded,
        stocks_available = len(registry.available_tickers),
    )
