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
    confidence_lower: float     # lower bound (Monte-Carlo 5th percentile)
    confidence_upper: float     # upper bound (Monte-Carlo 95th percentile)
    signal_strength: str        # "strong", "moderate", "weak"
    # Monte-Carlo (Merton jump-diffusion) tail risk — null if unavailable
    var_95: Optional[float] = None     # 95% Value-at-Risk (loss magnitude)
    cvar_95: Optional[float] = None    # 95% Conditional VaR / expected shortfall
    prob_up: Optional[float] = None    # simulated probability of a positive return


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
    avg_exposure: Optional[float] = None   # mean position size under vol targeting
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
    method: str = Field(
        default="black_litterman",
        description="black_litterman (blend views+equilibrium) | hrp (risk parity) | mvo (plain Markowitz)",
        example="black_litterman",
    )

class PortfolioOptimizeResponse(BaseModel):
    horizon: str
    risk_tolerance: float
    method: str = "black_litterman"
    allocations: Dict[str, float]
    summary: str


class SimulateRequest(BaseModel):
    ticker: str = Field(..., example="RELIANCE_NS")
    horizon: str = Field(default="20d", example="20d")
    n_sims: int = Field(default=2000, ge=200, le=20000)


class SimulateFan(BaseModel):
    steps: List[int]
    p05: List[float]
    p25: List[float]
    p50: List[float]
    p75: List[float]
    p95: List[float]


class SimulateResponse(BaseModel):
    ticker: str
    horizon: str
    current_price: float
    predicted_return: float
    n_sims: int
    n_jumps_history: int          # how many historical jumps calibrated the model
    fan: SimulateFan              # Monte-Carlo price percentile cone
    metrics: Dict[str, float]     # p05/p95/var_95/cvar_95/prob_up/...
    summary: str


class SignalItem(BaseModel):
    ticker: str
    rank: int
    side: str                     # "LONG" or "SHORT"
    score: float                  # cross-sectional rank score
    confidence: float             # meta-label confidence (0..1)
    company_name: Optional[str] = None
    sector: Optional[str] = None
    price: Optional[float] = None


class SignalsResponse(BaseModel):
    horizon: str
    as_of: str                    # date the board was computed for
    n_universe: int
    longs: List[SignalItem]
    shorts: List[SignalItem]
    summary: str


class BreadthInfo(BaseModel):
    advancers: int
    decliners: int
    unchanged: int
    pct_advancing: float          # share of moving names that are up (0..100)


class SectorMove(BaseModel):
    sector: str
    avg_change: float             # today's average % move for the sector


class PulseResponse(BaseModel):
    horizon: str
    conviction: int               # 0..100 aggregate model conviction
    conviction_label: str         # Bearish | Cautious | Neutral | Mildly Bullish | Bullish
    avg_prob_up: float            # mean classifier P(up) across the universe
    tilted_up: int                # # of names the model tilts UP
    universe: int                 # # of names scored
    breadth: BreadthInfo
    leading_sector: Optional[SectorMove] = None
    lagging_sector: Optional[SectorMove] = None
    regime: str
    stance: str                   # desk stance implied by the regime


class FundamentalInfo(BaseModel):
    market_cap_cr: Optional[float] = None   # market capitalisation in ₹ crore
    pe: Optional[float] = None              # trailing P/E
    forward_pe: Optional[float] = None
    pb: Optional[float] = None              # price / book
    roe: Optional[float] = None             # return on equity, %
    roa: Optional[float] = None             # return on assets, %
    de: Optional[float] = None              # debt / equity, ratio
    revenue_growth: Optional[float] = None  # %
    earnings_growth: Optional[float] = None # %
    dividend_yield: Optional[float] = None  # %
    beta: Optional[float] = None


class FundamentalsResponse(BaseModel):
    fundamentals: Dict[str, FundamentalInfo]


class ScreenTechnicals(BaseModel):
    rsi_14: Optional[float] = None
    macd_hist: Optional[float] = None
    vs_sma_50: Optional[float] = None        # (close-SMA50)/SMA50; >0 = above
    vs_sma_200: Optional[float] = None
    from_52w_high: Optional[float] = None    # <0 = below the high
    from_52w_low: Optional[float] = None
    ret_5d: Optional[float] = None
    ret_20d: Optional[float] = None
    ret_60d: Optional[float] = None
    rvol: Optional[float] = None             # volume vs 20-day average
    garch_vol: Optional[float] = None


class ScreenSignal(BaseModel):
    side: str                                # LONG | SHORT
    rank: Optional[int] = None
    confidence: Optional[float] = None       # meta-label confidence (0..1)


class ScreenRow(BaseModel):
    ticker: str
    company_name: Optional[str] = None
    sector: Optional[str] = None
    current_price: Optional[float] = None
    pct_change: Optional[float] = None       # today's % move
    direction: str
    probability: float
    predicted_return: Optional[float] = None
    signal_strength: str
    technicals: ScreenTechnicals
    fundamentals: Optional[FundamentalInfo] = None
    signal: Optional[ScreenSignal] = None
    regime: str


class ScreenResponse(BaseModel):
    horizon: str
    count: int
    rows: List[ScreenRow]


class NewsItem(BaseModel):
    headline: str
    link: str
    source: str
    published: Optional[str] = None
    summary: Optional[str] = None


class NewsResponse(BaseModel):
    sector: str
    count: int
    articles: List[NewsItem]


class NewsSectorsResponse(BaseModel):
    sectors: List[str]
