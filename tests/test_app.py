
def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200
    body = r.get_json()
    assert body["status"] == "ok"
    assert body["model_loaded"] is True
    assert body["model_version"]
    assert body["uptime_seconds"] >= 0


def test_predict_default_returns_7_days(client):
    r = client.post("/predict")
    assert r.status_code == 200
    forecast = r.get_json()["forecast"]
    assert len(forecast) == 7
    assert all(f["predicted_close"] > 0 for f in forecast)
    dates = [f["date"] for f in forecast]
    assert dates == sorted(dates)


def test_predict_custom_days(client):
    r = client.post("/predict", json={"forecast_days": 3})
    assert r.status_code == 200
    assert len(r.get_json()["forecast"]) == 3


def test_predict_custom_history(client):
    r = client.post("/predict", json={"history": [40000 + i * 10 for i in range(40)]})
    assert r.status_code == 200
    assert len(r.get_json()["forecast"]) == 7


def test_predict_invalid_days(client):
    for bad in [0, 31, "7", True, 2.5]:
        r = client.post("/predict", json={"forecast_days": bad})
        assert r.status_code == 400, bad


def test_predict_invalid_json(client):
    r = client.post("/predict", data="{not json", content_type="application/json")
    assert r.status_code == 400


def test_predict_invalid_history(client):
    assert client.post("/predict", json={"history": [1, 2, 3]}).status_code == 400
    assert client.post("/predict", json={"history": ["a"] * 40}).status_code == 400
    assert client.post("/predict", json=[1, 2]).status_code == 400


def test_metrics(client):
    r = client.get("/metrics")
    assert r.status_code == 200
    m = r.get_json()["metrics"]
    assert {"mae", "rmse", "mape"} <= set(m)


def test_unknown_route_is_json_404(client):
    r = client.get("/nope")
    assert r.status_code == 404
    assert r.get_json()["error"] == "Not Found"


def test_reload_requires_token(client):
    assert client.post("/admin/reload").status_code == 403
    r = client.post("/admin/reload", headers={"X-Reload-Token": "test-token"})
    assert r.status_code == 200
    assert r.get_json()["reloaded"] is True


def test_no_model_returns_503(empty_client):
    assert empty_client.post("/predict").status_code == 503
    assert empty_client.get("/metrics").status_code == 503
    assert empty_client.get("/health").get_json()["model_loaded"] is False
