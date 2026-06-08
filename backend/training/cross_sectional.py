"""
training/cross_sectional.py — Market-neutral cross-sectional ranking model.

THE BIG IDEA (Tier 1):
  Instead of 50 independent models each guessing "will RELIANCE go up?", we train
  ONE model over the whole panel that predicts each stock's RELATIVE return — how
  it ranks against the other 49 on the same day. Then we go long the top names and
  short the bottom, market-neutral.

WHY THIS IS HOW real equity quant desks work:
  • Strips out market beta (the dominant, ~unpredictable factor) → isolates alpha.
  • Pools all stocks into one model → ~50x the data, far more robust, less overfit.
  • Naturally hedged: a long/short book doesn't care which way the index goes.

KEY MECHANICS:
  • Target = forward return DEMEANED across the cross-section each day (the alpha).
  • Features = the existing engineered features, but Z-SCORED WITHIN EACH DAY so
    they're relative ("is this stock's RSI high vs its peers today?").
  • Market-wide features (macro, index, regime, calendar) have ZERO cross-sectional
    variance — identical for every stock that day — so they're dropped automatically.
    A cross-sectional model can only use STOCK-SPECIFIC signal.

EVALUATION (Tier 0 trust):
  • Information Coefficient (IC) — the core alpha metric.
  • Long/short quintile backtest with a REALISTIC cost model (training/costs.py).
  • Probabilistic & Deflated Sharpe — is the edge real or a multiple-testing fluke?
"""

import logging
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
import lightgbm as lgb

from config import SEED, MODELS_DIR, HORIZONS, LOG_LEVEL
from features.pipeline import load_all_features
from training.costs import DEFAULT_COSTS
from training.validation import information_coefficient, deflated_sharpe_ratio, annualize_sharpe

logging.basicConfig(level=LOG_LEVEL, format="%(asctime)s | %(levelname)s | %(message)s")
logger = logging.getLogger(__name__)

CS_DIR = MODELS_DIR / "cross_sectional"
CS_DIR.mkdir(parents=True, exist_ok=True)

# Raw price levels aren't comparable cross-sectionally; everything else is fair game.
# tb_days is the triple-barrier holding period (used for uniqueness weights, not a feature).
_EXCLUDE = {"open", "high", "low", "close", "volume", "tb_days"}
_MIN_NAMES = 15          # need a wide-enough cross-section per day to rank


# ── Factor & label augmentation (per stock, causal) ─────────────────────────────

def _add_stock_factors(sub: pd.DataFrame) -> pd.DataFrame:
    """
    Add canonical cross-sectional FACTOR features from price/volume. All causal.
    The big addition is 12-1 momentum (return over the past year, SKIPPING the most
    recent month to avoid short-term-reversal contamination) — the textbook
    cross-sectional momentum factor, which the existing technicals don't capture.
    """
    c = sub["close"]
    sub["mom_12_1"] = c.shift(21) / c.shift(252) - 1          # 12-month, skip last month
    sub["mom_6_1"]  = c.shift(21) / c.shift(126) - 1          # 6-month, skip last month
    sub["mom_accel"] = sub["mom_6_1"] - sub["mom_12_1"]       # momentum acceleration
    if "volume" in sub.columns:
        advol = (c * sub["volume"]).rolling(20).mean()
        sub["ln_advol"] = np.log(advol.clip(lower=1))          # liquidity / size proxy
    return sub


def build_panel(horizon: str = "5d", all_features: Optional[Dict[str, pd.DataFrame]] = None,
                label: str = "fixed", add_factors: bool = True, drop_target_na: bool = True
                ) -> Tuple[pd.DataFrame, List[str], str]:
    """
    Stack every stock into one (date, ticker) panel, cross-sectionally z-score the
    features, and demean the forward-return target within each day.

    Returns (panel, feature_cols, target_col). Panel has a 'y' column (demeaned
    target) and a raw target column (for P&L), indexed by ['date','ticker'].
    """
    target_col = f"target_{horizon}"
    if all_features is None:
        all_features = load_all_features()

    horizon_days = HORIZONS.get(horizon, 5)
    frames = []
    for ticker, df in all_features.items():
        if target_col not in df.columns:
            continue
        sub = df.copy()
        if add_factors:
            sub = _add_stock_factors(sub)
        if label == "triple_barrier" and "close" in sub.columns:
            from training.labeling import triple_barrier_full
            tb = triple_barrier_full(sub["close"], horizon=horizon_days, pt=1.0, sl=1.0)
            sub["target_tb"] = tb["target_tb"].values
            sub["tb_days"] = tb["tb_days"].values
        sub["ticker"] = ticker
        sub.index.name = "date"
        frames.append(sub.reset_index())
    if not frames:
        raise ValueError("No features with the requested target found")

    # Which column the model is TRAINED to rank (triple-barrier = cleaner target);
    # P&L is always evaluated on the actual fixed-horizon return (target_col).
    demean_col = "target_tb" if label == "triple_barrier" else target_col

    panel = pd.concat(frames, ignore_index=True)
    if drop_target_na:
        panel = panel.dropna(subset=[target_col, demean_col])
    # else: keep the most recent rows (target unknown) for LIVE signal inference
    panel = panel.set_index(["date", "ticker"]).sort_index()

    # Candidate features: numeric, not targets, not raw OHLCV
    num = panel.select_dtypes(include=[np.number])
    feat_cols = [c for c in num.columns
                 if not c.startswith("target_") and c not in _EXCLUDE]

    # Keep only dates with a wide-enough cross-section
    counts = panel.groupby(level="date").size()
    good_dates = counts[counts >= _MIN_NAMES].index
    panel = panel[panel.index.get_level_values("date").isin(good_dates)]

    # Cross-sectional z-score of each feature within each day
    g = panel.groupby(level="date")
    mean = g[feat_cols].transform("mean")
    std = g[feat_cols].transform("std")
    z = (panel[feat_cols] - mean) / std.replace(0.0, np.nan)

    # Drop features that are ~constant across the cross-section (macro/index/regime/
    # calendar): they carry no relative information and z-score to NaN.
    keep = [c for c in feat_cols if z[c].notna().mean() > 0.5]
    z = z[keep].replace([np.inf, -np.inf], np.nan).fillna(0.0)

    # Demeaned target = the cross-sectional alpha we actually want to predict
    # (triple-barrier touch return if requested, else fixed-horizon return)
    y = panel[demean_col] - g[demean_col].transform("mean")

    out = z.copy()
    out["y"] = y.values
    out[target_col] = panel[target_col].values
    if "tb_days" in panel.columns:
        out["tb_days"] = panel["tb_days"].values        # for sample-uniqueness weights
    logger.info(f"Panel[{horizon}]: {out.shape[0]} rows × {len(keep)} cross-sectional features "
                f"| {panel.index.get_level_values('date').nunique()} dates "
                f"| dropped {len(feat_cols) - len(keep)} market-wide features")
    return out, keep, target_col


# ── Train + evaluate ────────────────────────────────────────────────────────────

def train_cross_sectional(
    horizon: str = "5d",
    test_frac: float = 0.2,
    n_trials_for_dsr: int = 9,     # ~ (3 horizons × 3 model variants) tried overall
    save: bool = True,
) -> Dict:
    """
    Train one LightGBM ranker on the panel and evaluate it as a market-neutral
    long/short book with honest statistics.
    """
    logger.info("=" * 70)
    logger.info(f"CROSS-SECTIONAL MODEL | horizon={horizon}")
    logger.info("=" * 70)

    panel, feat_cols, target_col = build_panel(horizon)
    dates = panel.index.get_level_values("date")
    uniq = np.sort(dates.unique())
    split_date = uniq[int(len(uniq) * (1 - test_frac))]

    train = panel[dates <= split_date]
    test  = panel[dates >  split_date]
    logger.info(f"Train rows={len(train)} | Test rows={len(test)} | split={pd.Timestamp(split_date).date()}")

    X_tr, y_tr = train[feat_cols].values, train["y"].values
    X_te = test[feat_cols].values

    # Recency-weighted; shallow + regularized — one model over a big panel
    n = len(X_tr)
    weights = np.linspace(0.5, 1.0, n)
    dtrain = lgb.Dataset(X_tr, label=y_tr, weight=weights, feature_name=feat_cols)
    params = {
        "objective": "regression", "metric": "rmse", "verbosity": -1,
        "num_leaves": 63, "learning_rate": 0.02, "feature_fraction": 0.6,
        "bagging_fraction": 0.7, "bagging_freq": 5, "min_child_samples": 200,
        "reg_alpha": 0.5, "reg_lambda": 0.5, "max_depth": 6,
        "random_state": SEED, "n_jobs": -1,
    }
    model = lgb.train(params, dtrain, num_boost_round=600)

    test = test.copy()
    test["pred"] = model.predict(X_te)

    # ── Information Coefficient ──────────────────────────────────────────────
    test_dates = test.index.get_level_values("date")
    ic = information_coefficient(test["pred"], test["y"], test_dates)
    logger.info(f"IC: mean={ic['ic_mean']} IR={ic['ic_ir']} t={ic['ic_tstat']} "
                f"hit={ic['ic_hit']} over {ic['n_dates']} days")

    # ── Long/short quintile backtest (non-overlapping, realistic costs) ──────
    bt = _long_short_backtest(test, target_col, horizon, n_trials_for_dsr)

    results = {
        "horizon": horizon, "n_features": len(feat_cols),
        "n_train": len(train), "n_test": len(test),
        "ic": ic, "backtest": bt,
    }
    _print_summary(results)

    if save:
        path = CS_DIR / f"cs_model_{horizon}.txt"
        model.save_model(str(path))
        import json
        with open(CS_DIR / f"cs_results_{horizon}.json", "w") as f:
            json.dump(results, f, indent=2, default=str)
        logger.info(f"Saved cross-sectional model → {path}")

    return {**results, "model": model, "feature_cols": feat_cols}


def _long_short_backtest(test: pd.DataFrame, target_col: str, horizon: str,
                         n_trials: int, quantile: float = 0.2) -> Dict:
    """
    Rebalance every `horizon_days` (non-overlapping): long the top `quantile` by
    prediction, short the bottom, equal-weight, market-neutral. Charge realistic
    turnover costs. Report Sharpe + Deflated Sharpe.
    """
    horizon_days = HORIZONS.get(horizon, 5)
    dates = np.sort(test.index.get_level_values("date").unique())
    rebal = dates[::horizon_days]                       # non-overlapping holds

    ls_ret, gross_ret = [], []
    prev_long, prev_short = set(), set()
    for d in rebal:
        day = test.xs(d, level="date")
        if len(day) < _MIN_NAMES:
            continue
        day = day.sort_values("pred")
        k = max(1, int(len(day) * quantile))
        short, long = day.iloc[:k], day.iloc[-k:]

        gross = long[target_col].mean() - short[target_col].mean()    # market-neutral P&L
        long_s, short_s = set(long.index), set(short.index)
        # Turnover = fraction of each leg that changed since last rebalance
        turn = (len(long_s ^ prev_long) + len(short_s ^ prev_short)) / (2 * (2 * k))
        vol = float(day[target_col].std())
        cost = DEFAULT_COSTS.cost_fraction(turnover=turn, daily_vol=max(vol, 0.005))

        ls_ret.append(gross - cost)
        gross_ret.append(gross)
        prev_long, prev_short = long_s, short_s

    if len(ls_ret) < 8:
        return {"note": "insufficient rebalance periods"}

    ls = np.array(ls_ret)
    periods_per_year = 252 / horizon_days
    sr_period = ls.mean() / ls.std(ddof=1) if ls.std(ddof=1) > 0 else 0.0
    dsr = deflated_sharpe_ratio(ls, n_trials=n_trials)

    total = float(np.prod(1 + ls) - 1)
    ann = (1 + total) ** (periods_per_year / len(ls)) - 1
    eq = np.cumprod(1 + ls)
    maxdd = float(np.min(eq / np.maximum.accumulate(eq) - 1))

    return {
        "n_rebalances":     len(ls),
        "gross_mean_per_period": round(float(np.mean(gross_ret)), 5),
        "net_mean_per_period":   round(float(ls.mean()), 5),
        "sharpe_annual":    round(annualize_sharpe(sr_period, periods_per_year), 3),
        "annual_return":    round(float(ann), 4),
        "max_drawdown":     round(maxdd, 4),
        "win_rate":         round(float((ls > 0).mean()), 4),
        "deflated_sharpe":  dsr,
    }


def _print_summary(r: Dict) -> None:
    ic, bt = r["ic"], r["backtest"]
    logger.info(f"\n{'═'*70}\nCROSS-SECTIONAL RESULTS — {r['horizon']}\n{'═'*70}")
    logger.info(f"  IC mean {ic['ic_mean']} | IC-IR {ic['ic_ir']} | t-stat {ic['ic_tstat']} | hit {ic['ic_hit']}")
    if "sharpe_annual" in bt:
        d = bt["deflated_sharpe"]
        logger.info(f"  L/S Sharpe (annual, net of costs): {bt['sharpe_annual']}")
        logger.info(f"  L/S annual return: {bt['annual_return']:.1%} | maxDD {bt['max_drawdown']:.1%} | win {bt['win_rate']:.0%}")
        logger.info(f"  Deflated Sharpe (vs {bt['deflated_sharpe'].get('n_trials')} trials): "
                    f"DSR={d.get('dsr')} | PSR>0={d.get('psr_vs_0')}")
        logger.info(f"  → {'TRUSTWORTHY (DSR>0.95)' if (d.get('dsr') or 0) > 0.95 else 'NOT yet distinguishable from noise'}")
    logger.info("═"*70)


# ── Learning-to-rank + meta-labeling experiments ────────────────────────────────

def _sample_weights(df: pd.DataFrame) -> np.ndarray:
    """
    Combine RECENCY (recent data matters more) with SAMPLE UNIQUENESS (labels that
    resolved quickly overlap with fewer others → more independent info). Uniqueness
    ∝ 1 / triple-barrier holding period; falls back to recency-only if unavailable.
    Assumes `df` is sorted by date (as build_panel returns it).
    """
    n = len(df)
    recency = np.linspace(0.5, 1.0, n)
    if "tb_days" in df.columns:
        d = df["tb_days"].to_numpy(dtype=float)
        med = np.nanmedian(d[np.isfinite(d)]) if np.isfinite(d).any() else 1.0
        d = np.where(np.isfinite(d) & (d > 0), d, med)
        uniq = 1.0 / d
        uniq = uniq / uniq.mean()                     # normalize to mean 1
        return recency * uniq
    return recency


def _lgb_regression(X, y, feats, rounds=600, weight=None):
    w = weight if weight is not None else np.linspace(0.5, 1.0, len(X))
    params = {"objective": "regression", "metric": "rmse", "verbosity": -1,
              "num_leaves": 63, "learning_rate": 0.02, "feature_fraction": 0.6,
              "bagging_fraction": 0.7, "bagging_freq": 5, "min_child_samples": 200,
              "reg_alpha": 0.5, "reg_lambda": 0.5, "max_depth": 6,
              "random_state": SEED, "n_jobs": -1}
    return lgb.train(params, lgb.Dataset(X, label=y, weight=w, feature_name=feats), num_boost_round=rounds)


def _lgb_rank(train_df, feats, n_buckets=5, rounds=500, use_weights=True):
    """LightGBM LambdaRank: directly optimize the cross-sectional ordering."""
    dates = train_df.index.get_level_values("date")
    # Per-date relevance buckets (0..n-1) from the demeaned target
    def bucket(s):
        try:
            return pd.qcut(s.rank(method="first"), min(n_buckets, max(2, s.nunique())),
                           labels=False, duplicates="drop")
        except Exception:
            return pd.Series(0, index=s.index)
    labels = train_df["y"].groupby(dates).transform(bucket).fillna(0).astype(int)
    group = train_df.groupby(dates).size().values
    weight = _sample_weights(train_df) if use_weights else None
    params = {"objective": "lambdarank", "metric": "ndcg", "verbosity": -1,
              "num_leaves": 63, "learning_rate": 0.02, "feature_fraction": 0.6,
              "bagging_fraction": 0.7, "bagging_freq": 5, "min_child_samples": 200,
              "max_depth": 6, "random_state": SEED, "n_jobs": -1}
    dtrain = lgb.Dataset(train_df[feats].values, label=labels.values, group=group,
                         weight=weight, feature_name=feats)
    return lgb.train(params, dtrain, num_boost_round=rounds)


def _lgb_meta(train_meta_df, feats, rounds=300):
    """
    Meta-label model (López de Prado): predict whether the PRIMARY model's side is
    correct. Used to size bets — trade big when the meta-model is confident.
    Trained on a held-out slice so the primary predictions are out-of-sample.
    """
    side = np.sign(train_meta_df["pred"].values)
    correct = (np.sign(train_meta_df["y"].values) == side).astype(int)
    Xm = np.column_stack([train_meta_df[feats].values, train_meta_df["pred"].values])
    params = {"objective": "binary", "metric": "binary_logloss", "verbosity": -1,
              "num_leaves": 31, "learning_rate": 0.03, "min_child_samples": 200,
              "max_depth": 5, "random_state": SEED, "n_jobs": -1}
    return lgb.train(params, lgb.Dataset(Xm, label=correct), num_boost_round=rounds)


def _ls_meta_backtest(test, target_col, horizon, n_trials, quantile=0.2):
    """Long/short quintile, sized within each leg by meta-confidence."""
    horizon_days = HORIZONS.get(horizon, 5)
    dates = np.sort(test.index.get_level_values("date").unique())
    rebal = dates[::horizon_days]
    rets = []
    for d in rebal:
        day = test.xs(d, level="date")
        if len(day) < _MIN_NAMES:
            continue
        day = day.sort_values("pred")
        k = max(1, int(len(day) * quantile))
        short, long = day.iloc[:k], day.iloc[-k:]
        lw = long["meta"].clip(lower=0).values
        sw = short["meta"].clip(lower=0).values
        lw = lw / lw.sum() if lw.sum() > 0 else np.ones(k) / k
        sw = sw / sw.sum() if sw.sum() > 0 else np.ones(k) / k
        ret = (long[target_col].values * lw).sum() - (short[target_col].values * sw).sum()
        rets.append(ret)
    if len(rets) < 8:
        return {"note": "insufficient"}
    r = np.array(rets)
    ppy = 252 / horizon_days
    sr = r.mean() / r.std(ddof=1) if r.std(ddof=1) > 0 else 0.0
    return {"sharpe_annual": round(annualize_sharpe(sr, ppy), 3),
            "annual_return": round(float((1 + r).prod() ** (ppy / len(r)) - 1), 4),
            "win_rate": round(float((r > 0).mean()), 4),
            "deflated_sharpe": deflated_sharpe_ratio(r, n_trials=n_trials)}


def compare_models(horizon: str = "5d", n_trials: int = 9,
                   label: str = "fixed", add_factors: bool = True) -> Dict:
    """
    Bake-off on the same clean panel: regression vs learning-to-rank, plus
    meta-labeling on top. Reports IC + net-of-cost L/S Sharpe + Deflated Sharpe.
    """
    logger.info("=" * 70)
    logger.info(f"CROSS-SECTIONAL BAKE-OFF | horizon={horizon} | label={label} | factors={add_factors}")
    logger.info("=" * 70)
    panel, feats, tgt = build_panel(horizon, label=label, add_factors=add_factors)
    dates = panel.index.get_level_values("date")
    uniq = np.sort(dates.unique())
    # 3-way temporal split: primary-train | meta-train | test
    i1, i2 = int(len(uniq) * 0.6), int(len(uniq) * 0.8)
    d1, d2 = uniq[i1], uniq[i2]
    tr_p = panel[dates <= d1]
    tr_m = panel[(dates > d1) & (dates <= d2)]
    te = panel[dates > d2].copy()
    te_dates = te.index.get_level_values("date")

    out = {}

    # 1) Regression primary
    reg = _lgb_regression(tr_p[feats].values, tr_p["y"].values, feats)
    te["pred"] = reg.predict(te[feats].values)
    ic = information_coefficient(te["pred"], te["y"], te_dates)
    bt = _long_short_backtest(te, tgt, horizon, n_trials)
    out["regression"] = {"ic": ic, "bt": bt}
    logger.info(f"[regression] IC={ic['ic_mean']} t={ic['ic_tstat']} | Sharpe={bt.get('sharpe_annual')} DSR={bt['deflated_sharpe'].get('dsr')}")

    # 2) Learning-to-rank primary
    rk = _lgb_rank(tr_p, feats)
    te["pred"] = rk.predict(te[feats].values)
    ic_r = information_coefficient(te["pred"], te["y"], te_dates)
    bt_r = _long_short_backtest(te, tgt, horizon, n_trials)
    out["rank"] = {"ic": ic_r, "bt": bt_r}
    logger.info(f"[rank]       IC={ic_r['ic_mean']} t={ic_r['ic_tstat']} | Sharpe={bt_r.get('sharpe_annual')} DSR={bt_r['deflated_sharpe'].get('dsr')}")

    # 3) Meta-labeling on the better primary (use rank scores as the signal)
    tr_m = tr_m.copy()
    tr_m["pred"] = rk.predict(tr_m[feats].values)
    meta = _lgb_meta(tr_m, feats)
    te["pred"] = rk.predict(te[feats].values)
    te["meta"] = meta.predict(np.column_stack([te[feats].values, te["pred"].values]))
    bt_meta = _ls_meta_backtest(te, tgt, horizon, n_trials)
    out["rank+meta"] = {"bt": bt_meta}
    logger.info(f"[rank+meta]  Sharpe={bt_meta.get('sharpe_annual')} DSR={bt_meta['deflated_sharpe'].get('dsr')} win={bt_meta.get('win_rate')}")

    logger.info("=" * 70)
    return out


# ── Production: train, save, and generate live long/short signals ───────────────

def train_production(horizon: str = "5d", label: str = "triple_barrier",
                     add_factors: bool = True) -> Dict:
    """
    Train the deployable cross-sectional model (best config: rank primary +
    meta-labeling) and save it for the API. The meta model is trained on an
    out-of-sample slice; the final primary uses ALL history for the freshest scores.
    """
    import json
    logger.info(f"Training PRODUCTION cross-sectional model | horizon={horizon} | label={label}")
    panel, feats, tgt = build_panel(horizon, label=label, add_factors=add_factors)
    dates = panel.index.get_level_values("date")
    uniq = np.sort(dates.unique())
    d_meta = uniq[int(len(uniq) * 0.6)]

    # Primary on first 60% → OOS predictions on the rest → meta-label model
    prim_a = _lgb_rank(panel[dates <= d_meta], feats)
    tr_b = panel[dates > d_meta].copy()
    tr_b["pred"] = prim_a.predict(tr_b[feats].values)
    meta = _lgb_meta(tr_b, feats)

    # Final primary on ALL history (for live scoring)
    primary = _lgb_rank(panel, feats)

    primary.save_model(str(CS_DIR / f"prod_primary_{horizon}.txt"))
    meta.save_model(str(CS_DIR / f"prod_meta_{horizon}.txt"))
    with open(CS_DIR / f"prod_config_{horizon}.json", "w") as f:
        json.dump({"feats": feats, "label": label, "add_factors": add_factors, "horizon": horizon}, f)
    logger.info(f"Saved production cross-sectional model for {horizon} → {CS_DIR}")
    return {"primary": primary, "meta": meta, "feats": feats, "label": label, "add_factors": add_factors}


def load_production(horizon: str = "5d") -> Optional[Dict]:
    import json
    cfg = CS_DIR / f"prod_config_{horizon}.json"
    if not cfg.exists():
        return None
    with open(cfg) as f:
        c = json.load(f)
    c["primary"] = lgb.Booster(model_file=str(CS_DIR / f"prod_primary_{horizon}.txt"))
    c["meta"] = lgb.Booster(model_file=str(CS_DIR / f"prod_meta_{horizon}.txt"))
    return c


def generate_signals(horizon: str = "5d", all_features: Optional[Dict] = None,
                     prod: Optional[Dict] = None, top_q: float = 0.2) -> Dict:
    """
    Live long/short board for the most recent date: rank every stock by the
    cross-sectional model, return the top quintile (LONG) and bottom (SHORT) with
    rank score + meta confidence.
    """
    prod = prod or load_production(horizon)
    if prod is None:
        raise ValueError("No production cross-sectional model — run train_production() first")

    panel, _, _ = build_panel(horizon, all_features=all_features, label=prod["label"],
                              add_factors=prod["add_factors"], drop_target_na=False)
    feats = [f for f in prod["feats"] if f in panel.columns]
    last_date = panel.index.get_level_values("date").max()
    today = panel.xs(last_date, level="date")

    X = today[feats].values
    score = prod["primary"].predict(X)
    conf = prod["meta"].predict(np.column_stack([X, score]))
    df = pd.DataFrame({"ticker": list(today.index), "score": score, "confidence": conf}) \
        .sort_values("score", ascending=False).reset_index(drop=True)

    n = len(df)
    k = max(1, int(n * top_q))

    def fmt(rows, side):
        return [{"ticker": r["ticker"], "rank": i + 1, "side": side,
                 "score": round(float(r["score"]), 4),
                 "confidence": round(float(r["confidence"]), 4)}
                for i, (_, r) in enumerate(rows.iterrows())]

    return {
        "horizon": horizon,
        "as_of": str(pd.Timestamp(last_date).date()),
        "n_universe": n,
        "longs": fmt(df.head(k), "LONG"),
        "shorts": fmt(df.tail(k).iloc[::-1], "SHORT"),
    }


if __name__ == "__main__":
    import sys
    cmd = sys.argv[1] if len(sys.argv) > 1 else "train"
    hz = sys.argv[2] if len(sys.argv) > 2 else "5d"
    if cmd == "compare":
        compare_models(horizon=hz)
    elif cmd == "production":
        train_production(horizon=hz)
        sig = generate_signals(horizon=hz)
        print(f"Signals as of {sig['as_of']}: LONGS={[s['ticker'] for s in sig['longs']]}")
        print(f"SHORTS={[s['ticker'] for s in sig['shorts']]}")
    else:
        train_cross_sectional(horizon=hz)
