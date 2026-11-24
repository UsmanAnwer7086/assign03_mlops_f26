# """Train the 7-day BTC close forecaster, validate it, and register artifacts if it passes.

# Validation: hold out the last 7 days, forecast them recursively, compute MAE/RMSE/MAPE.
# If MAPE <= threshold the model is re-fit on all data and written atomically to MODEL_DIR.
# """

# import argparse
# import json
# import logging
# import os
# import tempfile
# from datetime import datetime, timezone
# from pathlib import Path

# import joblib
# import numpy as np
# import pandas as pd

# from .features import HORIZON, MIN_HISTORY, build_dataset, forecast_closes

# log = logging.getLogger("train")
# MIN_ROWS = 120


# def make_model():
#     from xgboost import XGBRegressor

#     return XGBRegressor(
#         n_estimators=int(os.getenv("N_ESTIMATORS", "300")),
#         max_depth=3,
#         learning_rate=0.05,
#         subsample=0.8,
#         random_state=42,
#         n_jobs=1,
#     )


# def _atomic_write(path, writer):
#     fd, tmp = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
#     os.close(fd)
#     writer(tmp)
#     os.replace(tmp, path)


# def _write_json(path, obj):
#     _atomic_write(path, lambda tmp: Path(tmp).write_text(json.dumps(obj, indent=2)))


# def train_and_register(df, model_dir, mape_threshold=None):
#     if mape_threshold is None:
#         mape_threshold = float(os.getenv("MAPE_THRESHOLD", "15"))
#     model_dir = Path(model_dir)
#     model_dir.mkdir(parents=True, exist_ok=True)
#     df = df.dropna(subset=["Close"]).sort_values("Date").reset_index(drop=True)
#     closes = df["Close"].astype(float).to_numpy()
#     if len(closes) < MIN_ROWS:
#         raise ValueError(f"Need at least {MIN_ROWS} rows, got {len(closes)}")

#     # 1) validation on the latest 7-day window
#     train_part, actual = closes[:-HORIZON], closes[-HORIZON:]
#     X, y = build_dataset(train_part)
#     candidate = make_model().fit(X, y)
#     pred = np.asarray(forecast_closes(candidate, train_part, HORIZON))
#     err = pred - actual
#     metrics = {
#         "mae": float(np.mean(np.abs(err))),
#         "rmse": float(np.sqrt(np.mean(err**2))),
#         "mape": float(np.mean(np.abs(err / actual)) * 100),
#         "validation_days": HORIZON,
#         "mape_threshold": mape_threshold,
#     }
#     passed = metrics["mape"] <= mape_threshold
#     result = {"passed": passed, "metrics": metrics}
#     log.info("Validation metrics: %s (passed=%s)", metrics, passed)
#     if not passed:
#         return result

#     # 2) re-fit on everything and register
#     X, y = build_dataset(closes)
#     final = make_model().fit(X, y)
#     now = datetime.now(timezone.utc)
#     last_date = pd.to_datetime(df["Date"].iloc[-1]).date().isoformat()
#     meta = {
#         "version": now.strftime("%Y%m%d%H%M%S"),
#         "trained_at": now.isoformat(),
#         "last_date": last_date,
#         "n_rows": int(len(closes)),
#         "algorithm": "xgboost-recursive-return-model",
#     }
#     metrics["version"] = meta["version"]
#     _atomic_write(model_dir / "model.joblib", lambda tmp: joblib.dump(final, tmp))
#     _write_json(model_dir / "closes.json", [float(c) for c in closes[-(MIN_HISTORY * 2):]])
#     _write_json(model_dir / "metrics.json", metrics)
#     _write_json(model_dir / "meta.json", meta)  # written last: the API watches this file
#     result["meta"] = meta
#     return result


# if __name__ == "__main__":
#     logging.basicConfig(level=logging.INFO)
#     parser = argparse.ArgumentParser()
#     parser.add_argument("--data", default=None)
#     parser.add_argument("--model-dir", default=None)
#     args = parser.parse_args()
#     data = args.data or str(Path(os.getenv("DATA_DIR", "data")) / "processed" / "btc_features.csv")
#     out_dir = args.model_dir or os.getenv("MODEL_DIR", "models")
#     print(json.dumps(train_and_register(pd.read_csv(data), out_dir)))
