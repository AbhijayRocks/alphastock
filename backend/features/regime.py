"""
features/regime.py — Detect market regimes using a Hidden Markov Model (HMM).

WHAT IS A MARKET REGIME?
  Markets don't behave the same way all the time. They cycle through distinct
  states:
    0 - Bull / low vol   : trending up, momentum strategies work
    1 - Bear / high vol  : trending down, fear dominates, correlations spike
    2 - Sideways         : no clear trend, range-bound choppy action
    3 - Crisis / extreme : black swan events, everything breaks down

WHY THIS MATTERS FOR PREDICTION:
  The same feature (e.g. RSI=70) means something completely different in a
  bull market vs a crisis. By labeling each day with its regime, we give the
  model critical context. The meta-learner in Phase 4 will also use regime
  to dynamically weight which model to trust more.

HOW HMM WORKS (simple version):
  We observe daily returns + volatility. The HMM says: "given these
  observations, what's the most likely hidden state (regime) the market
  was in?" It learns the transitions between states from historical data.
  Think of it like weather forecasting — you can't directly observe "summer"
  or "winter", but temperature + humidity patterns tell you which season it is.

WE FIT ON NIFTY INDEX (not individual stocks):
  Market regime is a macro concept. We use the Nifty 50 index returns and
  volatility to label regimes, then broadcast that label to all 50 stocks.
  Every stock on the same day gets the same regime label.
"""

import logging
import pickle
from pathlib import Path
from typing import Tuple

import numpy as np
import pandas as pd
try:
    from hmmlearn.hmm import GaussianHMM
except ImportError:
    GaussianHMM = None
from sklearn.preprocessing import StandardScaler

from config import MODELS_DIR, LOG_LEVEL

logging.basicConfig(level=LOG_LEVEL, format="%(asctime)s | %(levelname)s | %(message)s")
logger = logging.getLogger(__name__)

REGIME_MODEL_PATH = MODELS_DIR / "regime_hmm.pkl"
N_REGIMES = 4   # bull, bear, sideways, crisis


def _build_hmm_features(index_df: pd.DataFrame) -> Tuple[np.ndarray, pd.DatetimeIndex]:
    """
    Build the observation matrix the HMM learns from.

    Features fed to HMM:
      - 1-day log return          : direction signal
      - 5-day rolling volatility  : short-term vol regime
      - 20-day rolling volatility : medium-term vol regime
      - 1-day return magnitude    : size of move (|return|)

    WHY LOG RETURNS: They're additive over time and more statistically
    well-behaved than simple returns. Standard practice in quant finance.
    """
    # Use nifty50 column if available, else first column
    price_col = "nifty50" if "nifty50" in index_df.columns else index_df.columns[0]
    prices = index_df[price_col].dropna()

    log_ret = np.log(prices / prices.shift(1)).dropna()

    features = pd.DataFrame(index=log_ret.index)
    features["log_return"]   = log_ret
    features["vol_5d"]       = log_ret.rolling(5).std()
    features["vol_20d"]      = log_ret.rolling(20).std()
    features["abs_return"]   = log_ret.abs()

    features = features.dropna()
    return features.values, features.index


def fit_regime_model(index_df: pd.DataFrame) -> GaussianHMM:
    """
    Fit HMM on Nifty index data and save to disk.

    Called once during training. The fitted model is saved and reloaded
    for inference so we don't retrain on every prediction call.

    Args:
        index_df: DataFrame with nifty50 price column (from ingestion)

    Returns:
        Fitted GaussianHMM model
    """
    logger.info(f"Fitting HMM regime model with {N_REGIMES} states...")

    X, dates = _build_hmm_features(index_df)

    # Standardize — HMM is sensitive to feature scale
    scaler = StandardScaler()
    X_scaled = scaler.fit_transform(X)

    # GaussianHMM: assumes each hidden state emits observations from a Gaussian
    # covariance_type="full" lets each regime have its own covariance matrix
    # n_iter=200 gives enough EM iterations to converge
    model = GaussianHMM(
        n_components=N_REGIMES,
        covariance_type="full",
        n_iter=200,
        random_state=42,
        verbose=False,
    )
    model.fit(X_scaled)

    # Save both model and scaler together
    REGIME_MODEL_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(REGIME_MODEL_PATH, "wb") as f:
        pickle.dump({"model": model, "scaler": scaler}, f)

    logger.info(f"HMM fitted and saved to {REGIME_MODEL_PATH}")
    logger.info(f"Convergence: {model.monitor_.converged}")

    return model


def load_regime_model() -> Tuple[GaussianHMM, StandardScaler]:
    """Load the saved HMM model + scaler from disk."""
    if not REGIME_MODEL_PATH.exists():
        raise FileNotFoundError(
            f"No regime model found at {REGIME_MODEL_PATH}. "
            "Call fit_regime_model() first."
        )
    with open(REGIME_MODEL_PATH, "rb") as f:
        bundle = pickle.load(f)
    return bundle["model"], bundle["scaler"]


def predict_regimes(index_df: pd.DataFrame) -> pd.Series:
    """
    Predict regime label for every trading day using the fitted HMM.

    Returns a Series indexed by date with integer regime labels 0-3.
    These labels are then semantically mapped to human-readable names.

    WHY WE MAP LABELS TO NAMES:
      HMM assigns arbitrary integers (0,1,2,3) to regimes based on which
      Gaussian each state learned. We look at the mean return and volatility
      of each state to assign meaningful names: the state with highest mean
      return = bull, lowest mean return = bear, etc.
    """
    model, scaler = load_regime_model()
    X, dates = _build_hmm_features(index_df)
    X_scaled = scaler.transform(X)

    raw_labels = model.predict(X_scaled)
    regime_series = pd.Series(raw_labels, index=dates, name="regime_raw")

    # Semantically map raw labels to named regimes
    named = _map_regime_labels(model, scaler, regime_series)
    return named


def _map_regime_labels(
    model: GaussianHMM,
    scaler: StandardScaler,
    raw_series: pd.Series,
) -> pd.Series:
    """
    Map HMM's arbitrary integer labels to meaningful regime names.

    Strategy:
      - Get mean return for each state from the HMM's learned means
      - State with highest mean return = "bull"
      - State with lowest mean return  = "bear"
      - Among remaining two: higher vol = "crisis", lower vol = "sideways"
    """
    # HMM means are in scaled space — inverse transform to get real values
    means_scaled = model.means_          # shape: (n_regimes, n_features)
    means_real   = scaler.inverse_transform(means_scaled)

    # Feature order: [log_return, vol_5d, vol_20d, abs_return]
    mean_returns = means_real[:, 0]   # log_return column
    mean_vol5d   = means_real[:, 1]   # vol_5d column

    sorted_by_return = np.argsort(mean_returns)  # ascending

    bull_label  = sorted_by_return[-1]   # highest return
    bear_label  = sorted_by_return[0]    # lowest return
    remaining   = [i for i in range(N_REGIMES) if i not in [bull_label, bear_label]]

    # Among remaining 2: higher vol = crisis, lower vol = sideways
    if len(remaining) == 2:
        if mean_vol5d[remaining[0]] > mean_vol5d[remaining[1]]:
            crisis_label, sideways_label = remaining[0], remaining[1]
        else:
            crisis_label, sideways_label = remaining[1], remaining[0]
    else:
        crisis_label   = remaining[0] if remaining else bear_label
        sideways_label = remaining[0] if remaining else bear_label

    label_map = {
        bull_label:    "bull",
        bear_label:    "bear",
        sideways_label:"sideways",
        crisis_label:  "crisis",
    }

    named = raw_series.map(label_map)
    named.name = "regime"

    # Log distribution so we can sanity-check
    dist = named.value_counts(normalize=True) * 100
    logger.info(f"Regime distribution:\n{dist.round(1)}")

    return named


def add_regime_features(df: pd.DataFrame, regime_series: pd.Series) -> pd.DataFrame:
    """
    Merge regime labels into a stock's feature DataFrame.

    Creates both:
      1. Named regime string column ("bull", "bear", etc.) — for display
      2. One-hot encoded columns — for the ML models (can't use strings)
      3. Regime transition flag — did regime change today? (important signal)

    Args:
        df           : stock feature DataFrame with DatetimeIndex
        regime_series: regime labels indexed by date (from predict_regimes)

    Returns:
        df with regime columns added
    """
    # Align regime series to this stock's trading dates
    df = df.copy()
    df["regime"] = regime_series.reindex(df.index, method="ffill")

    # One-hot encode for models
    for r in ["bull", "bear", "sideways", "crisis"]:
        df[f"regime_{r}"] = (df["regime"] == r).astype(float)

    # Regime transition: did the regime change from yesterday?
    df["regime_change"] = (df["regime"] != df["regime"].shift(1)).astype(float)

    # Regime duration: how many days have we been in current regime?
    # Useful signal — early in a bull regime vs late stage behave differently
    regime_group = (df["regime"] != df["regime"].shift(1)).cumsum()
    df["regime_duration"] = regime_group.groupby(regime_group).cumcount() + 1

    return df


def get_current_regime(index_df: pd.DataFrame) -> str:
    """
    Returns the current market regime as a string.
    Used by the dashboard and API to show live regime status.
    """
    regimes = predict_regimes(index_df)
    current = regimes.iloc[-1]
    logger.info(f"Current market regime: {current}")
    return current


if __name__ == "__main__":
    # Quick test — fit on Nifty index data
    import yfinance as yf

    logger.info("Downloading Nifty index for regime fitting...")
    raw = yf.download("^NSEI", start="2015-01-01", auto_adjust=True, progress=False)

    if isinstance(raw.columns, pd.MultiIndex):
        raw.columns = [col[0].lower() for col in raw.columns]
    else:
        raw.columns = [c.lower() for c in raw.columns]

    raw.index.name = "date"
    raw = raw.rename(columns={"close": "nifty50"})

    # Fit model
    fit_regime_model(raw)

    # Predict
    regimes = predict_regimes(raw)
    print(f"\nRegime series tail:\n{regimes.tail(10)}")
    print(f"\nCurrent regime: {regimes.iloc[-1]}")
    print(f"\nRegime counts:\n{regimes.value_counts()}")
