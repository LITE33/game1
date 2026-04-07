"""
track_orderbook.py
==================
Track the Kalshi orderbook for the currently live KXBTC15M market.

By default, auto-detects the live ticker — no need to hardcode a date.

Usage:
    # Auto-detect live ticker, track one 15-min window
    python3 track_orderbook.py

    # Run all day: auto-detect each new window as it opens
    python3 track_orderbook.py --continuous

    # Pin a specific ticker (useful for replaying a known window)
    python3 track_orderbook.py --ticker KXBTC15M-26APR071030

    # Different series (e.g. ETH)
    python3 track_orderbook.py --series KXETH15M

After a run, analyze your data:
    python3 -c "
    from kalshi.storage import KalshiStorage
    df = KalshiStorage().get_snapshots_df('KXBTC15M')
    print(df[['timestamp','best_yes','best_no','spread','event']].tail(20))
    print(df['spread'].describe())
    "
"""

import argparse
import asyncio

from kalshi.tracker import OrderbookTracker

DEFAULT_SERIES = "KXBTC15M"
DEFAULT_MINUTES = 15
DEFAULT_DB = "data/kalshi.db"


def parse_args():
    p = argparse.ArgumentParser(description="Kalshi orderbook tracker")
    p.add_argument("--ticker", default=None,
                   help="Explicit market ticker. Omit to auto-detect the live market.")
    p.add_argument("--series", default=DEFAULT_SERIES,
                   help=f"Series to auto-detect from (default: {DEFAULT_SERIES})")
    p.add_argument("--minutes", type=int, default=DEFAULT_MINUTES,
                   help="Tracking window in minutes per market (default: 15, 0 = until Ctrl-C)")
    p.add_argument("--continuous", action="store_true",
                   help="Keep running across market windows all day")
    p.add_argument("--db", default=DEFAULT_DB, help="SQLite database path")
    p.add_argument("--quiet", action="store_true", help="Suppress per-update output")
    return p.parse_args()


if __name__ == "__main__":
    args = parse_args()
    tracker = OrderbookTracker(
        ticker=args.ticker,
        series_ticker=args.series,
        window_minutes=args.minutes,
        continuous=args.continuous,
        db_path=args.db,
        verbose=not args.quiet,
    )
    asyncio.run(tracker.run())
