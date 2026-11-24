import os
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "app"))


def synthetic_df(n=400, seed=0):
    rng = np.random.default_rng(seed)
    close = 30000 * np.exp(np.cumsum(rng.normal(0, 0.02, n)))
    return pd.DataFrame({"Date": pd.date_range("2024-01-01", periods=n), "Close": close})


@pytest.fixture(scope="session")
def client(tmp_path_factory):
    model_dir = tmp_path_factory.mktemp("models")
    os.environ["MODEL_DIR"] = str(model_dir)
    os.environ["N_ESTIMATORS"] = "20"
    os.environ["RELOAD_TOKEN"] = "test-token"
    from src.train_forecast import train_and_register

    result = train_and_register(synthetic_df(), model_dir, mape_threshold=1000)
    assert result["passed"]
    import app as api

    api.app.config["TESTING"] = True
    return api.app.test_client()


@pytest.fixture()
def empty_client(tmp_path, monkeypatch):
    """Client pointing at an empty model dir (no model trained yet)."""
    import app as api

    monkeypatch.setenv("MODEL_DIR", str(tmp_path))
    monkeypatch.setitem(api._state, "model", None)
    monkeypatch.setitem(api._state, "stamp", None)
    return api.app.test_client()
