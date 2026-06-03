"""
features/technical.py — Compute 100+ technical indicators for one stock.

WHY SO MANY FEATURES?
  Not all features will be useful for every stock or every market regime.
  We generate everything here and let the model (or feature selection) decide
  what's useful. XGBoost/LightGBM with SHAP will tell us which ones actually
  matter — you'll see this in the dashboard.

GROUPS OF FEATURES WE CREATE:
  1. Returns & price relatives   — how much did price move, vs what?
  2. Trend indicators            — is price trending up/down/flat?
  3. Momentum indicators         — is momentum accelerating or decelerating?
  4. Volatility indicators       — how wild is price swinging?
  5. Volume indicators           — is the move backed by conviction (volume)?
  6. Support/Resistance levels   — where are the key price levels?
  7. Calendar features           — day of week, month-end effects, etc.

WHY pandas-ta INSTEAD OF TA-Lib?
  TA-Lib requires C compilation which breaks on Windows constantly.
  pandas-ta is pure Python, pip install just works, covers 130+ indicators.
"""

import logging
from typing import Optional

import numpy as np
import pandas as pd
import pandas_ta as ta   # pip install pandas-ta

logger = logging.getLogger(__name__)


def add_return_features(df: pd.DataFrame) -> pd.DataFrame:
    """
    Price returns over multiple horizons.

    WHY: Past returns are the most predictive raw signal for future returns.
    We look at multiple horizons because short-term momentum (1-5d) and
    medium-term momentum (20-60d) can point in different directions.
    """
    close = df["close"]

    for n in [1, 2, 3, 5, 10, 20, 60]:
        df[f"return_{n}d"]     = close.pct_change(n)           # simple return
        df[f"log_return_{n}d"] = np.log(close / close.shift(n))# log return (better for stats)

    # Return relative to high and low (where in the daily range did we close?)
    df["close_vs_high"]  = (df["close"] - df["high"]) / (df["high"] - df["low"] + 1e-9)
    df["close_vs_low"]   = (df["close"] - df["low"])  / (df["high"] - df["low"] + 1e-9)
    df["daily_range_pct"]= (df["high"] - df["low"]) / df["close"]   # normalized range

    # Gap — how much did price jump at open vs yesterday's close?
    df["overnight_gap"]  = (df["open"] - df["close"].shift(1)) / df["close"].shift(1)

    return df


def add_trend_features(df: pd.DataFrame) -> pd.DataFrame:
    """
    Trend-following indicators — detect if price is in an uptrend or downtrend.

    SMA/EMA: Smoothed averages. Price above SMA = bullish bias.
    MACD: Difference between fast and slow EMAs. Crossovers = trend change.
    ADX: Measures trend *strength* (not direction). ADX > 25 = strong trend.
    Ichimoku: Japanese system; Kumo (cloud) acts as dynamic support/resistance.
    """
    close = df["close"]
    high  = df["high"]
    low   = df["low"]

    # Simple and Exponential Moving Averages
    for n in [5, 10, 20, 50, 100, 200]:
        df[f"sma_{n}"]   = ta.sma(close, length=n)
        df[f"ema_{n}"]   = ta.ema(close, length=n)
        # Price relative to moving average (normalize so it's scale-invariant)
        df[f"price_vs_sma_{n}"] = (close - df[f"sma_{n}"]) / df[f"sma_{n}"]
        df[f"price_vs_ema_{n}"] = (close - df[f"ema_{n}"]) / df[f"ema_{n}"]

    # MA crossovers (golden cross / death cross signals)
    df["ma_cross_5_20"]   = df["ema_5"]  - df["ema_20"]
    df["ma_cross_20_50"]  = df["ema_20"] - df["ema_50"]
    df["ma_cross_50_200"] = df["sma_50"] - df["sma_200"]

    # MACD (Moving Average Convergence Divergence)
    macd = ta.macd(close, fast=12, slow=26, signal=9)
    if macd is not None:
        df["macd"]         = macd["MACD_12_26_9"]
        df["macd_signal"]  = macd["MACDs_12_26_9"]
        df["macd_hist"]    = macd["MACDh_12_26_9"]
        df["macd_cross"]   = df["macd"] - df["macd_signal"]

    # ADX (Average Directional Index) — trend strength
    adx = ta.adx(high, low, close, length=14)
    if adx is not None:
        df["adx"]    = adx["ADX_14"]
        df["dmp"]    = adx["DMP_14"]    # +DI: up move strength
        df["dmn"]    = adx["DMN_14"]    # -DI: down move strength
        df["di_diff"]= df["dmp"] - df["dmn"]

    # Parabolic SAR — trend reversal signal
    psar = ta.psar(high, low, close)
    if psar is not None and "PSARl_0.02_0.2" in psar.columns:
        df["psar_bull"] = psar["PSARl_0.02_0.2"].notna().astype(float)

    # Ichimoku Cloud
    ichimoku = ta.ichimoku(high, low, close)
    if ichimoku is not None and len(ichimoku) == 2:
        ichi_df = ichimoku[0]
        for col in ichi_df.columns:
            short_name = col.split("_")[0].lower()
            df[f"ichi_{short_name}"] = ichi_df[col]

    return df


def add_momentum_features(df: pd.DataFrame) -> pd.DataFrame:
    """
    Momentum indicators — overbought/oversold and momentum acceleration.

    RSI: 0-100 oscillator. <30 = oversold (buy signal), >70 = overbought (sell).
    Stochastic: similar to RSI but uses range instead of change.
    ROC: Rate of change — pure momentum over N periods.
    Williams %R: Shows where close sits in the N-period high-low range.
    """
    close = df["close"]
    high  = df["high"]
    low   = df["low"]

    # RSI at multiple timeframes
    for n in [7, 14, 21]:
        df[f"rsi_{n}"] = ta.rsi(close, length=n)

    # RSI divergence (RSI slope vs price slope — powerful reversal signal)
    df["rsi_14_slope"] = df["rsi_14"].diff(3)
    df["price_slope_3d"]= close.pct_change(3)

    # Stochastic Oscillator
    stoch = ta.stoch(high, low, close, k=14, d=3)
    if stoch is not None:
        df["stoch_k"] = stoch["STOCHk_14_3_3"]
        df["stoch_d"] = stoch["STOCHd_14_3_3"]
        df["stoch_cross"] = df["stoch_k"] - df["stoch_d"]

    # Stochastic RSI (more sensitive than regular RSI)
    stochrsi = ta.stochrsi(close, length=14)
    if stochrsi is not None:
        df["stochrsi_k"] = stochrsi["STOCHRSIk_14_14_3_3"]
        df["stochrsi_d"] = stochrsi["STOCHRSId_14_14_3_3"]

    # Rate of Change
    for n in [5, 10, 20]:
        df[f"roc_{n}"] = ta.roc(close, length=n)

    # Williams %R
    df["willr_14"] = ta.willr(high, low, close, length=14)

    # Commodity Channel Index (CCI)
    df["cci_20"] = ta.cci(high, low, close, length=20)

    # Ultimate Oscillator (combines 3 timeframes of buying pressure)
    df["uo"] = ta.uo(high, low, close)

    # PPO — Percentage Price Oscillator (like MACD but in %)
    ppo = ta.ppo(close)
    if ppo is not None and "PPO_12_26_9" in ppo.columns:
        df["ppo"] = ppo["PPO_12_26_9"]

    return df


def add_volatility_features(df: pd.DataFrame) -> pd.DataFrame:
    """
    Volatility indicators — how much is price swinging?

    HIGH VOLATILITY MATTERS FOR 2 REASONS:
    1. Wider prediction intervals needed when vol is high
    2. Volatility itself is often predictable (vol clusters) — GARCH-like features

    Bollinger Bands: price ± 2 standard deviations. Squeeze = breakout coming.
    ATR: Average True Range — raw measure of daily price swing.
    Keltner: Like Bollinger but uses ATR instead of std. BB breakout through
             Keltner = very strong momentum signal.
    """
    close = df["close"]
    high  = df["high"]
    low   = df["low"]

    # Bollinger Bands
    for n in [10, 20]:
        bbands = ta.bbands(close, length=n, std=2)
        if bbands is not None:
            lower_col = [c for c in bbands.columns if c.startswith("BBL")]
            mid_col   = [c for c in bbands.columns if c.startswith("BBM")]
            upper_col = [c for c in bbands.columns if c.startswith("BBU")]
            bw_col    = [c for c in bbands.columns if c.startswith("BBB")]
            if lower_col and mid_col and upper_col:
                df[f"bb_lower_{n}"] = bbands[lower_col[0]]
                df[f"bb_mid_{n}"]   = bbands[mid_col[0]]
                df[f"bb_upper_{n}"] = bbands[upper_col[0]]
                df[f"bb_width_{n}"] = bbands[bw_col[0]] if bw_col else np.nan
                # Where is price within the band? 0 = at lower, 1 = at upper
                df[f"bb_pct_{n}"]   = (close - df[f"bb_lower_{n}"]) / \
                                      (df[f"bb_upper_{n}"] - df[f"bb_lower_{n}"] + 1e-9)

    # ATR (Average True Range) — normalized by close for scale-invariance
    for n in [7, 14, 21]:
        atr = ta.atr(high, low, close, length=n)
        if atr is not None:
            df[f"atr_{n}"]     = atr
            df[f"atr_{n}_pct"] = atr / close    # normalized ATR

    # Historical Volatility (realized vol — rolling std of log returns)
    log_ret = np.log(close / close.shift(1))
    for n in [5, 10, 20, 60]:
        df[f"hvol_{n}d"] = log_ret.rolling(n).std() * np.sqrt(252)  # annualized

    # Volatility ratio (short-term vol / long-term vol — detects vol spikes)
    df["vol_ratio_5_20"]  = df["hvol_5d"]  / (df["hvol_20d"] + 1e-9)
    df["vol_ratio_10_60"] = df["hvol_10d"] / (df["hvol_60d"] + 1e-9)

    # Keltner Channel
    kc = ta.kc(high, low, close)
    if kc is not None:
        kc_lower = [c for c in kc.columns if "L" in c]
        kc_upper = [c for c in kc.columns if "U" in c]
        if kc_lower and kc_upper:
            df["kc_lower"] = kc[kc_lower[0]]
            df["kc_upper"] = kc[kc_upper[0]]
            # BB breakout through Keltner = squeeze breakout
            df["bb_kc_squeeze"] = (df["bb_lower_20"] > df["kc_lower"]).astype(float)

    # True Range (single day measure of volatility)
    df["true_range"] = ta.true_range(high, low, close)

    return df


def add_volume_features(df: pd.DataFrame) -> pd.DataFrame:
    """
    Volume-based indicators — confirms if a price move has conviction.

    KEY INSIGHT: A price breakout with HIGH volume = real move.
                 A price breakout with LOW volume = likely fake-out.

    OBV: Accumulates volume on up-days, subtracts on down-days.
         Rising OBV + rising price = confirmed uptrend.
         Rising price + falling OBV = divergence (warning signal).
    VWAP: Average price weighted by volume. Institutions use this as benchmark.
    """
    close  = df["close"]
    high   = df["high"]
    low    = df["low"]
    volume = df["volume"]

    # Relative volume (today's volume vs average — spikes = news/event)
    for n in [5, 10, 20]:
        df[f"rvol_{n}d"] = volume / (volume.rolling(n).mean() + 1e-9)

    # Volume trend
    df["vol_change_1d"] = volume.pct_change(1)
    df["vol_change_5d"] = volume.pct_change(5)
    df["vol_sma_10"]    = volume.rolling(10).mean()

    # On-Balance Volume
    obv = ta.obv(close, volume)
    if obv is not None:
        df["obv"]         = obv
        df["obv_sma_20"]  = obv.rolling(20).mean()
        df["obv_vs_sma"]  = (obv - df["obv_sma_20"]) / (df["obv_sma_20"].abs() + 1e-9)

    # Volume-Price Trend
    df["vpt"] = (volume * close.pct_change()).cumsum()

    # Chaikin Money Flow (CMF) — buying vs selling pressure
    mfv = ((close - low) - (high - close)) / (high - low + 1e-9) * volume
    df["cmf_20"] = mfv.rolling(20).sum() / (volume.rolling(20).sum() + 1e-9)

    # VWAP (rolling 20-day — true intraday VWAP needs tick data)
    typical_price = (high + low + close) / 3
    df["vwap_20"] = (typical_price * volume).rolling(20).sum() / \
                    (volume.rolling(20).sum() + 1e-9)
    df["price_vs_vwap"] = (close - df["vwap_20"]) / df["vwap_20"]

    # Money Flow Index (volume-weighted RSI)
    df["mfi_14"] = ta.mfi(high, low, close, volume, length=14)

    # Ease of Movement (EOM) — large EOM = price moving easily on low volume
    df["eom_14"] = ta.eom(high, low, close, volume, length=14)

    return df


def add_support_resistance_features(df: pd.DataFrame) -> pd.DataFrame:
    """
    Support and resistance level features.

    INTUITION: Markets have memory. Prices tend to reverse at levels where
    they've reversed before. These features tell the model how close price
    is to historically significant levels.
    """
    close = df["close"]
    high  = df["high"]
    low   = df["low"]

    # Rolling highs and lows (natural support/resistance)
    for n in [20, 52]:
        df[f"roll_high_{n}w"] = high.rolling(n * 5).max()   # N weeks in trading days
        df[f"roll_low_{n}w"]  = low.rolling(n * 5).min()
        df[f"pct_from_high_{n}w"] = (close - df[f"roll_high_{n}w"]) / df[f"roll_high_{n}w"]
        df[f"pct_from_low_{n}w"]  = (close - df[f"roll_low_{n}w"])  / df[f"roll_low_{n}w"]

    # 52-week high/low proximity (widely watched by Indian retail investors)
    df["pct_from_52w_high"] = (close - high.rolling(252).max()) / high.rolling(252).max()
    df["pct_from_52w_low"]  = (close - low.rolling(252).min())  / low.rolling(252).min()

    # Pivot points (classic floor trader levels)
    df["pivot"]      = (high.shift(1) + low.shift(1) + close.shift(1)) / 3
    df["r1"]         = 2 * df["pivot"] - low.shift(1)
    df["s1"]         = 2 * df["pivot"] - high.shift(1)
    df["price_vs_pivot"] = (close - df["pivot"]) / df["pivot"]

    # Donchian Channel
    for n in [20, 55]:
        df[f"don_upper_{n}"] = high.rolling(n).max()
        df[f"don_lower_{n}"] = low.rolling(n).min()
        df[f"don_pct_{n}"]   = (close - df[f"don_lower_{n}"]) / \
                               (df[f"don_upper_{n}"] - df[f"don_lower_{n}"] + 1e-9)

    return df


def add_calendar_features(df: pd.DataFrame) -> pd.DataFrame:
    """
    Calendar/seasonality features.

    WHY: Indian markets have well-documented seasonality:
    - Expiry weeks (every last Thursday of month) see vol spike
    - Budget day (Feb 1) causes massive moves
    - FII selling in March (tax year end) is consistent
    - Monday returns differ from Friday returns
    """
    idx = df.index

    df["day_of_week"]     = idx.dayofweek              # 0=Mon, 4=Fri
    df["month"]           = idx.month
    df["quarter"]         = idx.quarter
    df["is_month_start"]  = idx.is_month_start.astype(float)
    df["is_month_end"]    = idx.is_month_end.astype(float)
    df["is_quarter_end"]  = idx.is_quarter_end.astype(float)

    # F&O expiry week — last Thursday of month (very important for Indian markets!)
    # Approximate: trading days 18-22 of month are typically expiry week
    df["is_expiry_week"]  = (
        (idx.day >= 18) & (idx.day <= 22) & (idx.dayofweek == 3)
    ).astype(float)

    # Sine/cosine encoding of cyclical features (better than raw integer for ML)
    df["dow_sin"]   = np.sin(2 * np.pi * df["day_of_week"] / 5)
    df["dow_cos"]   = np.cos(2 * np.pi * df["day_of_week"] / 5)
    df["month_sin"] = np.sin(2 * np.pi * df["month"] / 12)
    df["month_cos"] = np.cos(2 * np.pi * df["month"] / 12)

    return df


def compute_all_features(df: pd.DataFrame, ticker: str = "") -> pd.DataFrame:
    """
    Master function — runs all feature groups on a single stock's OHLCV DataFrame.

    INPUT:  DataFrame with columns [open, high, low, close, volume], DatetimeIndex
    OUTPUT: DataFrame with 150+ feature columns added

    The feature computation order matters — some features depend on others
    (e.g. support/resistance uses SMA columns computed in trend features).
    """
    logger.info(f"Computing features for {ticker or 'stock'} ({len(df)} rows)")

    if len(df) < 252:
        logger.warning(f"{ticker}: insufficient history ({len(df)} rows), some features will be NaN")

    original_len = len(df)

    df = add_return_features(df)
    df = add_trend_features(df)
    df = add_momentum_features(df)
    df = add_volatility_features(df)
    df = add_volume_features(df)
    df = add_support_resistance_features(df)
    df = add_calendar_features(df)

    # Remove infinite values that can appear in ratio calculations
    df = df.replace([np.inf, -np.inf], np.nan)

    # Count how many features we generated
    feature_cols = [c for c in df.columns if c not in ["open", "high", "low", "close", "volume"]]
    logger.info(f"{ticker}: generated {len(feature_cols)} technical features | "
                f"NaN rate: {df[feature_cols].isna().mean().mean():.1%}")

    assert len(df) == original_len, "Feature computation changed DataFrame length!"

    return df


if __name__ == "__main__":
    # Quick test — generates features for a single stock
    import yfinance as yf
    raw = yf.download("RELIANCE.NS", start="2020-01-01", auto_adjust=True, progress=False)
    raw.columns = [c.lower() for c in raw.columns]
    raw.index.name = "date"

    featured = compute_all_features(raw, ticker="RELIANCE.NS")
    print(f"\nFeature count: {len(featured.columns)}")
    print(f"Shape: {featured.shape}")
    print(f"\nSample features:\n{featured[['return_1d', 'rsi_14', 'atr_14_pct', 'bb_pct_20']].tail()}")
