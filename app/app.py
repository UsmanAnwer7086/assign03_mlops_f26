"""Flask REST API serving the 7-day BTC-USD closing price forecast."""

import hmac
import json
import logging
import os
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import joblib
from flask import Flask, jsonify, request
from werkzeug.exceptions import HTTPException

from src.features import MIN_HISTORY, forecast_closes

logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
log = logging.getLogger("btc-api")

app = Flask(__name__)
app.json.sort_keys = False

START_TIME = time.time()
MAX_DAYS = 30
_state = {"model": None, "meta": {}, "metrics": {}, "closes": [], "stamp": None}


def _model_dir():
    return Path(os.getenv("MODEL_DIR", "models"))


def _load(force=False):
    """(Re)load artifacts when meta.json changes. Returns True if a model is available."""
    meta_file = _model_dir() / "meta.json"
    if not meta_file.exists():
        return _state["model"] is not None
    stamp = meta_file.stat().st_mtime
    if not force and stamp == _state["stamp"]:
        return _state["model"] is not None
    try:
        d = _model_dir()
        _state.update(
            model=joblib.load(d / "model.joblib"),
            meta=json.loads(meta_file.read_text()),
            metrics=json.loads((d / "metrics.json").read_text()),
            closes=json.loads((d / "closes.json").read_text()),
            stamp=stamp,
        )
        log.info("Loaded model version %s", _state["meta"].get("version"))
    except Exception:
        log.exception("Could not load model artifacts")
    return _state["model"] is not None


def _bad_request(message):
    return jsonify(error="Bad Request", message=message), 400


@app.get("/health")
def health():
    loaded = _load()
    return jsonify(
        status="ok",
        uptime_seconds=round(time.time() - START_TIME, 1),
        model_loaded=loaded,
        model_version=_state["meta"].get("version") if loaded else None,
    )


@app.post("/predict")
def predict():
    if not _load():
        return jsonify(error="Service Unavailable", message="No trained model available yet"), 503
    payload = request.get_json(silent=True)
    if payload is None and request.get_data():
        return _bad_request("Request body must be valid JSON")
    payload = payload or {}
    if not isinstance(payload, dict):
        return _bad_request("JSON body must be an object")

    days = payload.get("forecast_days", 7)
    if isinstance(days, bool) or not isinstance(days, int) or not 1 <= days <= MAX_DAYS:
        return _bad_request(f"forecast_days must be an integer between 1 and {MAX_DAYS}")

    history = payload.get("history")
    today = datetime.now(timezone.utc).date()
    if history is None:
        closes = _state["closes"]
        start = datetime.fromisoformat(_state["meta"]["last_date"]).date() + timedelta(days=1)
    else:
        ok = isinstance(history, list) and len(history) >= MIN_HISTORY
        ok = ok and all(
            isinstance(v, (int, float)) and not isinstance(v, bool) and v > 0 for v in history
        )
        if not ok:
            return _bad_request(f"history must be a list of >= {MIN_HISTORY} positive numbers")
        closes, start = history, today

    preds = forecast_closes(_state["model"], closes, days)
    return jsonify(
        model_version=_state["meta"]["version"],
        currency="USD",
        forecast=[
            {"date": (start + timedelta(days=i)).isoformat(), "predicted_close": round(p, 2)}
            for i, p in enumerate(preds)
        ],
    )


@app.get("/metrics")
def metrics():
    if not _load():
        return jsonify(error="Service Unavailable", message="No trained model available yet"), 503
    return jsonify(model_version=_state["meta"]["version"], metrics=_state["metrics"])


@app.post("/admin/reload")
def reload_model():
    """Called by the Airflow DAG after retraining. Protected by the RELOAD_TOKEN secret."""
    expected = os.getenv("RELOAD_TOKEN", "")
    supplied = request.headers.get("X-Reload-Token", "")
    if not expected or not hmac.compare_digest(expected, supplied):
        return jsonify(error="Forbidden", message="Invalid reload token"), 403
    loaded = _load(force=True)
    return jsonify(reloaded=loaded, model_version=_state["meta"].get("version"))


@app.errorhandler(Exception)
def handle_error(exc):
    if isinstance(exc, HTTPException):
        return jsonify(error=exc.name, message=exc.description), exc.code
    log.exception("Unhandled error")
    return jsonify(error="Internal Server Error", message="Unexpected server error"), 500


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", "5000")))
