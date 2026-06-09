"""
data_pipeline/hf_sync.py — Hugging Face Hub artifact sync.

WHY THIS EXISTS
  The trained models (~97 MB) and feature panels (~360 MB) are git-ignored, so
  they never reach a clone-based deploy like Render. Without them the backend
  boots "healthy" but every model-backed endpoint (/predict, /screen, /pulse,
  /signals, /explain, /backtest) returns nothing, and the frontend silently
  falls back to mock data — only the live /prices ticker looks real.

  This module closes that gap with two halves:
    • prepare_and_upload()  — DEV side. Trims the feature parquets to a recent
      window and pushes a slim artifact set to a Hugging Face model repo.
    • ensure_artifacts()    — SERVING side. On boot, if artifacts/ is empty and
      HF_REPO_ID is configured, downloads them from the Hub to disk.

  Disk is not the bottleneck on Render — RAM is (512 MB free tier). So we keep
  the full (trimmed) parquets on disk for backtest/cross-sectional reads, and
  only load a short tail into memory (see ModelRegistry._load_latest_features).

ENV VARS
  HF_REPO_ID   e.g. "your-username/alphastock-artifacts"  (required)
  HF_TOKEN     a Hugging Face token (write for upload, read for private repos)
"""

import logging
import os
import shutil
from pathlib import Path
from typing import Optional

from config import (
    ARTIFACTS_DIR, FEATURES_DIR, MODELS_DIR, HF_REPO_ID, HF_TOKEN, LOG_LEVEL,
)

logging.basicConfig(level=LOG_LEVEL, format="%(asctime)s | %(levelname)s | %(message)s")
logger = logging.getLogger(__name__)

# Rows kept per feature parquet when shipping to the Hub. ~2000 daily bars ≈ 8
# years — enough for a meaningful walk-forward backtest (tests the last 15%)
# while keeping the download small. Override with ALPHASTOCK_SHIP_ROWS.
SHIP_ROWS = int(os.getenv("ALPHASTOCK_SHIP_ROWS", "2000"))

# A repo id is "configured" only if it isn't the placeholder from config.py.
_PLACEHOLDER = "your-username/alpha-stock-models"


def _repo_configured() -> bool:
    return bool(HF_REPO_ID) and HF_REPO_ID != _PLACEHOLDER


def _has_local_models() -> bool:
    """True if at least one trained-model directory already exists on disk."""
    if not MODELS_DIR.exists():
        return False
    for child in MODELS_DIR.iterdir():
        if child.is_dir() and not child.name.startswith("."):
            return True
    return False


# ── SERVING side: pull artifacts at boot ─────────────────────────────────────

def ensure_artifacts() -> bool:
    """
    Ensure model + feature artifacts exist on disk, pulling them from the Hugging
    Face Hub if missing. Safe to call at startup — never raises.

    Returns True if artifacts are present (already local or freshly downloaded),
    False if they could not be obtained (the app should still boot; auth + docs
    + the live-price ticker work without models).
    """
    if _has_local_models():
        logger.info("Artifacts already present on disk — skipping Hub download.")
        return True

    if not _repo_configured():
        logger.warning(
            "No models on disk and HF_REPO_ID is unset/placeholder — model "
            "endpoints will be empty. Set HF_REPO_ID (and HF_TOKEN) to auto-pull."
        )
        return False

    try:
        from huggingface_hub import snapshot_download
    except Exception as e:  # noqa: BLE001
        logger.error(f"huggingface_hub not importable ({e}); cannot pull artifacts.")
        return False

    logger.info(f"Downloading artifacts from Hugging Face repo '{HF_REPO_ID}'...")
    try:
        ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)
        # huggingface_hub >= 1.0 downloads real files into local_dir (no symlinks)
        # and dropped the old `local_dir_use_symlinks` kwarg, so we don't pass it.
        snapshot_download(
            repo_id=HF_REPO_ID,
            repo_type="model",
            local_dir=str(ARTIFACTS_DIR),
            token=HF_TOKEN or None,
        )
    except Exception as e:  # noqa: BLE001
        logger.error(f"Artifact download failed: {e}. App will boot without models.")
        return False

    ok = _has_local_models()
    logger.info(
        "Artifact download complete." if ok
        else "Download finished but no model directories found — check repo layout."
    )
    return ok


# ── DEV side: trim + upload artifacts ────────────────────────────────────────

def stage_artifacts(ship_rows: int = SHIP_ROWS) -> tuple:
    """
    Stage a slim artifact set into `artifacts/../_hf_staging` (models + recent-
    window feature parquets + the small raw snapshots the API reads). Returns
    (staging_path, n_stocks, size_mb). No network — safe to dry-run.
    """
    import pandas as pd

    if not _has_local_models():
        raise SystemExit(f"No local models under {MODELS_DIR}. Train first.")

    staging = ARTIFACTS_DIR.parent / "_hf_staging"
    if staging.exists():
        shutil.rmtree(staging)
    (staging / "features" / "pipeline").mkdir(parents=True, exist_ok=True)
    (staging / "features" / "raw").mkdir(parents=True, exist_ok=True)

    # 1) Models — copied whole (already compact at ~97 MB).
    logger.info("Staging models/ ...")
    shutil.copytree(MODELS_DIR, staging / "models", dirs_exist_ok=True)

    # 2) Feature pipeline parquets — trimmed to the most recent `ship_rows` bars.
    pipeline_src = FEATURES_DIR / "pipeline"
    kept = 0
    for pq in sorted(pipeline_src.glob("*.parquet")):
        try:
            df = pd.read_parquet(pq, engine="pyarrow")
            df.tail(ship_rows).to_parquet(
                staging / "features" / "pipeline" / pq.name,
                engine="pyarrow", compression="snappy",
            )
            kept += 1
        except Exception as e:  # noqa: BLE001
            logger.warning(f"Skipping {pq.name}: {e}")
    logger.info(f"Trimmed {kept} pipeline parquets to last {ship_rows} rows.")

    # 3) Small raw snapshots the serving API reads directly (fundamentals for the
    #    screener; macro/index in case features get rebuilt). All tiny.
    for name in ("fundamentals.parquet", "macro.parquet", "nifty_index.parquet"):
        src = FEATURES_DIR / "raw" / name
        if src.exists():
            shutil.copy2(src, staging / "features" / "raw" / name)

    # 4) Feature selectors, if present (small pickles used by some paths).
    sel_src = FEATURES_DIR / "selection"
    if sel_src.exists():
        shutil.copytree(sel_src, staging / "features" / "selection", dirs_exist_ok=True)

    size_mb = sum(f.stat().st_size for f in staging.rglob("*") if f.is_file()) / 1048576
    logger.info(f"Staged {size_mb:.0f} MB ({kept} stocks) at {staging}.")
    return staging, kept, size_mb


def prepare_and_upload(
    repo_id: Optional[str] = None,
    token: Optional[str] = None,
    ship_rows: int = SHIP_ROWS,
    private: bool = True,
) -> None:
    """
    Stage the slim artifact set and upload it to a Hugging Face model repo. Run
    this once from a machine that has the full local artifacts.

      python -m data_pipeline.hf_sync          # uses HF_REPO_ID / HF_TOKEN env
    """
    repo_id = repo_id or HF_REPO_ID
    token = token or HF_TOKEN
    if not repo_id or repo_id == _PLACEHOLDER:
        raise SystemExit("Set HF_REPO_ID (e.g. 'username/alphastock-artifacts').")
    if not token:
        raise SystemExit("Set HF_TOKEN (a Hugging Face write token).")

    from huggingface_hub import HfApi, upload_folder

    staging, kept, size_mb = stage_artifacts(ship_rows)

    logger.info(f"Uploading {size_mb:.0f} MB to '{repo_id}'...")
    api = HfApi(token=token)
    api.create_repo(repo_id=repo_id, repo_type="model", private=private, exist_ok=True)
    upload_folder(
        repo_id=repo_id,
        repo_type="model",
        folder_path=str(staging),
        token=token,
        commit_message=f"Upload serving artifacts ({size_mb:.0f} MB, {kept} stocks)",
    )
    logger.info(f"Upload complete → https://huggingface.co/{repo_id}")
    shutil.rmtree(staging, ignore_errors=True)


if __name__ == "__main__":
    prepare_and_upload()
