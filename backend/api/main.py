"""
api/main.py — FastAPI application entry point.

HOW TO RUN (host/port are environment-driven — see config.py):
  Simplest (honors HOST / PORT / RELOAD env vars; defaults to 0.0.0.0:9000):
    python -m api.main

  Development (auto-reload on code changes):
    uvicorn api.main:app --reload --port %PORT%

  Production (Render sets PORT automatically):
    uvicorn api.main:app --host 0.0.0.0 --port %PORT%

WHAT HAPPENS AT STARTUP:
  1. FastAPI app is created
  2. CORS is configured (allows React frontend to call the API)
  3. Model registry loads all trained models into memory
  4. API is ready to serve requests

INTERACTIVE DOCS:
  Once running, visit:
    http://localhost:8000/docs      → Swagger UI (try endpoints live)
    http://localhost:8000/redoc    → ReDoc (clean documentation)
"""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.routes import router, set_registry
from api.model_registry import ModelRegistry
from auth import init_db, auth_router
from config import LOG_LEVEL, API_PORT

logging.basicConfig(level=LOG_LEVEL, format="%(asctime)s | %(levelname)s | %(message)s")
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Lifespan context manager — runs startup code before the app serves requests.

    WHY LIFESPAN (not @app.on_event):
      The modern FastAPI way. Cleaner than deprecated event handlers.
      Everything before `yield` runs at startup.
      Everything after `yield` runs at shutdown.
    """
    # ── Startup ────────────────────────────────────────────────────────────────
    logger.info("AlphaStock API starting up...")

    # Accounts/auth database — created first so login works even if the heavy
    # ML registry fails to load (e.g. models not yet downloaded).
    init_db()
    logger.info("Auth database ready")

    # Pull model + feature artifacts from the Hugging Face Hub if they aren't on
    # disk (the case on a fresh clone-based deploy like Render — they're git-
    # ignored). Local dev with already-built artifacts is a no-op. Never raises.
    try:
        from data_pipeline.hf_sync import ensure_artifacts
        ensure_artifacts()
    except Exception as e:  # noqa: BLE001
        logger.error(f"Artifact sync skipped: {e}")

    try:
        registry = ModelRegistry()
        registry.load_all()
        set_registry(registry)
        logger.info(f"API ready — {len(registry.available_tickers)} stocks loaded")

        # Keep market data current automatically: a daemon thread catches up on
        # startup and then refreshes shortly after each NSE close, hot-reloading
        # the registry in place (no restart). See api/daily_scheduler.py.
        try:
            from api.daily_scheduler import start_daily_scheduler
            start_daily_scheduler(registry)
        except Exception as e:  # noqa: BLE001
            logger.error(f"Daily auto-refresh scheduler failed to start: {e}")
    except Exception as e:  # noqa: BLE001
        logger.error(f"Model registry failed to load: {e}. Auth + docs still available.")

    logger.info(f"Docs available at: http://localhost:{API_PORT}/docs")

    yield   # API serves requests here

    # ── Shutdown ───────────────────────────────────────────────────────────────
    logger.info("AlphaStock API shutting down...")


# Create FastAPI app
app = FastAPI(
    title       = "AlphaStock Prediction API",
    description = """
    AI-powered stock price prediction for Nifty 50 stocks.

    Features:
    - Direction predictions (UP/DOWN) with confidence scores
    - 3 prediction horizons: 1 day, 5 days, 20 days
    - SHAP-based explainability: know WHY the model predicted what it did
    - Market regime detection: bull / bear / sideways / crisis
    - Backtesting: see how the model would have performed historically

    Built with LightGBM, XGBoost, and ensemble methods trained on 10 years of NSE data.
    """,
    version     = "1.0.0",
    lifespan    = lifespan,
)

# ── CORS Middleware ────────────────────────────────────────────────────────────
# CORS = Cross-Origin Resource Sharing
# Without this, the browser blocks React (port 5173) from calling FastAPI (port 8000)
# because they're on different ports = different "origins"

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",    # Vite dev server
        "http://localhost:3000",    # Create React App (if used)
        "http://127.0.0.1:5173",
        "https://*.onrender.com",   # Render deployment
        "*",                        # Allow all for now — restrict in production
    ],
    allow_credentials = True,
    allow_methods     = ["*"],
    allow_headers     = ["*"],
)

# ── Register Routes ────────────────────────────────────────────────────────────
app.include_router(router, prefix="/api")
app.include_router(auth_router, prefix="/api")   # /api/auth/* and /api/user/*

# ── Root Endpoint ──────────────────────────────────────────────────────────────
@app.get("/")
async def root():
    return {
        "name":    "AlphaStock Prediction API",
        "version": "1.0.0",
        "docs":    "/docs",
        "health":  "/api/health",
        "status":  "running",
    }


# ── Run directly: `python -m api.main` ───────────────────────────────────────────
# Reads HOST / PORT / RELOAD from the environment via config.py so the bind
# address is never hardcoded.
if __name__ == "__main__":
    import uvicorn
    from config import API_HOST, API_PORT, API_RELOAD

    uvicorn.run("api.main:app", host=API_HOST, port=API_PORT, reload=API_RELOAD)
