"""
config.py — Single source of truth for all settings.

WHY THIS EXISTS:
  Never hardcode paths, tickers, or API keys inside individual files.
  Every file imports from here. Change one thing here, it updates everywhere.
"""

import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()  # reads your .env file automatically

# ── Paths ──────────────────────────────────────────────────────────────────────
ROOT_DIR       = Path(__file__).parent          # alpha_stock/
ARTIFACTS_DIR  = ROOT_DIR / "artifacts"
FEATURES_DIR   = ARTIFACTS_DIR / "features"
MODELS_DIR     = ARTIFACTS_DIR / "models"
LOGS_DIR       = ROOT_DIR / "logs"

for _dir in [FEATURES_DIR, MODELS_DIR, LOGS_DIR]:
    _dir.mkdir(parents=True, exist_ok=True)

# ── Nifty 50 Universe ──────────────────────────────────────────────────────────
# yfinance uses the ".NS" suffix for NSE-listed stocks
NIFTY50_TICKERS = [
    "RELIANCE.NS", "TCS.NS", "HDFCBANK.NS", "BHARTIARTL.NS", "ICICIBANK.NS",
    "INFOSYS.NS",  "SBIN.NS", "HINDUNILVR.NS", "ITC.NS",      "LT.NS",
    "KOTAKBANK.NS","AXISBANK.NS","WIPRO.NS",   "HCLTECH.NS",  "ASIANPAINT.NS",
    "MARUTI.NS",   "SUNPHARMA.NS","ULTRACEMCO.NS","TITAN.NS", "BAJFINANCE.NS",
    "NTPC.NS",     "POWERGRID.NS","ONGC.NS",   "COALINDIA.NS","NESTLEIND.NS",
    "BAJAJFINSV.NS","M&M.NS",    "TECHM.NS",   "ADANIENT.NS", "ADANIPORTS.NS",
    "JSWSTEEL.NS", "TATASTEEL.NS","HINDALCO.NS","GRASIM.NS",  "CIPLA.NS",
    "DRREDDY.NS",  "DIVISLAB.NS","EICHERMOT.NS","HEROMOTOCO.NS","BPCL.NS",
    "BRITANNIA.NS","TATACONSUM.NS","APOLLOHOSP.NS","INDUSINDBK.NS","SHRIRAMFIN.NS",
    "SBILIFE.NS",  "HDFCLIFE.NS","BAJAJ-AUTO.NS","BEL.NS",    "TRENT.NS",
]

# Nifty 50 index itself — useful as a market-wide feature
NIFTY_INDEX_TICKER = "^NSEI"
SENSEX_TICKER      = "^BSESN"

# Macro indicators available free on yfinance
MACRO_TICKERS = {
    "usd_inr":    "USDINR=X",     # USD/INR exchange rate
    "brent":      "BZ=F",         # Brent crude oil futures
    "gold":       "GC=F",         # Gold futures
    "vix_india":  "^INDIAVIX",    # India VIX (fear index)
    "us_10y":     "^TNX",         # US 10-year treasury yield
    "dxy":        "DX-Y.NYB",     # US Dollar index
}

# ── Data Settings ──────────────────────────────────────────────────────────────
HISTORICAL_START   = "2007-01-01"   # Fetch data as far back as possible for deep learning
HISTORICAL_END     = "today"        # auto-resolves to current date
DATA_INTERVAL      = "1d"           # daily OHLCV bars

# ── Prediction Horizons ────────────────────────────────────────────────────────
# We predict all three simultaneously — one model, multiple output heads
HORIZONS = {
    "1d":  1,    # next day close
    "5d":  5,    # next week close
    "20d": 20,   # next month close
}

# ── Feature Engineering ────────────────────────────────────────────────────────
# Lookback window fed into sequence models (TFT, PatchTST)
SEQUENCE_LENGTH    = 120    # 120 trading days (~6 months) of history per sample
MIN_HISTORY_DAYS   = 252    # need at least 1 year to compute annual features

# ── Model Training ─────────────────────────────────────────────────────────────
SEED               = 42
TEST_RATIO         = 0.15   # last 15% of time = test set (never touched during training)
VAL_RATIO          = 0.15   # 15% of remaining = validation
N_CV_SPLITS        = 5      # walk-forward cross-validation folds

# Optuna tuning budget (increase for better results, decrease for speed)
N_OPTUNA_TRIALS    = 50

# ── Deep Learning ──────────────────────────────────────────────────────────────
BATCH_SIZE         = 64
MAX_EPOCHS         = 100
LEARNING_RATE      = 1e-3
EARLY_STOPPING     = 15     # stop if val loss doesn't improve for 15 epochs

# ── API Keys (loaded from .env) ────────────────────────────────────────────────
# Create a .env file in alpha_stock/ with these variables:
#   NEWS_API_KEY=your_key_here
#   HF_TOKEN=your_huggingface_token_here
NEWS_API_KEY       = os.getenv("NEWS_API_KEY", "")
HF_TOKEN           = os.getenv("HF_TOKEN", "")
HF_REPO_ID         = os.getenv("HF_REPO_ID", "your-username/alpha-stock-models")

# ── Hugging Face Model Storage ─────────────────────────────────────────────────
# After training, artifacts are pushed here and pulled by Render at startup
HF_MODELS_SUBDIR   = "models"
HF_FEATURES_SUBDIR = "features"

# ── Logging ────────────────────────────────────────────────────────────────────
LOG_LEVEL          = "INFO"
LOG_FILE           = LOGS_DIR / "pipeline.log"

# ── Render / API ───────────────────────────────────────────────────────────────
# Host + port are environment-driven so the same code runs locally, in Docker,
# and on Render without edits. Override with HOST / PORT (and RELOAD for dev).
API_HOST           = os.getenv("HOST", "0.0.0.0")
API_PORT           = int(os.getenv("PORT", 9000))
API_RELOAD         = os.getenv("RELOAD", "false").lower() in ("1", "true", "yes", "on")
CACHE_TTL_SECONDS  = 3600   # cache predictions for 1 hour in Redis
