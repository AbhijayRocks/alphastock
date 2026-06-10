# Quant Roadmap — Accuracy & Trust

Living doc. Goal: move the pipeline from "guess a direction per stock" to a
**trustworthy, market-neutral, cross-sectional** system, validated honestly.

Status legend: ☐ todo · ◐ in progress · ☑ done · ✗ dropped

---

## Tier 0 — Earn trust (validate honestly, de-bias)
- ☑ **Realistic cost model** — STT + brokerage + slippage + market impact (sqrt law), per-side bps. `training/costs.py`
- ☑ **Honest cross-sectional metrics** — Information Coefficient (IC), IC-IR, t-stat; long/short quintile backtest. `training/cross_sectional.py`, `training/validation.py`
- ☑ **Deflated / Probabilistic Sharpe (PSR/DSR)** — penalize multiple-trial selection bias. `training/validation.py`
- ☑ **🔴 LEAK FOUND & FIXED — Ichimoku Chikou (ICS) look-ahead.** `ta.ichimoku` default emits the lagging span = `close.shift(-26)` (future close) and `lookahead=True` forward-shifts the cloud. The cross-sectional model paired it with current-price features to reconstruct the forward return → fake IC 0.28 / Sharpe 8.9. Fixed in `features/technical.py` (`lookahead=False`, drop ICS). Caught *by the trust harness* — exactly its job.
- ◐ **Retrain production models on clean features** — the 750 per-stock models were trained with the leak; rebuilding + retraining on clean data.
- ☐ **Combinatorial Purged CV (CPCV)** with embargo — distribution of Sharpes, not one number.
- ☐ **Probability of Backtest Overfitting (PBO)**.
- ☐ **Fundamentals look-ahead fix** — `fetch_fundamentals` broadcasts *current* ratios backward. (Currently the NaN filter drops them from the cross-section anyway; revisit if re-added.)
- ☐ **Survivorship bias** — using today's Nifty-50 over 18y. Document loudly; ideally point-in-time index membership.

## Tier 1 — Change the problem (highest alpha/effort)
- ☑ **Cross-sectional long/short ranking (baseline)** — one LightGBM over the stacked panel predicts the *demeaned* (market-neutral) forward return; long/short top/bottom quintile. `training/cross_sectional.py`
  - **Clean honest result (5d):** IC mean **0.036**, t-stat **7.1**, L/S Sharpe **0.92** (net of costs), ann **10.5%**, maxDD −10.8%, DSR **0.61**. → real but modest signal; not yet "trustworthy" (DSR<0.95). A baseline to beat with the items below.
- ☑ **Learning-to-rank objective** (LightGBM LambdaRank) — `_lgb_rank` in `cross_sectional.py`. Modest lift over regression (Sharpe 0.50→0.60, DSR 0.29→0.36 on the 3-way split).
- ☑ **Meta-labeling** — secondary model predicts *whether the primary side is correct*, sizes bets by confidence. `_lgb_meta` / `_ls_meta_backtest`. **Big win: Sharpe 0.60→1.27, DSR 0.36→0.80.** Run: `python -m training.cross_sectional compare 5d`.
- ☑ **Triple-barrier labeling** (vol-scaled TP/SL, path-dependent) — `training/labeling.py`; `build_panel(label="triple_barrier")`. Cleaner target → lifted best Sharpe 1.27→**1.43**, DSR 0.80→**0.885**.
- ☑ **Sample-uniqueness weighting** — `_sample_weights` blends recency with uniqueness (∝ 1/triple-barrier holding period); used by the rank model + production. `triple_barrier_full` returns holding days.
- ☑ **Wired cross-sectional signal into the app** — `GET /api/signals?horizon=`, served by `ModelRegistry.cross_sectional_signals` from the saved production model (`train_production`/`generate_signals`), shown on the Dashboard "Long / Short Signals" card. Live board enriched with name/sector/price + meta confidence.

## Tier 2 — Economic-prior features
- ☑ **Price-based factors** — 12-1 & 6-1 momentum (skip last month), momentum acceleration, liquidity/size proxy (`ln_advol`). `_add_stock_factors` in `cross_sectional.py`. Lifted rank IC 0.033→0.040. (Value/quality need point-in-time fundamentals — deferred.)
- ☑ **Cross-sectional standardization** — z-score features within each day; auto-drop market-wide (zero cross-sectional variance) features. `training/cross_sectional.py`
- ☐ **Point-in-time NLP** — earnings/news embeddings (FinBERT scaffolding exists), no look-ahead.

## Tier 3 — Portfolio construction  ✅ (live in `/api/optimize_portfolio`, `models/portfolio.py`)
- ☑ **Covariance shrinkage (Ledoit-Wolf)** — `shrink_covariance` shrinks the GARCH covariance toward its diagonal (intensity from sklearn Ledoit-Wolf). Applied before every optimization.
- ☑ **Hierarchical Risk Parity (HRP)** — `hierarchical_risk_parity`; clustering + recursive bisection, no matrix inversion. `method="hrp"`.
- ☑ **Black-Litterman** — `black_litterman_returns`; blends the model's predicted returns (views) with index-weight equilibrium. **Default method**, anchored by real NIFTY index weights.
- ☑ **Constraints** — 40% per-position cap (anti-concentration) in `optimize_portfolio(max_weight=)`. (Turnover penalty / sector-beta neutrality still ☐.)
- ☐ **DCC-GARCH** (dynamic correlations) — future upgrade from current CCC.

## Tier 4 — Bigger models (last; overfit-prone)
- ☐ **CatBoost + stacking meta-learner** (cheap diversity).
- ☐ **TFT / PatchTST / N-HiTS** — joint multi-asset multi-horizon (scaffolding in `models/tft_model.py`).
- ☐ **Conformal prediction** — distribution-free, guaranteed-coverage intervals.

---

## Changelog
- **2026-06-08** Built Tier 0 trust harness (`costs.py`, `validation.py`) + Tier 1 cross-sectional baseline (`cross_sectional.py`).
- **2026-06-08** 🔴 Trust harness immediately caught a **look-ahead leak**: Ichimoku Chikou span (`ichi_ics` = future close) inflated cross-sectional IC to 0.28 / Sharpe 8.9. Fixed in `technical.py`; clean result is IC 0.036 / Sharpe 0.92 (real but modest). Rebuilt all features clean.
- **2026-06-08** (in progress) Retraining the 750 production per-stock models on clean features (they were trained with the leak).
- **2026-06-08** Added learning-to-rank (LambdaRank) + **meta-labeling** to the cross-sectional model. Bake-off: regression 0.50 → rank 0.60 → **rank+meta 1.27** L/S Sharpe (DSR 0.80). `compare_models()`.
- **2026-06-08** Added **price factors** (`_add_stock_factors`) + **triple-barrier labeling** (`labeling.py`). Best config now **rank+meta+factors+triple-barrier: Sharpe 1.43, DSR 0.885, win 60.7%**. Run: `python -m training.cross_sectional` then `compare_models(label="triple_barrier")`.
- **2026-06-08** Wired the cross-sectional long/short board into the app (`GET /api/signals` + Dashboard card). **Clean retrain of all 750 per-stock models complete** and loaded — all 3 horizons leak-free. Backend restarted & verified.
- **2026-06-08** **Tier 3 portfolio upgrades shipped & live:** Ledoit-Wolf covariance shrinkage, Hierarchical Risk Parity, Black-Litterman (default), 40% position cap — `/api/optimize_portfolio?method=`. Verified on real data: BL/HRP give balanced books vs MVO's concentration.
- **2026-06-08** Added **sample-uniqueness weighting** (recency × 1/holding-period) to the cross-sectional rank/production model.
- **2026-06-08** **Productionization / app surface (not new alpha):** automatic daily data refresh (incremental ingest fix + in-process scheduler); Market Pulse dashboard hero (`/api/pulse`, aggregate model conviction + breadth); screener overhaul on a single `/api/screen` board with fundamental/technical/model filters, presets, and saved screens; `/api/fundamentals` exposed (current-snapshot — flagged for the look-ahead item below).
- **Next:** CPCV / PBO validation rigor · Tier 4 (CatBoost+stacking, conformal intervals, TFT) · **point-in-time fundamentals** (the screener now surfaces the current snapshot — replace with PIT before using fundamentals in any backtest) + survivorship.
