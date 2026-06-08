"""
api/daily_scheduler.py — In-process automatic daily data refresh.

A daemon thread that keeps the platform's data current without any OS-level cron
or manual command:

  • On startup it runs a catch-up refresh, so if the app was closed over a
    trading session (e.g. you open it Monday after a Friday close) the data is
    brought current right away.
  • Thereafter it wakes once per day shortly after the NSE close, refreshes the
    raw data, rebuilds features only if a newer bar arrived, and **hot-reloads
    the live model registry in place** — no restart needed.

It only runs while the backend is up (by design — see the chosen approach). The
same work is available as a standalone command for OS schedulers / manual runs:
`python -m data_pipeline.daily_update`.

Configuration (all optional, env-driven):
    ALPHASTOCK_DAILY_UPDATE   "1"/"true" to enable (default: enabled)
    ALPHASTOCK_UPDATE_HOUR    hour of day, IST, to run the refresh (default: 18)
    ALPHASTOCK_UPDATE_MINUTE  minute of the hour (default: 0)
"""

import os
import logging
import threading
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

try:  # Python 3.9+ stdlib; present on the project's 3.14 interpreter.
    from zoneinfo import ZoneInfo
    _IST = ZoneInfo("Asia/Kolkata")
except Exception:  # noqa: BLE001 — fall back to a fixed +05:30 offset.
    from datetime import timezone
    _IST = timezone(timedelta(hours=5, minutes=30))


def _enabled() -> bool:
    val = os.getenv("ALPHASTOCK_DAILY_UPDATE", "1").strip().lower()
    return val not in ("0", "false", "no", "off", "")


def _run_at() -> tuple[int, int]:
    """(hour, minute) in IST at which the daily refresh runs."""
    try:
        hour = int(os.getenv("ALPHASTOCK_UPDATE_HOUR", "18"))
    except ValueError:
        hour = 18
    try:
        minute = int(os.getenv("ALPHASTOCK_UPDATE_MINUTE", "0"))
    except ValueError:
        minute = 0
    return max(0, min(hour, 23)), max(0, min(minute, 59))


def _seconds_until_next_run() -> float:
    hour, minute = _run_at()
    now = datetime.now(_IST)
    target = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if target <= now:
        target += timedelta(days=1)
    return (target - now).total_seconds()


def _refresh_and_reload(registry, reason: str) -> None:
    """Run the data refresh and hot-reload the registry if anything changed."""
    # Imported lazily so importing this module never drags in the heavy ML stack.
    from data_pipeline.daily_update import run_daily_update

    logger.info(f"Daily refresh starting ({reason})...")
    summary = run_daily_update()

    if summary.get("error"):
        logger.warning(f"Daily refresh hit an error: {summary['error']}")
    if summary.get("updated"):
        logger.info(
            f"Daily refresh: data advanced to {summary.get('feature_date')} "
            f"(was {summary.get('previous_date')}) — hot-reloading registry."
        )
        try:
            registry.reload_live_data()
        except Exception as e:  # noqa: BLE001
            logger.error(f"Registry hot-reload failed: {e}")
    else:
        logger.info(
            f"Daily refresh: no new session (data at {summary.get('feature_date')}) — "
            "nothing to reload."
        )


def _loop(registry) -> None:
    # Catch-up on startup: bring data current if a session was missed while closed.
    try:
        _refresh_and_reload(registry, reason="startup catch-up")
    except Exception as e:  # noqa: BLE001
        logger.error(f"Startup catch-up refresh failed: {e}")

    hour, minute = _run_at()
    logger.info(f"Daily auto-refresh scheduled for {hour:02d}:{minute:02d} IST.")

    while True:
        # Sleep in <=1h slices so a long wait stays responsive to process exit.
        remaining = _seconds_until_next_run()
        while remaining > 0:
            time_to_sleep = min(remaining, 3600.0)
            threading.Event().wait(time_to_sleep)
            remaining = _seconds_until_next_run()
            # When we've crossed the target the next computed value jumps back up
            # near a full day, so break once we were within a slice of firing.
            if remaining > 3600.0 and time_to_sleep < 3600.0:
                break
        try:
            _refresh_and_reload(registry, reason="scheduled daily run")
        except Exception as e:  # noqa: BLE001
            logger.error(f"Scheduled refresh failed: {e}")


def start_daily_scheduler(registry) -> bool:
    """
    Launch the daily-refresh daemon thread. Returns True if started.

    No-op (returns False) when disabled via ALPHASTOCK_DAILY_UPDATE=0.
    """
    if not _enabled():
        logger.info("Daily auto-refresh disabled (ALPHASTOCK_DAILY_UPDATE=0).")
        return False

    thread = threading.Thread(
        target=_loop, args=(registry,), name="daily-refresh", daemon=True
    )
    thread.start()
    return True
