import pytorch_lightning as pl
from pytorch_forecasting import TemporalFusionTransformer
from pytorch_forecasting.metrics import QuantileLoss
from pytorch_forecasting.data import TimeSeriesDataSet

def build_tft_model(training_dataset: TimeSeriesDataSet, learning_rate: float = 1e-3) -> TemporalFusionTransformer:
    """
    Builds the Temporal Fusion Transformer architecture using the schema derived
    from the training dataset.
    """
    tft = TemporalFusionTransformer.from_dataset(
        training_dataset,
        learning_rate=learning_rate,
        hidden_size=128,           # Increased from 32 to 128 (4x capacity)
        attention_head_size=8,     # Increased from 4 to 8 for better temporal parsing
        dropout=0.1,
        hidden_continuous_size=64, # Increased from 16 to 64 for 80+ features
        output_size=7,             # QuantileLoss predicts 7 quantiles by default
        loss=QuantileLoss(),       # Provides confidence intervals natively
        log_interval=10,
        reduce_on_plateau_patience=4,
    )
    return tft
