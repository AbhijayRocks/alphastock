"""
data_pipeline/ingestion.py — Pulls all raw data from free sources.

WHAT THIS DOES:
  1. Downloads 10 years of OHLCV data for all Nifty 50 stocks via yfinance
  2. Downloads macro indicators (USD/INR, crude, gold, VIX, US yields)
  3. Downloads Nifty index data (used as market-wide feature)
  4. Downloads fundamental data (P/E, EPS, D/E, market cap) via yfinance
  5. Saves everything as Parquet files (fast, compressed, typed)

WHY PARQUET (not CSV):
  Parquet is ~10x faster to read than CSV and preserves dtypes (dates stay
  dates, floats stay floats). Critical when you're loading 50 stocks x 10 years
  every time you train. Think of it as a lightweight database on disk.

ARCHITECTURE NOTE:
  This module only FETCHES raw data - no feature engineering here.
  Raw -> features/pipeline.py -> models/. Clean separation of concerns.
"""

import time
import logging
from datetime import date
from pathlib import Path
from typing import Dict, List, Optional

import pandas as pd
import numpy as np
import yfinance as yf

from config import (
    FEATURES_DIR, NIFTY_INDEX_TICKER,
    SENSEX_TICKER, MACRO_TICKERS, HISTORICAL_START,
    HISTORICAL_END, DATA_INTERVAL, LOG_LEVEL
)
from data_pipeline.nifty50 import get_all_tickers

logging.basicConfig(level=LOG_LEVEL, format="%(asctime)s | %(levelname)s | %(message)s")
logger = logging.getLogger(__name__)

RAW_DIR = FEATURES_DIR / "raw"
RAW_DIR.mkdir(parents=True, exist_ok=True)


def _flatten_columns(df: pd.DataFrame) -> pd.DataFrame:
    """
    Newer yfinance (0.2.40+) returns MultiIndex columns like ('Close', 'RELIANCE.NS').
    Flatten to just the price type in lowercase: 'close', 'open', 'high', etc.
    Safe to call on both old and new yfinance output.
    """
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = [col[0].lower() for col in df.columns]
    else:
        df.columns = [c.lower() for c in df.columns]
    return df


def _extract_close_series(raw: pd.DataFrame, ticker: str, ticker_list: List[str]) -> pd.Series:
    """
    Safely extract the Close price series from a yfinance download result.
    Handles single-ticker vs multi-ticker downloads and MultiIndex columns.
    """
    sub = raw if len(ticker_list) == 1 else raw[ticker]

    if isinstance(sub.columns, pd.MultiIndex):
        close_cols = [col for col in sub.columns if col[0] == "Close"]
        return sub[close_cols[0]].dropna() if close_cols else pd.Series(dtype=float)
    else:
        return sub["Close"].dropna() if "Close" in sub.columns else pd.Series(dtype=float)


# ── Price Data ─────────────────────────────────────────────────────────────────

def fetch_ohlcv(
    tickers: List[str],
    start: str = HISTORICAL_START,
    end: str = HISTORICAL_END,
    interval: str = DATA_INTERVAL,
) -> Dict[str, pd.DataFrame]:
    """
    Fetch OHLCV for a list of tickers in one batched API call.
    Returns dict of {ticker: DataFrame with lowercase columns [open,high,low,close,volume]}
    """
    logger.info(f"Fetching OHLCV for {len(tickers)} tickers from {start} to {end}")
    end_str = str(date.today()) if end == "today" else end

    raw = yf.download(
        tickers=tickers,
        start=start,
        end=end_str,
        interval=interval,
        auto_adjust=True,
        progress=False,
        threads=True,
        group_by="ticker",
    )

    result: Dict[str, pd.DataFrame] = {}

    for ticker in tickers:
        try:
            df = raw.copy() if len(tickers) == 1 else raw[ticker].copy()
            df = _flatten_columns(df)

            if "close" not in df.columns:
                logger.warning(f"{ticker}: no close column found, skipping")
                continue

            df = df.dropna(subset=["close"])

            if len(df) < 252:
                logger.warning(f"{ticker}: only {len(df)} rows, skipping (need 252+)")
                continue

            df.index.name = "date"
            df.index = pd.to_datetime(df.index)
            result[ticker] = df
            logger.debug(f"{ticker}: {len(df)} rows ({df.index[0].date()} to {df.index[-1].date()})")

        except Exception as e:
            logger.error(f"{ticker}: failed - {e}")
            continue

    logger.info(f"Successfully fetched {len(result)}/{len(tickers)} tickers")
    return result


def fetch_macro() -> pd.DataFrame:
    """
    Fetch macro-economic indicators as daily time series.
    USD/INR, Brent crude, gold, India VIX, US 10Y yield, DXY.
    All are freely available on Yahoo Finance.
    """
    logger.info("Fetching macro indicators...")
    end_str = str(date.today())
    ticker_list = list(MACRO_TICKERS.values())

    raw = yf.download(
        tickers=ticker_list,
        start=HISTORICAL_START,
        end=end_str,
        interval="1d",
        auto_adjust=True,
        progress=False,
        group_by="ticker",
    )

    macro_df = pd.DataFrame(index=pd.bdate_range(HISTORICAL_START, end_str))
    macro_df.index.name = "date"

    for name, ticker in MACRO_TICKERS.items():
        try:
            series = _extract_close_series(raw, ticker, ticker_list)
            series.name = name
            macro_df = macro_df.join(series, how="left")
        except Exception as e:
            logger.warning(f"Macro {name} ({ticker}): {e}")
            macro_df[name] = np.nan

    macro_df = macro_df.ffill().bfill()
    macro_df = macro_df.dropna(how="all")
    logger.info(f"Macro data: {macro_df.shape} | cols: {list(macro_df.columns)}")
    return macro_df


def fetch_nifty_index() -> pd.DataFrame:
    """
    Fetch Nifty 50 and Sensex index levels + returns.
    Index returns are one of the strongest predictors of individual stock moves.
    """
    logger.info("Fetching Nifty & Sensex index data...")
    end_str = str(date.today())
    ticker_list = [NIFTY_INDEX_TICKER, SENSEX_TICKER]

    raw = yf.download(
        tickers=ticker_list,
        start=HISTORICAL_START,
        end=end_str,
        interval="1d",
        auto_adjust=True,
        progress=False,
        group_by="ticker",
    )

    index_df = pd.DataFrame()
    for col_name, ticker in [("nifty50", NIFTY_INDEX_TICKER), ("sensex", SENSEX_TICKER)]:
        try:
            s = _extract_close_series(raw, ticker, ticker_list)
            s.name = col_name
            index_df = index_df.join(s, how="outer") if not index_df.empty else s.to_frame()
        except Exception as e:
            logger.warning(f"Index {ticker}: {e}")

    index_df.index = pd.to_datetime(index_df.index)
    index_df.index.name = "date"

    for col in index_df.columns:
        index_df[f"{col}_return_1d"] = index_df[col].pct_change(1)
        index_df[f"{col}_return_5d"] = index_df[col].pct_change(5)

    logger.info(f"Index data: {index_df.shape}")
    return index_df


def fetch_fundamentals(tickers: List[str]) -> pd.DataFrame:
    """
    Fetch point-in-time fundamental data via yfinance.
    P/E, P/B, D/E, ROE, ROA, growth rates, beta.
    Note: these are current values, not historical. Known limitation.
    """
    logger.info(f"Fetching fundamentals for {len(tickers)} stocks...")
    rows = []

    for ticker in tickers:
        try:
            info = yf.Ticker(ticker).info
            rows.append({
                "ticker":          ticker,
                "market_cap":      info.get("marketCap",           np.nan),
                "pe_ratio":        info.get("trailingPE",          np.nan),
                "forward_pe":      info.get("forwardPE",           np.nan),
                "pb_ratio":        info.get("priceToBook",         np.nan),
                "debt_to_equity":  info.get("debtToEquity",        np.nan),
                "roe":             info.get("returnOnEquity",      np.nan),
                "roa":             info.get("returnOnAssets",      np.nan),
                "revenue_growth":  info.get("revenueGrowth",       np.nan),
                "earnings_growth": info.get("earningsGrowth",      np.nan),
                "dividend_yield":  info.get("dividendYield",       np.nan),
                "beta":            info.get("beta",                np.nan),
                "52w_high":        info.get("fiftyTwoWeekHigh",    np.nan),
                "52w_low":         info.get("fiftyTwoWeekLow",     np.nan),
                "avg_volume_10d":  info.get("averageVolume10days", np.nan),
            })
            time.sleep(0.3)
        except Exception as e:
            logger.warning(f"{ticker} fundamentals failed: {e}")
            rows.append({"ticker": ticker})

    df = pd.DataFrame(rows).set_index("ticker")
    logger.info(f"Fundamentals fetched: {df.shape}")
    return df


# ── Persistence ────────────────────────────────────────────────────────────────

def save_ohlcv(ohlcv_dict: Dict[str, pd.DataFrame]) -> None:
    ohlcv_dir = RAW_DIR / "ohlcv"
    ohlcv_dir.mkdir(parents=True, exist_ok=True)
    for ticker, df in ohlcv_dict.items():
        safe_name = ticker.replace(".", "_").replace("&", "_").replace("^", "")
        df.to_parquet(ohlcv_dir / f"{safe_name}.parquet", engine="pyarrow", compression="snappy")
    logger.info(f"Saved {len(ohlcv_dict)} OHLCV files to {ohlcv_dir}")


def load_ohlcv(tickers: Optional[List[str]] = None) -> Dict[str, pd.DataFrame]:
    ohlcv_dir = RAW_DIR / "ohlcv"
    result = {}
    for f in ohlcv_dir.glob("*.parquet"):
        df = pd.read_parquet(f, engine="pyarrow")
        df.index = pd.to_datetime(df.index)
        result[f.stem] = df
    logger.info(f"Loaded {len(result)} OHLCV files from disk")
    return result


def save_dataframe(df: pd.DataFrame, name: str) -> Path:
    path = RAW_DIR / f"{name}.parquet"
    df.to_parquet(path, engine="pyarrow", compression="snappy")
    logger.info(f"Saved {name} -> {path} ({df.shape})")
    return path


def load_dataframe(name: str) -> pd.DataFrame:
    path = RAW_DIR / f"{name}.parquet"
    if not path.exists():
        raise FileNotFoundError(f"No cached data at {path}. Run ingestion first.")
    df = pd.read_parquet(path, engine="pyarrow")
    # Fundamentals index is ticker names (strings), not dates — skip conversion
    if name != "fundamentals":
        try:
            df.index = pd.to_datetime(df.index)
        except Exception:
            pass
    return df


# ── Main Pipeline ──────────────────────────────────────────────────────────────

def run_full_ingestion(tickers: Optional[List[str]] = None) -> Dict:
    """
    Run the complete data ingestion pipeline.
    Downloads everything and saves to disk. Run once, then use load functions.
    """
    if tickers is None:
        tickers = get_all_tickers()

    logger.info("=" * 60)
    logger.info("STARTING FULL DATA INGESTION")
    logger.info(f"Stocks: {len(tickers)} | Start: {HISTORICAL_START}")
    logger.info("=" * 60)

    results = {}

    ohlcv = fetch_ohlcv(tickers)
    save_ohlcv(ohlcv)
    results["ohlcv"] = ohlcv

    macro = fetch_macro()
    save_dataframe(macro, "macro")
    results["macro"] = macro

    index = fetch_nifty_index()
    save_dataframe(index, "nifty_index")
    results["index"] = index

    fundamentals = fetch_fundamentals(tickers)
    save_dataframe(fundamentals, "fundamentals")
    results["fundamentals"] = fundamentals

    logger.info("=" * 60)
    logger.info("INGESTION COMPLETE")
    logger.info(f"  Stocks fetched:   {len(ohlcv)}")
    logger.info(f"  Macro columns:    {macro.shape[1]}")
    logger.info(f"  Index columns:    {index.shape[1]}")
    logger.info(f"  Fundamental cols: {fundamentals.shape[1]}")
    logger.info(f"  Data saved to:    {RAW_DIR}")
    logger.info("=" * 60)

    return results


def run_incremental_update(tickers: Optional[List[str]] = None) -> None:
    """Fetch only last 7 days and append to existing Parquet files."""
    if tickers is None:
        tickers = get_all_tickers()

    start = (pd.Timestamp.today() - pd.Timedelta(days=7)).strftime("%Y-%m-%d")
    logger.info(f"Running incremental update from {start}...")

    ohlcv_new = fetch_ohlcv(tickers, start=start)
    ohlcv_dir = RAW_DIR / "ohlcv"

    for ticker, new_df in ohlcv_new.items():
        safe_name = ticker.replace(".", "_").replace("&", "_").replace("^", "")
        path = ohlcv_dir / f"{safe_name}.parquet"
        if path.exists():
            old_df = pd.read_parquet(path)
            combined = pd.concat([old_df, new_df])
            combined = combined[~combined.index.duplicated(keep="last")].sort_index()
            combined.to_parquet(path, engine="pyarrow", compression="snappy")
        else:
            new_df.to_parquet(path, engine="pyarrow", compression="snappy")

    logger.info(f"Incremental update done for {len(ohlcv_new)} stocks")


if __name__ == "__main__":
    data = run_full_ingestion()
    print(f"\nMacro tail:\n{data['macro'].tail()}")
