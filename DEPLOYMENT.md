# Deployment — getting real data into production

This is the runbook for the production bug where **only the ticker showed real
prices and everything else was mock data**.

## Why it happened

The trained models (~97 MB) and feature panels (~360 MB) are **git-ignored**
(`.gitignore` → `backend/artifacts/models/`, `backend/artifacts/features/`,
`*.pkl`, `*.parquet`). Render deploys from GitHub, so the container booted with
an **empty `artifacts/` directory**:

- `/api/prices` worked → it fetches live from yfinance, no models needed → **the
  ticker tape looked real.**
- `/api/predict`, `/screen`, `/pulse`, `/signals`, `/explain`, `/backtest`
  needed the missing models → returned empty/errored → the frontend
  (`client.js`, `mockMode: 'auto'`) **silently fell back to mock data**.

The `huggingface-hub` dependency and `HF_TOKEN`/`HF_REPO_ID` config existed, but
the actual download-at-startup code was never written.

## The fix (in code)

1. **`data_pipeline/hf_sync.py`**
   - `ensure_artifacts()` — at startup, if `artifacts/` has no models and
     `HF_REPO_ID` is set, downloads the artifact set from a Hugging Face repo.
   - `prepare_and_upload()` — trims the feature parquets to a recent window and
     uploads a slim artifact set to the Hub.
2. **`api/main.py`** — calls `ensure_artifacts()` before the registry loads.
3. **`api/model_registry.py`** — `_load_latest_features()` keeps only the last
   `ALPHASTOCK_FEATURE_ROWS` (default **750**) rows per stock in RAM, so the
   process fits Render's 512 MB free tier. Backtest / cross-sectional still read
   the full (trimmed) parquet from disk, so they are unaffected.

## One-time setup you must do

### 1. Create a Hugging Face repo + token
- Sign up at <https://huggingface.co> (free).
- Settings → **Access Tokens** → create a **write** token.
- You don't need to create the repo by hand — the upload step makes it.

### 2. Upload the artifacts (from your machine — it has the full 456 MB)
```bash
cd backend
# activate the env that has the artifacts/ folder built
set HF_TOKEN=hf_xxxxxxxxxxxxxxxxx           # PowerShell: $env:HF_TOKEN="hf_..."
set HF_REPO_ID=YOUR_USERNAME/alphastock-artifacts
python -m data_pipeline.hf_sync
```
This trims each feature parquet to the last ~2000 bars (≈8 yrs; tune with
`ALPHASTOCK_SHIP_ROWS`), stages models + raw snapshots, and pushes to the Hub.
Re-run it any time you retrain to publish fresh models.

### 3. Configure Render (backend service → Environment)
| Key | Value |
|---|---|
| `HF_REPO_ID` | `YOUR_USERNAME/alphastock-artifacts` |
| `HF_TOKEN` | `hf_xxxxx` (needed only if the repo is private) |
| `ALPHASTOCK_DAILY_UPDATE` | `0` — skip the heavy daily feature rebuild on the 512 MB tier |
| `ALPHASTOCK_FEATURE_ROWS` | *(optional)* lower than 750 if you still hit OOM |

Then **Manual Deploy → Clear build cache & deploy**. On boot the logs should show
`Downloading artifacts from Hugging Face repo ...` then
`Registry loaded: 50 stocks, ~750 models total`.

### 4. Vercel — nothing to change
The ticker already reaching real `/prices` proves `VITE_API_BASE` and CORS are
correct. Once the backend has models, every page returns real data with no
frontend change.

## Verify
```bash
curl https://<your-render-app>.onrender.com/api/health           # coverage > 0
curl -X POST https://<your-render-app>.onrender.com/api/predict \
     -H "Content-Type: application/json" \
     -d '{"ticker":"RELIANCE.NS","horizon":"5d","model":"ensemble_clf"}'
```
A real prediction (not the mock shape) confirms the fix end to end.

## Note on free-tier cold starts
Render free instances spin down when idle and re-download the artifacts on the
next cold boot, so the first request after a long idle is slow. If that matters,
upgrade to a paid instance (persistent disk / always-on) or lower
`ALPHASTOCK_SHIP_ROWS` to shrink the download.
