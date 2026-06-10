# AlphaStock — TODO / Open Items

Last updated: 2026-06-10. Owner context: production "fake data everywhere except
ticker" bug. See `DEPLOYMENT.md` for the full runbook and `PROJECT_STATE.md` for
system state.

## 🔴 Blocking decision — Render is out of RAM (DECIDE FIRST)
The production root cause (git-ignored artifacts never reaching Render) is FIXED:
models now download from Hugging Face on boot and 750 models load successfully.
**But Render's free 512 MB tier has almost no headroom left after loading the
models — any analytics request (`/predict`, `/pulse`, `/screen`, `/signals`)
OOM-kills the instance (502/503).** Boot is stable; serving analytics is not.

Pick one path:
- [ ] **Option A — Upgrade Render to 2 GB (Standard, ~$25/mo).** Reliable, full
      functionality, no code changes. NOTE: Starter ($7) is still 512 MB and will
      NOT help — must be the 2 GB Standard tier (verify current Render pricing).
- [ ] **Option B — Stay free, add lazy model loading.** Load models per-ticker on
      demand (LRU cache) instead of all 750 at startup. Single-stock Analysis
      (`/predict`, `/explain`, `/backtest`, `/simulate`) would work on 512 MB.
      Dashboard aggregate cards (`/pulse`, `/screen`, `/signals` — all 50 stocks at
      once) would still OOM and stay mock. Partial result, more dev time.
- [ ] **Option C — Aggressive squeeze (uncertain).** Lower `ALPHASTOCK_FEATURE_ROWS`
      (e.g. 300) + load only the classifiers needed (drop the two regressors per
      horizon → ~300 fewer models). Might fit single-stock predict; aggregates
      still risky. No guarantee.

## 🟠 Security
- [ ] **Revoke the leaked Hugging Face token** (`hf_Xtkrw…`, exposed in a
      screenshot) at huggingface.co → Settings → Access Tokens. Since the
      artifacts repo is now **public**, Render does NOT need a token, so you can
      simply delete it (or replace and update Render's `HF_TOKEN`).

## 🟢 Done (this session)
- [x] Diagnosed: model + feature artifacts are git-ignored → never deployed to
      Render → all model endpoints fell back to mock; only `/prices` (live
      yfinance, ticker) looked real.
- [x] `data_pipeline/hf_sync.py` — `ensure_artifacts()` pulls artifacts from the
      HF Hub on boot; `prepare_and_upload()` trims + uploads a slim serving set.
- [x] `api/main.py` — calls `ensure_artifacts()` before the registry loads.
- [x] `api/model_registry.py` — keep only the last `ALPHASTOCK_FEATURE_ROWS`
      (default 750) feature rows in RAM; gate the startup signal warm-up behind
      `ALPHASTOCK_WARM_SIGNALS` (default off) — the warm-up was OOM-crash-looping
      the instance at boot.
- [x] Uploaded artifacts to `eLeetCoder/alphastock-artifacts` (made **public**).
- [x] Render env set: `HF_REPO_ID=eLeetCoder/alphastock-artifacts`,
      `ALPHASTOCK_DAILY_UPDATE=0`.
- [x] Pushed to `Stock_Web_App` (origin, the Render-connected repo) and
      `AbhijayRocks/alphastock`. Commits `c42ab62`, `c919ab0`.
- [x] Verified: boot reaches `models_loaded: 750, stocks_available: 50` and is
      stable until an analytics request hits it.

## ⚪ Later / backlog
- [ ] Make `/signals` + `/screen` memory-safe (have `build_panel` use the resident
      trimmed tails instead of `load_all_features()` re-reading full parquets) so
      they survive even on small instances.
- [ ] yfinance rate-limiting (`YFRateLimitError`) on the live-price refresh —
      occasional single-stock failures; add backoff / spread requests.
- [ ] Cold-start cost: free instance re-downloads ~160 MB artifacts on each cold
      boot. Lower `ALPHASTOCK_SHIP_ROWS` to shrink, or use an always-on instance.
- [ ] Re-trim/re-upload artifacts whenever models are retrained
      (`python -m data_pipeline.hf_sync`).
- [ ] CONFIRM-ON-2GB: once on a bigger instance, set `ALPHASTOCK_WARM_SIGNALS=1`
      to pre-warm the signal board.
