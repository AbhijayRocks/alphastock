# AlphaStock — Project State (master context doc)

**Purpose:** single source of truth for a fresh chat. What the system is, what's
LIVE in the web app, how to run it, environment gotchas, and what's planned.
Quant research plan lives in `QUANT_ROADMAP.md` (linked at the end).

Last updated: 2026-06-08.

---

## 1. What it is
AI stock-prediction web app for **NIFTY-50** equities. Backend (FastAPI) serves
ML predictions + risk analytics; React frontend ("AlphaStock Terminal") consumes
them. Predicts forward returns/direction at **1d / 5d / 20d** horizons, with
explainability, backtesting, regime detection, volatility & jump risk, and
portfolio optimization.

## 2. How to run
- **Backend:** from `backend/`, `python -m api.main` → serves `0.0.0.0:9000`,
  docs at `:9000/docs`, routes under `/api`. Port via `PORT` env.
- **Frontend:** from `frontend/`, `npm run dev` → `http://localhost:4000`
  (Vite). Talks to `http://localhost:9000/api` (override `VITE_API_BASE`).
- Frontend has **offline mock mode** (`src/data/mock.js`): if the API is
  unreachable or returns empty, it shows synthetic demo data. Real data requires
  the backend up **with trained models loaded**.
- **Automatic daily data refresh (live):** while the backend runs, a daemon
  thread (`api/daily_scheduler.py`) catches up on startup and then refreshes
  shortly after each NSE close (18:00 IST, override `ALPHASTOCK_UPDATE_HOUR`),
  then **hot-reloads features in place — no restart** (`ModelRegistry.reload_live_data`).
  Work is in `data_pipeline/daily_update.py` (incremental OHLCV + macro/index
  refresh → rebuild features only when a newer bar arrived; idempotent, never
  raises). Manual / OS-cron form: `python -m data_pipeline.daily_update [--force]`.
  Disable with `ALPHASTOCK_DAILY_UPDATE=0`.

## 3. Environment & gotchas (IMPORTANT for a new chat)
- **Python 3.14** (`C:\Python314`). Several ML libs don't support it:
  - `numba` → no 3.14 wheels. We ship a **no-op shim `backend/numba.py`** so
    `pandas_ta` imports and runs in pure Python. Don't delete it on 3.14.
  - `shap` → needs numba; **not installed**. We use **native TreeSHAP**
    (LightGBM `pred_contrib` / XGBoost `pred_contribs`) instead — real signed
    SHAP, no dependency.
  - `arch` (GARCH lib) → **not installed**. We use our own dependency-free
    GARCH(1,1) in `features/garch.py`.
  - `pandas_ta` is pinned `0.4.71b0` installed `--no-deps`.
- Installed & working: lightgbm, xgboost, optuna, sklearn, hmmlearn, scipy,
  pandas, numpy, fastapi, uvicorn, yfinance, torch, transformers, sqlalchemy.
- **Disk:** `C:` is tight (system drive). `D:` has space. Artifacts/data live on
  `E:` with the repo. If installs fail with "No space", `pip cache purge`.
- Live market data via **yfinance** (free). Today's date in env may be a weekend
  → "live" price = last trading session.

## 4. Repo layout (key files)
```
backend/
  api/main.py            FastAPI app, CORS, lifespan loads ModelRegistry
  api/routes.py          all endpoints
  api/model_registry.py  loads models, serves predict/explain/backtest/simulate/prices
  api/schemas.py         pydantic request/response shapes
  config.py              tickers, paths, horizons, seeds
  data_pipeline/
    ingestion.py         yfinance OHLCV/macro/index/fundamentals → parquet
    nifty50.py           universe metadata (50 names, sectors)
    news_sentiment.py    FinBERT scaffolding (imports torch/transformers)
  features/
    technical.py         ~150 technical indicators (pandas_ta)
    garch.py             dependency-free GARCH(1,1)  [risk layer]
    pipeline.py          assembles per-stock feature panel + targets
    regime.py            HMM market regime (bull/bear/sideways/crisis)
    selection.py         feature selection (variance/corr/importance)
  models/
    lgbm_xgb.py          LightGBM/XGBoost regressors (Optuna)
    classifier.py        LightGBM/XGBoost classifiers (direction)
    ensemble.py          weighted/stacking ensemble
    montecarlo.py        Merton jump-diffusion Monte Carlo  [risk layer]
    portfolio.py         Markowitz MVO + GARCH covariance
    tft_model.py         (scaffolding, unused) Temporal Fusion Transformer
  training/
    trainer.py           per-stock training orchestration
    backtest.py          long/cash backtest (+ vol targeting)
    costs.py             realistic NSE transaction-cost model   [NEW]
    validation.py        IC, Probabilistic/Deflated Sharpe       [NEW]
    cross_sectional.py   market-neutral long/short ranking model [NEW]
  numba.py               Python-3.14 no-op numba shim
  artifacts/             features/ (parquet) + models/ (trained)
frontend/                React + Vite + Tailwind + recharts
  src/api/client.js      typed API client + mock fallback
  src/pages/             Dashboard, Analysis, Screener, Backtest, Portfolio
QUANT_ROADMAP.md         forward research plan + tier checklist
PROJECT_STATE.md         (this file)
```

## 5. Data & models — current state
- **50/50 NIFTY-50 stocks** ingested (10+ yrs daily OHLCV) + macro + index +
  fundamentals. Stored `artifacts/features/raw/`.
- **Features:** ~193 per stock (technical + macro + index + regime + GARCH +
  sector + fundamentals), per-stock parquet in `artifacts/features/pipeline/`.
- **Regime HMM** fitted (`artifacts/models/regime_hmm.pkl`).
- **Per-stock models:** 1d/5d/20d × 50 stocks × {lightgbm, xgboost,
  lightgbm_clf, xgboost_clf, ensemble_reg, ensemble_clf} → ~750 models.
  - ✅ **All retrained on CLEAN features** (post Ichimoku-leak fix) and loaded —
    all three horizons are leak-free and live.
- **Cross-sectional model:** `artifacts/models/cross_sectional/` (research, not
  yet wired to the API).
- Realistic accuracy: classifiers ~50–57%; cross-sectional IC ~0.036 (real).

## 6. Implemented & LIVE in the web app
### Predictions (`/api/predict`, Analysis + Dashboard)
- Real **ensemble** evaluation (was a constant-0.5 stub — fixed). Direction,
  probability, predicted return, signal strength.
- **GARCH prediction bands** + **Monte-Carlo (Merton) fat-tailed bands** with
  **VaR₉₅, CVaR₉₅, P(up)** (replaces the old fabricated ± heuristic).
- Live `current_price`.
### Explainability (`/api/explain`, Analysis "Key Drivers")
- **Native TreeSHAP** — real signed per-feature contributions (push UP/DOWN).
### Backtest (`/api/backtest`, Backtest page)
- Long/cash strategy on the test set; **classifier signal centered correctly**;
  **GARCH volatility-targeted position sizing** (`avg_exposure` reported).
### Risk · Monte Carlo (`/api/simulate`, Analysis "Risk · Monte Carlo" tab)
- Merton jump-diffusion **fan chart** (p5/p25/p50/p75/p95 price cone) + tail
  metrics. Calibrated to each stock's historical jumps.
### Regime (`/api/regime`)
- HMM bull/bear/sideways/crisis from live Nifty index.
### Prices & history (`/api/prices`, `/api/history`)
- **Live yfinance prices** for the full universe (background-refreshed cache,
  decoupled from trained models). History from stored features.
### Portfolio optimizer (`/api/optimize_portfolio`, Portfolio page)
- Three methods (request `method=`): **black_litterman** (default — blends model
  views with NIFTY index-weight equilibrium), **hrp** (Hierarchical Risk Parity,
  diversification-first), **mvo** (plain Markowitz). All run on a **Ledoit-Wolf-
  shrunk GARCH covariance** with a **40% position cap**. `models/portfolio.py`.
### Market news (`/api/news`, News page)
- Free sector news via **Google News RSS** (no API key, no cost), cached ~15 min.
  User picks a sector → headlines + source + time + link to the publisher.
  `data_pipeline/news.py`. Also `fetch_stock_news` (per-company) available.
### Cross-sectional long/short signals (`/api/signals`, Dashboard card)
- Market-neutral **rank + meta-labeling** board (the quant research model, now
  productionized): top quintile LONG / bottom SHORT, with score, meta confidence,
  name/sector/live price. Model: `artifacts/models/cross_sectional/prod_*_5d`.
  Warmed at startup, cached 1h. (5d trained; 1d/20d optional via `train_production`.)
### Auth (`/api/auth/*`, `/api/user/*`)
- JWT + SQLite accounts, per-user watchlist/preferences (offline fallback).

## 7. API surface
`GET  /api/health` · `GET /api/regime` · `GET /api/models` · `GET /api/prices` ·
`GET /api/history/{ticker}` · `POST /api/predict` · `POST /api/explain` ·
`POST /api/backtest` · `POST /api/simulate` · `POST /api/optimize_portfolio` ·
`GET /api/signals?horizon=` (cross-sectional long/short board) ·
`GET /api/news?sector=` · `GET /api/news/sectors` (free Google-News RSS) ·
`POST /api/auth/register|login` · `GET/PATCH /api/auth/me` · `GET/PUT /api/user/data`

## 8. Risk / uncertainty stack (how the pieces fit)
```
ML model      → drift / direction (LightGBM/XGBoost ensembles)
GARCH(1,1)    → conditional volatility  (features/garch.py)
Merton jumps  → discontinuous gap/crash risk (models/montecarlo.py)
Monte Carlo   → full forward distribution → bands, VaR, CVaR, fan chart
Regime HMM    → market context
```
GARCH also feeds: prediction bands, a model feature (`garch_vol`,
`garch_vol_ratio`), vol-targeted backtest sizing, and the portfolio covariance.

## 9. Bugs fixed this project (don't reintroduce)
1. Ensemble predict returned constant 0.5 → real member eval + weights.
2. Backtest fed classifier probabilities as signed returns → center on 0.5.
3. `INFOSYS.NS` → `INFY.NS` (Infosys never downloaded).
4. Feature-selection look-ahead → fit selector on train+val only.
5. Portfolio optimizer crashed on unequal-length histories → date-aligned.
6. Stray `4` token in `regime.py`; dead code in `lgbm_xgb.py`.
7. 🔴 **Ichimoku Chikou (`ichi_ics`) look-ahead leak** = `close.shift(-26)`
   (future price). Inflated cross-sectional IC to 0.28 / Sharpe 8.9. Fixed in
   `technical.py` (`lookahead=False`, drop ICS). Features rebuilt; models
   retraining.
8. **Daily data never auto-updated.** `run_incremental_update` was doubly broken:
   it reused `fetch_ohlcv`'s 252-row history guard (so every short pull was
   discarded → 0 stocks appended) and used `end=date.today()`, which yfinance
   treats as *exclusive* (so today's bar was never fetched). Added a `min_rows`
   param (incremental passes `1`) and set `end=today+1`. Also wired an in-process
   daily scheduler (was previously no automation at all). See §2.

## 10. Known open risks / limitations
- **Survivorship bias:** using today's NIFTY-50 over 18y (winners only).
- **Fundamentals look-ahead:** `fetch_fundamentals` = current snapshot broadcast
  back (currently dropped by the cross-sectional NaN filter; risk if re-added to
  per-stock models — they DO include `fund_*`).
- **Validation:** still single purged walk-forward; no CPCV/PBO yet.
- Per-stock models are independent & predict absolute return (not market-neutral).
- shap/arch/numba/TFT unavailable on Python 3.14 (worked around or unused).

## 11. Quant research track (see QUANT_ROADMAP.md)
Tier 0 trust harness ✅ (costs, IC, PSR/DSR) · Tier 1 cross-sectional model ✅:
- Progression (net-of-cost L/S Sharpe → Deflated Sharpe):
  regression 0.50/0.29 → +rank 0.60/0.36 → +meta **1.27/0.80**
  → +factors+triple-barrier **1.43/0.885** (win 60.7%). Best config = rank + meta
  + price factors + triple-barrier labels.
- Files: `training/{costs,validation,cross_sectional,labeling}.py`.
- Run: `python -m training.cross_sectional` (baseline) ·
  `... compare 5d` (bake-off) · `... production 5d` (train+save deployable model).
- ✅ **Wired into the app:** `GET /api/signals` + Dashboard "Long / Short Signals"
  card. Production model saved at `artifacts/models/cross_sectional/prod_*_5d`.

**Next:** sample-uniqueness weighting → Tier 3 portfolio (HRP / Black-Litterman /
shrinkage). All per-stock models (1d/5d/20d) retrained clean & loaded — no pending
restart.

## 12. Session changelog (high level)
- Fixed 7 pipeline bugs (see §9).
- Added live prices, GARCH risk layer, Merton Monte-Carlo, native SHAP, GARCH
  portfolio covariance.
- Ran full data pipeline: ingest → features → train 750 models (3 horizons).
- Built quant trust harness + cross-sectional model; **caught & fixed the
  Ichimoku leak**; rebuilding/retraining clean.
