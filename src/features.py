"""Feature engineering shared by training, the Airflow DAG and the Flask API.

Features are scale-free (returns and ratios), and the target is the next-day return, so the
tree model does not have to extrapolate absolute BTC prices.
"""
import numpy as np
import pandas as pd

HORIZON = 7
LAGS = 14
MIN_HISTORY = 30
FEATURE_COLS = [f"ret_{i}" for i in range(1, LAGS + 1)] + ["ma7", "ma30", "vol7"]
MAX_DAILY_MOVE = 0.20


def make_row(closes):
    """Build one feature row from the tail of a close-price history."""
    s = np.asarray(closes[-(MIN_HISTORY + 1) :], dtype=float)
    last = s[-1]
    row = {f"ret_{i}": s[-i] / s[-i - 1] - 1 for i in range(1, LAGS + 1)}
    row["ma7"] = s[-7:].mean() / last
    row["ma30"] = s[-30:].mean() / last
    window = s[-8:]
    row["vol7"] = float(np.std(np.diff(window) / window[:-1]))
    return row


def build_dataset(closes):
    """Return (X, y) where y is the next-day return for every usable day."""
    s = np.asarray(closes, dtype=float)
    rows, targets = [], []
    for t in range(MIN_HISTORY, len(s)):
        rows.append(make_row(s[:t]))
        targets.append(s[t] / s[t - 1] - 1)
    return pd.DataFrame(rows, columns=FEATURE_COLS), np.asarray(targets)


def forecast_closes(model, closes, days=HORIZON):
    """Recursive multi-step forecast of the next `days` closing prices."""
    history = [float(c) for c in closes]
    out = []
    for _ in range(days):
        x = pd.DataFrame([make_row(history)], columns=FEATURE_COLS)
        ret = float(model.predict(x)[0])
        ret = max(min(ret, MAX_DAILY_MOVE), -MAX_DAILY_MOVE)
        history.append(history[-1] * (1 + ret))
        out.append(history[-1])
    return out
