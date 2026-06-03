import pandas as pd
import numpy as np
from pytorch_forecasting import TimeSeriesDataSet
from config import SEQUENCE_LENGTH

def create_tft_dataset(df: pd.DataFrame, ticker: str, horizon: str, training_dataset: TimeSeriesDataSet = None) -> TimeSeriesDataSet:
    """
    Convert a feature DataFrame into a PyTorch Forecasting TimeSeriesDataSet.
    TFT requires specific formatting:
      - time_idx: Continuous integer index
      - group_id: The entity being tracked (the ticker)
      - target: The column to predict
    """
    df = df.copy()
    
    # 1. Add required identifier columns
    df['ticker'] = ticker
    df['time_idx'] = np.arange(len(df))
    
    # 2. Identify target
    target_col = f"target_{horizon}"
    if target_col not in df.columns:
        raise ValueError(f"Target column {target_col} missing.")
        
    # Drop rows where target is NaN
    df = df.dropna(subset=[target_col])
    
    # 3. Categorize features
    # Exclude targets from being used as features
    target_cols = [c for c in df.columns if c.startswith('target_')]
    exclude_cols = ['ticker', 'time_idx', 'date'] + target_cols
    
    feature_cols = [c for c in df.columns if c not in exclude_cols]
    
    # Identify statics and time-varying
    # For now, all our computed features are time-varying and known up to the present
    # We will treat them as time_varying_unknown_reals because we don't know them in the future
    time_varying_unknown_reals = feature_cols
    
    # 4. Create the dataset
    max_prediction_length = 1  # We predict exactly 1 step into the future (the horizon return)
    max_encoder_length = SEQUENCE_LENGTH
    
    if training_dataset is not None:
        return TimeSeriesDataSet.from_dataset(training_dataset, df, predict=False, stop_randomization=True)
        
    dataset = TimeSeriesDataSet(
        df,
        time_idx="time_idx",
        target=target_col,
        group_ids=["ticker"],
        min_encoder_length=max_encoder_length // 2,  # allow shorter sequences if needed
        max_encoder_length=max_encoder_length,
        min_prediction_length=1,
        max_prediction_length=max_prediction_length,
        static_categoricals=["ticker"],
        time_varying_known_categoricals=[],
        time_varying_known_reals=["time_idx"],
        time_varying_unknown_categoricals=[],
        time_varying_unknown_reals=time_varying_unknown_reals,
        target_normalizer=None,  # Returns are already stationary and scaled (-1 to 1 mostly)
        add_relative_time_idx=True,
        add_target_scales=True,
        add_encoder_length=True,
    )
    
    return dataset
