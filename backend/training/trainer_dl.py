import logging
import os
from pathlib import Path
import lightning.pytorch as pl
from lightning.pytorch.callbacks import EarlyStopping, ModelCheckpoint
import torch
from sklearn.model_selection import TimeSeriesSplit

from config import MODELS_DIR, SEQUENCE_LENGTH, LOG_LEVEL
from features.pipeline import load_features, get_train_test_split
from training.dl_dataset import create_tft_dataset
from models.tft_model import build_tft_model

logging.basicConfig(level=LOG_LEVEL, format="%(asctime)s | %(levelname)s | %(message)s")
logger = logging.getLogger(__name__)

def train_tft(ticker: str, horizon: str = "20d", batch_size: int = 64, max_epochs: int = 150):
    """
    Train a Temporal Fusion Transformer for a given stock and horizon.
    Uses TimeSeriesSplit (Walk-Forward Cross Validation) to train 3 separate models
    and ensure robustness across different market regimes.
    """
    logger.info(f"Preparing Heavy TFT training for {ticker} (horizon: {horizon})...")
    
    # 1. Load data
    df = load_features(ticker)
    
    # 2. Setup Walk-Forward CV
    n_splits = 3
    tscv = TimeSeriesSplit(n_splits=n_splits)
    
    fold = 1
    best_models = []
    
    accelerator = "gpu" if torch.cuda.is_available() else "cpu"
    logger.info(f"Training on accelerator: {accelerator} | Batch Size: {batch_size}")

    for train_index, val_index in tscv.split(df):
        logger.info(f"--- Starting Fold {fold}/{n_splits} ---")
        
        # Apply embargo (prevent data leakage by dropping 1% of overlapping data between train/val)
        embargo = max(1, int(len(train_index) * 0.01))
        train_index_purged = train_index[:-embargo]
        
        train_df = df.iloc[train_index_purged].copy()
        val_df = df.iloc[val_index].copy()
        
        logger.info(f"Fold {fold} Data shapes - Train: {train_df.shape}, Val: {val_df.shape}")
        
        # 3. Create Datasets
        training_dataset = create_tft_dataset(train_df, ticker, horizon)
        validation_dataset = create_tft_dataset(val_df, ticker, horizon, training_dataset=training_dataset)
        
        # 4. Create DataLoaders
        train_dataloader = training_dataset.to_dataloader(train=True, batch_size=batch_size, num_workers=0)
        val_dataloader = validation_dataset.to_dataloader(train=False, batch_size=batch_size, num_workers=0)
        
        # 5. Build Model
        tft = build_tft_model(training_dataset)
        
        # 6. Setup Callbacks
        save_dir = MODELS_DIR / ticker / horizon / f"tft_fold_{fold}"
        save_dir.mkdir(parents=True, exist_ok=True)
        
        early_stop_callback = EarlyStopping(
            monitor="val_loss", 
            min_delta=1e-4, 
            patience=10, 
            verbose=True, 
            mode="min"
        )
        
        checkpoint_callback = ModelCheckpoint(
            dirpath=save_dir,
            filename="best_tft",
            save_top_k=1,
            verbose=True,
            monitor="val_loss",
            mode="min",
        )
        
        # 7. Setup Trainer
        trainer = pl.Trainer(
            max_epochs=max_epochs,
            accelerator=accelerator,
            devices=1,
            callbacks=[early_stop_callback, checkpoint_callback],
            gradient_clip_val=0.1,
            enable_progress_bar=True,
        )
        
        # 8. Train
        logger.info(f"Training Fold {fold}...")
        trainer.fit(
            tft,
            train_dataloaders=train_dataloader,
            val_dataloaders=val_dataloader,
        )
        
        logger.info(f"Fold {fold} complete. Best model saved to: {checkpoint_callback.best_model_path}")
        best_models.append(checkpoint_callback.best_model_path)
        fold += 1

    # Ultimately, after CV proves stability, we train a final model on all data.
    # For now, we return the paths of the CV models.
    return best_models

if __name__ == "__main__":
    # Test script - train on one stock
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--ticker", type=str, default="RELIANCE.NS")
    parser.add_argument("--horizon", type=str, default="20d")
    parser.add_argument("--batch_size", type=int, default=64)
    args = parser.parse_args()
    
    train_tft(ticker=args.ticker, horizon=args.horizon, batch_size=args.batch_size)
