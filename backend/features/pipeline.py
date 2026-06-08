"""
features/pipeline.py — Master feature assembler.

THIS IS THE MOST IMPORTANT FILE IN THE PROJECT.

It takes all the raw ingredients and combines them into one clean, aligned,
ready-to-train DataFrame per stock. Everything the models see comes from here.

WHAT IT JOINS TOGETHER:
  1. Technical features      (150+ indicators from features/technical.py)
  2. Macro features          (USD/INR, crude, gold, VIX from ingestion.py)
  3. Market index features   (Nifty return, Sensex from ingestion.py)
  4. Regime labels           (bull/bear/sideways/crisis from features/regime.py)
  5. Sentiment features      (FinBERT news scores from news_sentiment.py)
  6. Fundamental features    (P/E, ROE etc. from ingestion.py)
  7. Cross-stock features    (sector avg return, sector momentum)
  8. Target columns          (what we're trying to predict: 1d/5d/20d returns)

OUTPUT PER STOCK:
  A DataFrame where:
    - Each row  = one trading day
    - Each col  = one feature (200+ total)
    - Last cols = target_1d, target_5d, target_20d (the labels)

WHY FUTURE RETURNS AS TARGETS (not prices):
  Predicting raw price (e.g. "RELIANCE will be at 2450") is hard because
  prices are non-stationary (they drift over time). Predicting returns
  (e.g. "RELIANCE will be up 2% in 5 days") is a stationary problem —
  much better behaved for ML. We can always convert back to price later.

DATA LEAKAGE PREVENTION:
  This is critical. Target_5d on day T must use the close price of day T+5,
  NOT any information from days T+1 to T+5. We use shift(-N) carefully and
  drop the last N rows where targets would be NaN (future data doesn't exist yet).
"""

import logging
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
from tqdm import tqdm

from config import (
    FEATURES_DIR, HORIZONS, SEQUENCE_LENGTH,
    MIN_HISTORY_DAYS, LOG_LEVEL
)
from data_pipeline.ingestion import load_ohlcv, load_dataframe
from data_pipeline.nifty50 import NIFTY50_META, get_sector_map
from data_pipeline.news_sentiment import load_sentiment, get_fallback_sentiment
from features.technical import compute_all_features
from features.regime import predict_regimes, load_regime_model, add_regime_features

logging.basicConfig(level=LOG_LEVEL, format="%(asctime)s | %(levelname)s | %(message)s")
logger = logging.getLogger(__name__)

PIPELINE_DIR = FEATURES_DIR / "pipeline"
PIPELINE_DIR.mkdir(parents=True, exist_ok=True)


# ── Target Creation ────────────────────────────────────────────────────────────

def add_targets(df: pd.DataFrame) -> pd.DataFrame:
    """
    Add prediction targets for all horizons.

    WHY FORWARD RETURNS (not prices):
      Returns are scale-invariant and stationary. A model trained on Reliance
      (price ~2000) generalizes to HDFC Bank (price ~1600) if both use returns.
      Price models don't generalize across stocks.

    target_1d  = return from today's close to tomorrow's close
    target_5d  = return from today's close to close 5 days from now
    target_20d = return from today's close to close 20 days from now

    CRITICAL: shift(-N) looks N rows into the future.
    The last N rows will have NaN targets — we drop them before training.
    This is correct and intentional, NOT a bug.
    """
    close = df["close"]

    for horizon_name, horizon_days in HORIZONS.items():
        # Forward return: (future_price - current_price) / current_price
        future_close = close.shift(-horizon_days)
        df[f"target_{horizon_name}"] = (future_close - close) / close

        # Also add direction target (up=1, down=0) for classification metrics
        df[f"target_{horizon_name}_direction"] = (df[f"target_{horizon_name}"] > 0).astype(float)

    return df


# ── GARCH Volatility Feature ────────────────────────────────────────────────────

def add_garch_features(df: pd.DataFrame, ticker: str = "") -> pd.DataFrame:
    """
    Add a GARCH(1,1) forward-looking conditional-volatility feature.

    All the existing vol features (hvol_*, atr_*, bb_width) are *realized* — they
    describe vol that already happened. GARCH gives the model a CONDITIONAL
    forecast of tomorrow's vol (volatility clustering + mean reversion), which is
    a genuinely predictable signal. We add two columns:

      garch_vol       : annualized GARCH conditional vol (same scale as hvol_*)
      garch_vol_ratio : GARCH forecast vs 20d realized vol — >1 means the model
                        expects vol to expand (often precedes large moves)

    Causal: sigma_t uses returns only up to t-1, so no look-ahead is introduced.
    """
    from features.garch import conditional_vol_daily

    try:
        log_ret = np.log(df["close"] / df["close"].shift(1))
        cond_vol = conditional_vol_daily(log_ret)          # daily, return units
        df["garch_vol"] = cond_vol * np.sqrt(252)          # annualize to match hvol_*
        if "hvol_20d" in df.columns:
            df["garch_vol_ratio"] = df["garch_vol"] / (df["hvol_20d"] + 1e-9)
    except Exception as e:
        logger.warning(f"{ticker}: GARCH feature failed ({e}) — skipping")

    return df


# ── Macro Feature Integration ──────────────────────────────────────────────────

def add_macro_features(df: pd.DataFrame, macro_df: pd.DataFrame) -> pd.DataFrame:
    """
    Join macro indicators onto the stock's feature DataFrame.

    We also compute macro changes (not just levels) because the *change*
    in crude oil price is more informative than the absolute level.

    Forward-fill to handle trading day mismatches between stock and macro data.
    """
    if macro_df.empty:
        logger.warning("Macro DataFrame is empty — skipping macro features")
        return df

    # Compute macro changes before joining
    macro_features = macro_df.copy()
    for col in macro_df.columns:
        macro_features[f"{col}_chg_1d"] = macro_df[col].pct_change(1)
        macro_features[f"{col}_chg_5d"] = macro_df[col].pct_change(5)

    # Join on date index, forward fill gaps
    df = df.join(macro_features, how="left", rsuffix="_macro")
    df[macro_features.columns] = df[macro_features.columns].ffill()

    return df


def add_index_features(df: pd.DataFrame, index_df: pd.DataFrame) -> pd.DataFrame:
    """
    Join Nifty index features onto the stock DataFrame.

    Key features added:
      - nifty50_return_1d: market return yesterday (strongest single predictor)
      - nifty50_return_5d: 5-day market momentum
      - stock_vs_nifty_1d: this stock's return vs market (alpha signal)
    """
    if index_df.empty:
        logger.warning("Index DataFrame is empty — skipping index features")
        return df

    df = df.join(index_df, how="left", rsuffix="_idx")
    df[index_df.columns] = df[index_df.columns].ffill()

    # Relative performance: stock vs market
    if "return_1d" in df.columns and "nifty50_return_1d" in df.columns:
        df["alpha_vs_nifty_1d"] = df["return_1d"] - df["nifty50_return_1d"]
    if "return_5d" in df.columns and "nifty50_return_5d" in df.columns:
        df["alpha_vs_nifty_5d"] = df["return_5d"] - df["nifty50_return_5d"]

    return df


# ── Sentiment Integration ──────────────────────────────────────────────────────

def add_sentiment_features(df: pd.DataFrame, ticker: str) -> pd.DataFrame:
    """
    Add news sentiment features.

    We use market-wide sentiment (always available) and stock-specific
    sentiment (when available — depends on NewsAPI quota).

    If no sentiment data exists, we use zeros (neutral) — the model
    learns that zero = no news = neutral, which is correct.
    """
    # Market-wide sentiment
    market_sent = load_sentiment("market_sentiment")
    if market_sent.empty:
        market_sent = get_fallback_sentiment(df.index)

    df = df.join(market_sent, how="left")
    df[market_sent.columns] = df[market_sent.columns].ffill().fillna(0)

    # Stock-specific sentiment
    safe_name = ticker.replace(".", "_")
    stock_sent = load_sentiment(f"{safe_name}_sentiment")
    if not stock_sent.empty:
        stock_sent.columns = [f"stock_sentiment_{c}" for c in stock_sent.columns]
        df = df.join(stock_sent, how="left")
        df[stock_sent.columns] = df[stock_sent.columns].ffill().fillna(0)
    else:
        df["stock_sentiment"] = 0.0

    return df


# ── Fundamental Integration ────────────────────────────────────────────────────

def add_fundamental_features(df: pd.DataFrame, ticker: str, fundamentals_df: pd.DataFrame) -> pd.DataFrame:
    """
    Add static fundamental features for this stock.

    Fundamentals are point-in-time (today's values broadcasted across all dates).
    This is a known simplification — in production you'd want historical fundamentals.
    """
    if fundamentals_df.empty or ticker not in fundamentals_df.index:
        return df

    fund_row = fundamentals_df.loc[ticker]
    for col, val in fund_row.items():
        if pd.notna(val):
            df[f"fund_{col}"] = float(val)

    return df


# ── Cross-Stock (Sector) Features ─────────────────────────────────────────────

def compute_sector_features(
    all_ohlcv: Dict[str, pd.DataFrame],
    sector_map: Dict[str, str],
) -> Dict[str, pd.DataFrame]:
    """
    Compute sector-level aggregated return features.

    WHY SECTOR FEATURES:
      If all banking stocks are falling but HDFC Bank is holding up,
      that relative strength is a powerful signal. The model needs to know
      what the sector is doing to interpret any individual stock's move.

    For each stock, we compute:
      - sector_return_1d  : average 1-day return of all OTHER stocks in same sector
      - sector_return_5d  : 5-day sector momentum
      - sector_strength   : this stock's return vs sector average (relative strength)

    Returns:
        dict of {ticker: DataFrame with sector features}
    """
    logger.info("Computing cross-stock sector features...")

    # Build dict of {sector: [tickers]}
    sector_to_tickers: Dict[str, List[str]] = {}
    for ticker, sector in sector_map.items():
        sector_to_tickers.setdefault(sector, []).append(ticker)

    # Compute daily close returns for all available stocks
    close_returns: Dict[str, pd.Series] = {}
    for ticker, df in all_ohlcv.items():
        # Match ticker to our naming (file stems use underscores)
        original_ticker = ticker.replace("_NS", ".NS").replace("M_M", "M&M")
        close_returns[original_ticker] = df["close"].pct_change(1)

    sector_features: Dict[str, pd.DataFrame] = {}

    for ticker in all_ohlcv.keys():
        original_ticker = ticker.replace("_NS", ".NS").replace("M_M", "M&M")
        sector = sector_map.get(original_ticker, "Unknown")
        sector_peers = sector_to_tickers.get(sector, [])

        # Peers = same sector but NOT this stock (exclude self)
        peer_returns = []
        for peer in sector_peers:
            if peer != original_ticker and peer in close_returns:
                peer_returns.append(close_returns[peer])

        if not peer_returns:
            sector_features[ticker] = pd.DataFrame()
            continue

        peers_df = pd.concat(peer_returns, axis=1)
        feat_df = pd.DataFrame(index=peers_df.index)
        feat_df["sector_return_1d"] = peers_df.mean(axis=1)
        feat_df["sector_return_5d"] = peers_df.mean(axis=1).rolling(5).mean()
        feat_df["sector_vol_20d"]   = peers_df.mean(axis=1).rolling(20).std()

        # Relative strength vs sector
        if original_ticker in close_returns:
            feat_df["sector_rel_strength_1d"] = (
                close_returns[original_ticker] - feat_df["sector_return_1d"]
            )

        sector_features[ticker] = feat_df

    return sector_features


# ── Master Pipeline ────────────────────────────────────────────────────────────

def build_features_for_stock(
    ticker: str,
    ohlcv_df: pd.DataFrame,
    macro_df: pd.DataFrame,
    index_df: pd.DataFrame,
    regime_series: pd.Series,
    fundamentals_df: pd.DataFrame,
    sector_feat_df: Optional[pd.DataFrame] = None,
    add_sentiment: bool = True,
) -> pd.DataFrame:
    """
    Build the complete feature set for a single stock.

    This is the core function — called once per stock per training run.

    Steps:
      1. Compute 150+ technical features from OHLCV
      2. Add macro features (USD/INR, crude, etc.)
      3. Add market index features (Nifty returns)
      4. Add regime labels (bull/bear/sideways/crisis)
      5. Add sentiment scores (FinBERT news)
      6. Add fundamental ratios (P/E, ROE etc.)
      7. Add sector relative features
      8. Add prediction targets (1d/5d/20d forward returns)
      9. Clean up: remove NaN rows, verify no data leakage

    Args:
        ticker        : e.g. "RELIANCE.NS"
        ohlcv_df      : raw OHLCV DataFrame for this stock
        macro_df      : macro indicators DataFrame
        index_df      : Nifty/Sensex index DataFrame
        regime_series : market regime labels (from fit_regime_model)
        fundamentals_df: fundamental ratios for all stocks
        sector_feat_df: sector average features for this stock
        add_sentiment : whether to add FinBERT sentiment (False = faster)

    Returns:
        DataFrame ready for model training
    """
    logger.info(f"Building features for {ticker}...")

    if len(ohlcv_df) < MIN_HISTORY_DAYS:
        raise ValueError(f"{ticker}: insufficient history ({len(ohlcv_df)} days)")

    # Step 1: Technical features
    df = compute_all_features(ohlcv_df.copy(), ticker=ticker)

    # Step 1b: GARCH(1,1) forward-looking volatility (vs the realized vol above)
    df = add_garch_features(df, ticker=ticker)

    # Step 2: Macro
    df = add_macro_features(df, macro_df)

    # Step 3: Market index
    df = add_index_features(df, index_df)

    # Step 4: Regime
    if regime_series is not None and not regime_series.empty:
       df = add_regime_features(df, regime_series)
    else:
      # No regime data — add neutral defaults so downstream code doesn't break
        df["regime_bull"]     = 0.0
        df["regime_bear"]     = 0.0
        df["regime_sideways"] = 0.0
        df["regime_crisis"]   = 0.0
        df["regime_change"]   = 0.0
        df["regime_duration"] = 1.0

    # Step 5: Sentiment
    if add_sentiment:
        df = add_sentiment_features(df, ticker)

    # Step 6: Fundamentals
    df = add_fundamental_features(df, ticker, fundamentals_df)

    # Step 7: Sector features
    if sector_feat_df is not None and not sector_feat_df.empty:
        df = df.join(sector_feat_df, how="left", rsuffix="_sector")
        sector_cols = sector_feat_df.columns.tolist()
        df[sector_cols] = df[sector_cols].ffill()

    # Step 8: Add targets LAST — after all features are computed
    df = add_targets(df)

    # Step 9: Clean up
    # Drop the regime string column — models need numbers, not strings
    if "regime" in df.columns:
        df = df.drop(columns=["regime"])

    # Remove rows with all-NaN features (typically first 200 rows due to long lookbacks)
    feature_cols = [c for c in df.columns if not c.startswith("target_")]
    df = df.dropna(subset=feature_cols, how="all")

    # Replace any remaining inf values
    df = df.replace([np.inf, -np.inf], np.nan)

    # Fill remaining NaNs with column median (not mean — more robust to outliers)
    for col in df.select_dtypes(include=[np.number]).columns:
        if df[col].isna().any():
            df[col] = df[col].fillna(df[col].median())

    n_features = len([c for c in df.columns if not c.startswith("target_")])
    logger.info(f"{ticker}: {len(df)} rows x {n_features} features | "
                f"targets: {[c for c in df.columns if c.startswith('target_')]}")

    return df


def build_all_features(
    tickers: Optional[List[str]] = None,
    add_sentiment: bool = True,
    save: bool = True,
) -> Dict[str, pd.DataFrame]:
    """
    Build features for all stocks and optionally save to Parquet.

    This is the main entry point — run this before training.
    Takes ~5-10 minutes for all 50 stocks.

    Usage:
        from features.pipeline import build_all_features
        all_features = build_all_features()
        # Then: all_features["RELIANCE_NS"] is a ready-to-train DataFrame
    """
    logger.info("=" * 60)
    logger.info("BUILDING FEATURES FOR ALL STOCKS")
    logger.info("=" * 60)

    # Load all raw data from disk
    logger.info("Loading raw data from disk...")
    all_ohlcv      = load_ohlcv()
    macro_df       = _safe_load("macro")
    index_df       = _safe_load("nifty_index")
    fundamentals_df= _safe_load("fundamentals")

    if tickers is None:
        tickers = list(all_ohlcv.keys())

    # Fit regime model on index data
    logger.info("Fitting regime model on Nifty index...")
    regime_series = _get_regime_series(index_df)

    # Compute sector features (cross-stock — done once for all)
    sector_map      = get_sector_map()
    sector_features = compute_sector_features(all_ohlcv, sector_map)

    # Build features for each stock
    results: Dict[str, pd.DataFrame] = {}
    failed: List[str] = []

    for ticker in tqdm(tickers, desc="Building features"):
        if ticker not in all_ohlcv:
            logger.warning(f"{ticker} not in OHLCV data, skipping")
            continue

        try:
            feat_df = build_features_for_stock(
                ticker          = ticker,
                ohlcv_df        = all_ohlcv[ticker],
                macro_df        = macro_df,
                index_df        = index_df,
                regime_series   = regime_series,
                fundamentals_df = fundamentals_df,
                sector_feat_df  = sector_features.get(ticker),
                add_sentiment   = add_sentiment,
            )

            results[ticker] = feat_df

            if save:
                path = PIPELINE_DIR / f"{ticker}.parquet"
                feat_df.to_parquet(path, engine="pyarrow", compression="snappy")

        except Exception as e:
            logger.error(f"{ticker}: feature build failed — {e}")
            failed.append(ticker)
            continue

    logger.info("=" * 60)
    logger.info(f"Feature build complete: {len(results)} stocks")
    if failed:
        logger.warning(f"Failed: {failed}")
    if results:
        sample = next(iter(results.values()))
        logger.info(f"Sample shape: {sample.shape}")
        logger.info(f"Feature cols: {len([c for c in sample.columns if not c.startswith('target_')])}")
    logger.info("=" * 60)

    return results


def load_features(ticker: str) -> pd.DataFrame:
    """Load pre-built features for one stock from disk."""
    safe_ticker = ticker.replace(".", "_")
    path = PIPELINE_DIR / f"{safe_ticker}.parquet"
    if not path.exists():
        raise FileNotFoundError(
            f"No features found for {ticker} (looked for {path}). Run build_all_features() first."
        )
    df = pd.read_parquet(path, engine="pyarrow")
    df.index = pd.to_datetime(df.index)
    return df


def load_all_features(tickers: Optional[List[str]] = None) -> Dict[str, pd.DataFrame]:
    """Load all pre-built feature files from disk."""
    files = list(PIPELINE_DIR.glob("*.parquet"))
    result = {}
    for f in files:
        if tickers and f.stem not in tickers:
            continue
        df = pd.read_parquet(f, engine="pyarrow")
        df.index = pd.to_datetime(df.index)
        result[f.stem] = df
    logger.info(f"Loaded features for {len(result)} stocks")
    return result


# ── Helpers ────────────────────────────────────────────────────────────────────

def _safe_load(name: str) -> pd.DataFrame:
    """Load a DataFrame from disk, returning empty DataFrame on failure."""
    try:
        return load_dataframe(name)
    except FileNotFoundError:
        logger.warning(f"{name} not found on disk — returning empty DataFrame")
        return pd.DataFrame()


def _get_regime_series(index_df: pd.DataFrame) -> pd.Series:
    """
    Get regime labels, fitting the model if needed.
    Returns a neutral series if index data is unavailable.
    """
    if index_df.empty:
        logger.warning("No index data — using neutral regime for all dates")
        return pd.Series(dtype=str)

    try:
        from features.regime import fit_regime_model, predict_regimes, REGIME_MODEL_PATH
        if not REGIME_MODEL_PATH.exists():
            logger.info("Regime model not found — fitting now...")
            fit_regime_model(index_df)
        return predict_regimes(index_df)
    except Exception as e:
        logger.warning(f"Regime detection failed: {e} — using neutral regime")
        return pd.Series("bull", index=index_df.index, name="regime")


def get_train_test_split(
    df: pd.DataFrame,
    test_ratio: float = 0.15,
    val_ratio: float = 0.15,
    horizon: str = "1d",
) -> Tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """
    Time-aware train/val/test split.

    CRITICAL RULE: Never use random splits for time series.
    Always use the last N% of time as test, the N% before that as val.
    This prevents data leakage from future to past.

    Layout: |----train----|--val--|--test--|
            0%           70%     85%     100%

    Also drops rows where the target is NaN (last N rows for each horizon).
    """
    target_col = f"target_{horizon}"
    if target_col not in df.columns:
        raise ValueError(f"Target column {target_col} not found")

    # Drop rows where target is NaN (the trailing rows for each horizon)
    df_clean = df.dropna(subset=[target_col])

    n = len(df_clean)
    test_start = int(n * (1 - test_ratio))
    val_start  = int(n * (1 - test_ratio - val_ratio))

    train = df_clean.iloc[:val_start]
    val   = df_clean.iloc[val_start:test_start]
    test  = df_clean.iloc[test_start:]

    logger.info(f"Split for horizon={horizon}: "
                f"train={len(train)}, val={len(val)}, test={len(test)}")

    return train, val, test


if __name__ == "__main__":
    # Build features for just one stock as a quick test
    import yfinance as yf
    from data_pipeline.ingestion import load_ohlcv

    logger.info("Quick test: building features for RELIANCE.NS")

    all_ohlcv = load_ohlcv()
    reliance_key = "RELIANCE_NS"

    if reliance_key not in all_ohlcv:
        print(f"Keys available: {list(all_ohlcv.keys())[:5]}")
    else:
        df = build_features_for_stock(
            ticker          = "RELIANCE.NS",
            ohlcv_df        = all_ohlcv[reliance_key],
            macro_df        = _safe_load("macro"),
            index_df        = _safe_load("nifty_index"),
            regime_series   = pd.Series(dtype=str),
            fundamentals_df = _safe_load("fundamentals"),
            add_sentiment   = False,   # skip sentiment for quick test
        )

        print(f"\nShape: {df.shape}")
        print(f"Feature count: {len([c for c in df.columns if not c.startswith('target_')])}")
        print(f"Target cols: {[c for c in df.columns if c.startswith('target_')]}")
        print(f"\nSample targets:\n{df[[c for c in df.columns if c.startswith('target_')]].tail()}")
