"""
api/schemas.py — Pydantic models for all API request/response shapes.

WHY PYDANTIC SCHEMAS?
  FastAPI uses these to:
  1. Validate incoming requests automatically (wrong type = 422 error with clear message)
  2. Serialize outgoing responses to clean JSON
  3. Auto-generate interactive API docs at /docs (Swagger UI)

  Think of schemas as contracts between frontend and backend.
  The React app sends a PredictRequest, gets back a PredictResponse.
  Both sides know exactly what shape the data will be.
"""

from typing import Dict, List, Optional
from pydantic import BaseModel, Field


# ── Request Models ─────────────────────────────────────────────────────────────

class PredictRequest(BaseModel):
    ticker: str = Field(
        ...,
        description="Stock ticker in file format e.g. RELIANCE_NS",
        example="RELIANCE_NS"
    )
    horizon: str = Field(
        default="1d",
        description="Prediction horizon: 1d, 5d, or 20d",
        example="5d"
    )
    model: str = Field(
        default="ensemble_clf",
        description="Model to use: lightgbm_clf, xgboost_clf, ensemble_clf",
        example="ensemble_clf"
    )


class ExplainRequest(BaseModel):
    ticker: str = Field(..., example="RELIANCE_NS")
    horizon: str = Field(default="1d", example="1d")
    top_n: int = Field(
        default=15,
        description="Number of top features to return",
        ge=1, le=50
    )


class BacktestRequest(BaseModel):
    ticker: str = Field(..., example="RELIANCE_NS")
    horizon: str = Field(default="1d", example="1d")
    transaction_cost: float = Field(
        default=0.001,
        description="Transaction cost per trade (0.001 = 0.1%)",
        ge=0.0, le=0.05
    )


# ── Response Models ────────────────────────────────────────────────────────────

class PredictionDetail(BaseModel):
    direction: str              # "UP" or "DOWN"
    probability: float          # confidence 0.0 to 1.0
    predicted_return: float     # expected return e.g. 0.023 = +2.3%
    confidence_lower: float     # lower bound of confidence interval
    confidence_upper: float     # upper bound
    signal_strength: str        # "strong", "moderate", "weak"


class PredictResponse(BaseModel):
    ticker: str
    company_name: str
    sector: str
    horizon: str
    current_price: float
    prediction: PredictionDetail
    regime: str                 # "bull", "bear", "sideways", "crisis"
    model_used: str
    last_updated: str           # ISO timestamp
    disclaimer: str = "For educational purposes only. Not financial advice."


class FeatureImportance(BaseModel):
    feature: str
    importance: float
    direction: str              # "positive" or "negative" impact


class ExplainResponse(BaseModel):
    ticker: str
    horizon: str
    top_features: List[FeatureImportance]
    interpretation: str         # plain-English summary


class BacktestMetrics(BaseModel):
    hit_rate: float
    annual_return: float
    benchmark_annual_return: float
    excess_return: float
    sharpe_ratio: float
    max_drawdown: float
    calmar_ratio: float
    n_trades: int
    equity_curve: List[float]
    buyhold_curve: List[float]
    dates: Optional[List[str]]


class BacktestResponse(BaseModel):
    ticker: str
    horizon: str
    metrics: BacktestMetrics
    summary: str                # plain-English summary


class ModelInfo(BaseModel):
    ticker: str
    company_name: str
    sector: str
    horizons_available: List[str]
    best_accuracy: Dict[str, float]   # {horizon: accuracy}


class ModelsResponse(BaseModel):
    total_stocks: int
    stocks: List[ModelInfo]


class HealthResponse(BaseModel):
    status: str                 # "healthy" or "degraded"
    models_loaded: int
    stocks_available: int
    version: str = "1.0.0"


class ErrorResponse(BaseModel):
    error: str
    detail: str


class PriceInfo(BaseModel):
    price: float
    pct_change: float

class PricesResponse(BaseModel):
    prices: Dict[str, PriceInfo]

class HistoryPoint(BaseModel):
    date: str
    price: float

class HistoryResponse(BaseModel):
    ticker: str
    history: List[HistoryPoint]

class PortfolioOptimizeRequest(BaseModel):
    tickers: List[str] = Field(..., example=["RELIANCE.NS", "TCS.NS", "HDFCBANK.NS"])
    horizon: str = Field(default="20d", example="20d")
    risk_tolerance: float = Field(default=1.0, description="Higher means more risk-seeking", ge=0.1, le=5.0)

class PortfolioOptimizeResponse(BaseModel):
    horizon: str
    risk_tolerance: float
    allocations: Dict[str, float]
    summary: str
