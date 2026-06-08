"""
data_pipeline/daily_update.py — Automatic daily data refresh.

Brings the platform's stored data current with the latest NSE trading session:

  1. Incrementally fetches the last few days of OHLCV and appends to the raw store
     (deduped, sorted) — see `ingestion.run_incremental_update`.
  2. Refreshes the macro and Nifty-index series (small full re-pulls).
  3. Rebuilds the per-stock feature panels the models predict from — but only
     when a genuinely newer bar actually arrived, so weekends / market holidays
     are cheap no-ops instead of pointless 5-10 minute rebuilds.

Design goals:
  - **Idempotent & safe to call repeatedly.** Re-running on the same day does
    nothing expensive.
  - **Never raises.** A failed refresh logs the problem and leaves the previous
    good data in place, so a flaky yfinance call can't take the API down.

Run manually:
    python -m data_pipeline.daily_update            # refresh + rebuild if newer
    python -m data_pipeline.daily_update --force     # always rebuild features

In-process:
    The API schedules `run_daily_update()` after each NSE close and then
    hot-reloads the model registry — see `api/daily_scheduler.py`.
"""

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional

import pandas as pd

from config import FEATURES_DIR
from data_pipeline.ingestion import (
    run_incremental_update,
    fetch_macro,
    fetch_nifty_index,
    save_dataframe,
)
from data_pipeline.nifty50 import get_all_tickers

logger = logging.getLogger(__name__)

PIPELINE_DIR = FEATURES_DIR / "pipeline"
RAW_OHLCV_DIR = FEATURES_DIR / "raw" / "ohlcv"
MARKER_PATH = FEATURES_DIR / ".last_update.json"


def _max_last_index(directory: Path) -> Optional[pd.Timestamp]:
    """Latest bar date across every parquet in `directory` (None if empty)."""
    if not directory.exists():
        return None
    latest: Optional[pd.Timestamp] = None
    for path in directory.glob("*.parquet"):
        try:
            # Reading just the index is cheap relative to a feature rebuild.
            idx = pd.read_parquet(path, engine="pyarrow").index
            if len(idx) == 0:
                continue
            last = pd.Timestamp(idx[-1])
            if latest is None or last > latest:
                latest = last
        except Exception:  # noqa: BLE001 — a single unreadable file shouldn't abort
            continue
    return latest


def latest_feature_date() -> Optional[pd.Timestamp]:
    """Newest bar present in the built feature panels (what models predict on)."""
    return _max_last_index(PIPELINE_DIR)


def latest_ohlcv_date() -> Optional[pd.Timestamp]:
    """Newest bar present in the raw OHLCV store."""
    return _max_last_index(RAW_OHLCV_DIR)


def read_marker() -> Optional[Dict]:
    """Return the last-update record written by `run_daily_update`, if any."""
    if not MARKER_PATH.exists():
        return None
    try:
        return json.loads(MARKER_PATH.read_text())
    except Exception:  # noqa: BLE001
        return None


def _write_marker(info: Dict) -> None:
    try:
        MARKER_PATH.write_text(json.dumps(info, indent=2))
    except Exception as e:  # noqa: BLE001
        logger.warning(f"daily_update: could not write marker file: {e}")


def run_daily_update(
    tickers: Optional[List[str]] = None,
    force: bool = False,
    rebuild: bool = True,
) -> Dict:
    """
    Refresh raw data and (when newer bars arrived) rebuild the feature panels.

    Returns a summary dict:
        {
          "ran_at":        ISO timestamp (UTC),
          "ohlcv_date":    latest raw bar after ingest (str | None),
          "feature_date":  latest feature bar after the run (str | None),
          "previous_date": latest feature bar before the run (str | None),
          "rebuilt":       bool — whether features were rebuilt,
          "updated":       bool — whether new data actually landed,
          "error":         str | None,
        }

    Never raises — failures are captured in the "error" field.
    """
    if tickers is None:
        tickers = get_all_tickers()

    before = latest_feature_date()
    summary: Dict = {
        "ran_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "ohlcv_date": None,
        "feature_date": before.isoformat() if before is not None else None,
        "previous_date": before.isoformat() if before is not None else None,
        "rebuilt": False,
        "updated": False,
        "error": None,
    }

    try:
        # 1) Incremental OHLCV (last ~7 days, appended + deduped).
        logger.info("daily_update: fetching incremental OHLCV...")
        run_incremental_update(tickers)

        # 2) Refresh the small market-wide series so index/macro features stay current.
        for name, fetch in (("macro", fetch_macro), ("nifty_index", fetch_nifty_index)):
            try:
                df = fetch()
                if df is not None and not df.empty:
                    save_dataframe(df, name)
            except Exception as e:  # noqa: BLE001
                logger.warning(f"daily_update: {name} refresh failed: {e}")

        after_ohlcv = latest_ohlcv_date()
        summary["ohlcv_date"] = after_ohlcv.isoformat() if after_ohlcv is not None else None

        # 3) Rebuild features only when a genuinely newer bar arrived (or forced).
        need_rebuild = force or before is None or (
            after_ohlcv is not None and after_ohlcv > before
        )

        if need_rebuild and rebuild:
            logger.info("daily_update: newer data detected — rebuilding feature panels...")
            # Imported lazily: the feature pipeline pulls in the heavy TA/ML stack.
            from features.pipeline import build_all_features

            # NB: build_all_features keys OHLCV by the on-disk *safe* name
            # (e.g. "RELIANCE_NS"), not the dotted yfinance symbol. Passing the
            # dotted `tickers` here would match nothing — let it derive the
            # universe from the loaded files (tickers=None).
            build_all_features(save=True)
            summary["rebuilt"] = True
        elif not need_rebuild:
            logger.info("daily_update: no newer bars — feature rebuild skipped.")

        after_feat = latest_feature_date()
        summary["feature_date"] = after_feat.isoformat() if after_feat is not None else None
        summary["updated"] = bool(
            after_feat is not None and (before is None or after_feat > before)
        )

    except Exception as e:  # noqa: BLE001 — never let a refresh crash the caller/API
        logger.error(f"daily_update: failed — {e}", exc_info=True)
        summary["error"] = str(e)

    _write_marker(summary)
    return summary


if __name__ == "__main__":
    import sys

    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s"
    )
    force = "--force" in sys.argv[1:]
    result = run_daily_update(force=force)
    print(json.dumps(result, indent=2))
