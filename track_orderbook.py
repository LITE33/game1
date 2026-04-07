"""
track_orderbook.py
==================
Run this script to track the Kalshi orderbook for a full 15-minute window.

Usage:
    python3 track_orderbook.py
    python3 track_orderbook.py --ticker KXBTC15M-26APR071030 --minutes 15
    python3 track_orderbook.py --minutes 0   # run until Ctrl-C

After the run, analyze your data:
    python3 -c "
    from kalshi.storage import KalshiStorage
    df = KalshiStorage().get_snapshots_df('KXBTC15M-26APR071030')
    print(df[['timestamp','best_yes','best_no','spread','event']].tail(20))
    print(df['spread'].describe())
    "
"""

import argparse
import asyncio

from kalshi.tracker import OrderbookTracker

DEFAULT_TICKER = "KXBTC15M-26APR071030"
DEFAULT_MINUTES = 15
DEFAULT_DB = "data/kalshi.db"


def parse_args():
    p = argparse.ArgumentParser(description="Kalshi orderbook tracker")
    p.add_argument("--ticker", default=DEFAULT_TICKER, help="Kalshi market ticker")
    p.add_argument("--minutes", type=int, default=DEFAULT_MINUTES,
                   help="Tracking window in minutes (0 = run forever)")
    p.add_argument("--db", default=DEFAULT_DB, help="SQLite database path")
    p.add_argument("--quiet", action="store_true", help="Suppress per-update output")
    return p.parse_args()


if __name__ == "__main__":
    args = parse_args()
    tracker = OrderbookTracker(
        ticker=args.ticker,
        window_minutes=args.minutes,
        db_path=args.db,
        verbose=not args.quiet,
    )
    asyncio.run(tracker.run())
