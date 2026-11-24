"""Clean raw data and add technical indicators (7/30-day MA, volatility, next-day target)."""
import argparse
import logging
import os
from pathlib import Path

import pandas as pd

log = logging.getLogger("preprocess")


def clean(df):
    df = df.copy()
    df["Date"] = pd.to_datetime(df["Date"], utc=True).dt.tz_localize(None)
    for col in ["Open", "High", "Low", "Close", "Volume"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    df = df.dropna(subset=["Close"])
    df = df[df["Close"] > 0]
    df = df.drop_duplicates("Date", keep="last").sort_values("Date").reset_index(drop=True)
    return df.ffill()


def add_indicators(df):
    df = df.copy()
    df["return_1d"] = df["Close"].pct_change()
    df["ma7"] = df["Close"].rolling(7).mean()
    df["ma30"] = df["Close"].rolling(30).mean()
    df["vol7"] = df["return_1d"].rolling(7).std()
    df["vol30"] = df["return_1d"].rolling(30).std()
    df["target_next_close"] = df["Close"].shift(-1)
    return df


def run(inp=None, out=None):
    data_dir = Path(os.getenv("DATA_DIR", "data"))
    inp = Path(inp) if inp else data_dir / "raw" / "btc_usd.csv"
    out = Path(out) if out else data_dir / "processed" / "btc_features.csv"
    out.parent.mkdir(parents=True, exist_ok=True)
    df = add_indicators(clean(pd.read_csv(inp)))
    df.to_csv(out, index=False)
    log.info("Wrote %d processed rows to %s", len(df), out)
    return str(out)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    parser = argparse.ArgumentParser()
    parser.add_argument("--inp", default=None)
    parser.add_argument("--out", default=None)
    args = parser.parse_args()
    print(run(args.inp, args.out))
