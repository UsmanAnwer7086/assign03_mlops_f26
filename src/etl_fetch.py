"""Fetch daily BTC-USD OHLCV data (yfinance first, Binance public API as fallback)."""

import argparse
import logging
import os
from pathlib import Path
from datetime import datetime, timedelta, timezone
import pandas as pd
import requests
import yfinance as yf

log = logging.getLogger("etl_fetch")

COLUMNS = ["Date", "Open", "High", "Low", "Close", "Volume"]

DEFAULT_DAYS = 1500


def default_raw_path():
    return Path(os.getenv("DATA_DIR", "data")) / "raw" / "btc_usd.csv"


def _fetch_yfinance(days):
    end_dt = datetime.now(timezone.utc)
    start_dt = end_dt - timedelta(days=days)

    df = yf.download(
        "BTC-USD",
        start=start_dt.strftime("%Y-%m-%d"),
        end=end_dt.strftime("%Y-%m-%d"),
        interval="1d",
        progress=False,
        auto_adjust=True,
    )
    if df is None or df.empty:
        raise RuntimeError("yfinance returned no data")

    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)

    df = df.reset_index().rename(columns={"index": "Date", "Datetime": "Date"})
    missing = [c for c in COLUMNS if c not in df.columns]
    if missing:
        raise RuntimeError(f"yfinance missing expected columns: {missing}")

    return df[COLUMNS]


def _fetch_binance(days):
    resp = requests.get(
        "https://api.binance.com/api/v3/klines",
        params={"symbol": "BTCUSDT", "interval": "1d", "limit": min(days, 1000)},
        timeout=30,
    )
    resp.raise_for_status()
    rows = [[pd.to_datetime(k[0], unit="ms"), k[1], k[2], k[3], k[4], k[5]] for k in resp.json()]
    df = pd.DataFrame(rows, columns=COLUMNS)
    return df.astype({c: float for c in COLUMNS[1:]})


def fetch_btc(days=DEFAULT_DAYS):
    try:
        return _fetch_yfinance(days)
    except Exception as exc:  # network / schema problems -> try the fallback source
        log.warning("yfinance failed (%s); falling back to Binance", exc)
        return _fetch_binance(days)


def run(out_path=None, days=DEFAULT_DAYS):
    """Download data, merge with any existing file, drop today's partial candle, save CSV."""
    out = Path(out_path) if out_path else default_raw_path()
    out.parent.mkdir(parents=True, exist_ok=True)
    df = fetch_btc(days)
    df["Date"] = pd.to_datetime(df["Date"], utc=True).dt.tz_localize(None).dt.normalize()
    if out.exists():
        old = pd.read_csv(out, parse_dates=["Date"])
        df = pd.concat([old, df])
    today = pd.Timestamp.now(tz="UTC").tz_localize(None).normalize()
    df = df[df["Date"] < today]
    df = df.drop_duplicates("Date", keep="last").sort_values("Date")
    df.to_csv(out, index=False)
    log.info("Saved %d rows to %s (last day: %s)", len(df), out, df["Date"].iloc[-1].date())
    return str(out)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default=None)
    parser.add_argument("--days", type=int, default=DEFAULT_DAYS)
    args = parser.parse_args()
    print(run(args.out, args.days))
