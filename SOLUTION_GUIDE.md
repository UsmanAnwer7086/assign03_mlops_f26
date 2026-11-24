# Assignment 3 – Step-by-Step Solution Guide

Replace `YOUR_DOCKERHUB_USER` / `YOUR_GH_USER` everywhere (search the repo for it).
**Before your first commit run `pip install -r requirements-dev.txt && black . && flake8 .`** so the CI lint step passes.

## Architecture
```
yfinance/Binance -> [Airflow DAG: fetch -> features -> train+evaluate -> gate -> reload API]
                                         |                     |
                                  models/ (PVC)  <---- reads ---- Flask API x N pods (Gunicorn)
GitHub push -> Actions: black/flake8/pytest -> build image -> push Docker Hub -> K8s pulls image
Client -> Ingress (btc-forecast.local) -> Service :80 -> Pods :5000   (HPA scales 2-8 pods)
```
Model: XGBoost on scale-free return features, recursive 7-day forecast (`src/features.py`).
Validation = forecast the last 7 known days; the model is only registered if MAPE <= `MAPE_THRESHOLD` (default 15).

## Repo map -> marks
| Part | Files |
|---|---|
| A (10) | `app/app.py`, `tests/` |
| B (10) | `app/Dockerfile`, `docker-compose.yml`, `.github/workflows/ci_cd.yml` |
| C (12) | `dags/btc_etl_pipeline.py`, `kubeflow/btc_kfp_pipeline.py`, `src/` |
| D (18) | `k8s/*.yaml` |
| E (10) | chaos test, E2E check, PDF report |

---
## Step 1 – Local setup (Day 1)
```bash
python -m venv .venv && source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -r requirements.txt -r requirements-dev.txt
git init && git remote add origin https://github.com/YOUR_GH_USER/btc-mlops.git
```

## Step 2 – Get data and train once (Day 1)
```bash
python -m src.etl_fetch        # -> data/raw/btc_usd.csv   (yfinance, Binance fallback)
python -m src.preprocess       # -> data/processed/btc_features.csv
python -m src.train_forecast   # -> models/{model.joblib,meta.json,metrics.json,closes.json}
```
The last command prints `{"passed": true, "metrics": {...}}`. If `passed` is false, raise `MAPE_THRESHOLD` or tune `make_model()`.

## Step 3 – Run and test the API (Part A, Day 2)
```bash
pytest -v                                              # screenshot this
python app/app.py &                                    # dev server, or:
cd app && PYTHONPATH=.. gunicorn --bind 0.0.0.0:5000 app:app
curl localhost:5000/health
curl -X POST localhost:5000/predict -H 'Content-Type: application/json' -d '{"forecast_days":7}'
curl localhost:5000/metrics
curl -X POST localhost:5000/predict -d '{"forecast_days":99}' -H 'Content-Type: application/json'   # 400 demo
```
Endpoints: `/health` (status, uptime, model version), `/predict` (optional `forecast_days` 1–30 or custom `history` list), `/metrics` (MAE/RMSE/MAPE), `/admin/reload` (token-protected; used by Airflow).
Error handling: 400 for bad input, 503 if no model yet, 500 for unexpected errors – all JSON.

## Step 4 – Docker image (Part B1, Day 3)
```bash
docker build -f app/Dockerfile -t btc-forecast:local .     # build from repo ROOT
docker images btc-forecast:local                           # screenshot: image size
docker run --rm -p 5000:5000 -v "$PWD/models:/app/models" btc-forecast:local
```
Report talking points: multi-stage (deps built in a venv, only the venv is copied), `python:3.10-slim`, requirements copied first for layer caching, non-root UID 10001, HEALTHCHECK, `exec gunicorn`.

## Step 4b – docker-compose (Part B2)
```bash
mkdir -p data models && chmod -R 777 data models
docker compose up --build -d
docker compose logs airflow | grep -i password             # Airflow admin login (user: admin) at :8080
```
API on `:5000`, Airflow on `:8080`, Postgres is Airflow's metadata DB.

## Step 5 – Airflow DAG (Part C1, Day 4–5)
1. Open http://localhost:8080, log in, un-pause `btc_etl_pipeline`.
2. Click **Trigger DAG**. Tasks: `fetch_data -> preprocess_features -> train_and_evaluate -> check_threshold -> reload_api_model`.
3. Screenshot the **Graph** view (all green) and the `reload_api_model` task log.
4. Verify: `curl localhost:5000/health` – `model_version` changed (the API also auto-detects new artifacts via `meta.json` mtime, so every replica picks up the new model even if only one receives the reload call).

`ShortCircuitOperator` is the "performance passes threshold" gate – if validation fails, nothing is registered and the API keeps the old model.

## Step 6 – Kubeflow pipeline (Part C2, Day 5)
```bash
pip install kfp==2.8.0
KFP_IMAGE=YOUR_DOCKERHUB_USER/btc-forecast:latest python kubeflow/btc_kfp_pipeline.py
# -> btc_kfp_pipeline.yaml  (commit this file, screenshot the compile output)
```
Three container components (ingest, features, train) pass `Dataset`/`Model` artifacts. Optional: upload the YAML in a Kubeflow UI and create a **recurring run** for the schedule.

## Step 7 – GitHub Actions CI/CD (Part B3/B4, Day 6)
1. Docker Hub -> Account Settings -> Security -> create an **access token**.
2. GitHub repo -> Settings -> Secrets and variables -> Actions -> add `DOCKER_USERNAME` and `DOCKER_PASSWORD` (the token).
3. `git add . && git commit -m "Initial MLOps pipeline" && git push -u origin main`
4. Actions tab: `test` job (black, flake8, pytest) then `build-and-push` (tags: `:<commit-sha>` and `:latest`). Screenshot the green run and the Docker Hub tags page.
5. Make the Docker Hub repo public (deliverable).

## Step 8 – Kubernetes on Minikube (Part D, Day 7–8)
```bash
minikube start --cpus=4 --memory=6g
minikube addons enable ingress
minikube addons enable metrics-server        # required by the HPA
sed -i 's/YOUR_DOCKERHUB_USER/<your-user>/' k8s/deployment.yaml k8s/train-job.yaml

kubectl apply -f k8s/configmap-secret.yaml   # D1
kubectl apply -f k8s/pvc.yaml                # D2
kubectl apply -f k8s/train-job.yaml          # trains the first model INTO the PVC
kubectl wait --for=condition=complete job/btc-initial-train --timeout=600s
kubectl apply -f k8s/deployment.yaml         # D3: 3 replicas, probes, limits
kubectl apply -f k8s/service.yaml            # D4: ClusterIP + NodePort
kubectl apply -f k8s/hpa.yaml                # D5
kubectl apply -f k8s/ingress.yaml            # D6
kubectl get pods,svc,hpa,ingress,pvc         # screenshot
```
Ingress access:
```bash
# Linux:      echo "$(minikube ip) btc-forecast.local" | sudo tee -a /etc/hosts
# Win/macOS (docker driver): run `minikube tunnel` in another terminal and map btc-forecast.local to 127.0.0.1
curl http://btc-forecast.local/health
curl -X POST http://btc-forecast.local/predict
# NodePort alternative:  minikube service btc-forecast-nodeport --url
```
Using a locally built image instead of Docker Hub: `minikube image load btc-forecast:local`, set `image: btc-forecast:local` and `imagePullPolicy: IfNotPresent`.

Why the Job: the PVC starts empty, so without a model `/predict` returns 503. The PVC (mounted at `/app/models`) also stores the raw/processed CSVs (`DATA_DIR=/app/models/data`), so data and model survive pod restarts.

## Step 9 – HPA load test (D5, Day 8)
```bash
pip install locust
# terminal 1
kubectl get hpa --watch
# terminal 2
kubectl get pods -w
# terminal 3
locust -f loadtest/locustfile.py --host http://btc-forecast.local --headless -u 200 -r 20 -t 5m
```
CPU should pass 60% and replicas climb from 2 toward 8; stop the test and replicas scale back down after ~5 minutes. Screenshot the `hpa --watch` output and a Locust chart (run without `--headless` for the web UI at :8089).
(`wrk` alternative: `wrk -t4 -c100 -d120s -s post.lua http://btc-forecast.local/predict`.)

## Step 10 – Chaos / self-healing (E1)
```bash
kubectl get pods
kubectl delete pod <one-pod-name>
kubectl get pods -w          # a replacement is scheduled immediately; ReplicaSet keeps desired count
curl http://btc-forecast.local/health   # keep hitting it: no downtime thanks to the other replicas
```
Also try `kubectl rollout restart deployment/btc-forecast` and `kubectl describe pod` to show probes.

## Step 11 – End-to-end verification (E2)
1. Trigger the Airflow DAG manually (Step 5) and show the new `model_version` in `/health`.
2. Show the green GitHub Actions run (Step 7).
3. `curl -X POST http://btc-forecast.local/predict` -> 7 dated predictions.

Note: Airflow runs in docker-compose, K8s pods have their own PVC. For the report, either (a) show the DAG updating the compose API and the K8s API serving predictions from its own PVC-trained model, or (b) re-run `kubectl delete job btc-initial-train && kubectl apply -f k8s/train-job.yaml` and `kubectl rollout restart` to demonstrate a K8s model refresh. State which one you used.

## Step 12 – PDF report (E3, 4–6 pages, Day 9–10)
| Section | Screenshots / logs |
|---|---|
| 1. Architecture | diagram (draw.io) + model choice and why |
| 2. Part A | `pytest -v`, curl `/health` `/predict` `/metrics`, 400 error demo |
| 3. Part B | `docker build` output + `docker images`, compose `ps`, Actions green run, Docker Hub tags |
| 4. Part C | Airflow graph + task logs, compiled KFP YAML snippet |
| 5. Part D | `kubectl get pods,svc,hpa,ingress,pvc`, `describe deployment` (probes/limits), configmap/secret (values hidden) |
| 6. Autoscaling | `hpa --watch` before/during/after, Locust chart, analysis |
| 7. Resilience | pod deletion log and timeline |
| 8. Performance | MAE/RMSE/MAPE from `/metrics`, forecast table, limitations (BTC is near-random-walk; MAPE is for a 7-day window) |

## Suggested 10-day split (2 students)
| Day | Student A | Student B |
|---|---|---|
| 1–2 | Data + model + training | Flask API + tests |
| 3–4 | Dockerfile + compose | GitHub Actions |
| 5 | Airflow DAG | Kubeflow pipeline |
| 6–7 | ConfigMap/Secret/PVC/Deployment | Service/Ingress/HPA |
| 8 | Load test | Chaos test + E2E |
| 9–10 | Report + README (together) | Report + final repo check |

## Troubleshooting
- **Pods `ImagePullBackOff`**: Docker Hub repo is private or username not replaced; or use `minikube image load`.
- **`/predict` 503**: model not on the PVC yet – check `kubectl logs job/btc-initial-train`.
- **HPA shows `<unknown>`**: metrics-server not ready (`kubectl top pods` must work) and the deployment must define CPU requests (it does).
- **PVC permission denied**: `fsGroup: 10001` is set; on exotic storage classes, run `kubectl exec` and `ls -ld /app/models`.
- **Job can't download data**: cluster has no internet; the Binance fallback is also external – copy a CSV into the PVC instead.
- **Airflow can't write `data/`/`models/`**: `chmod -R 777 data models` on the host.
- **yfinance rate-limited**: the code automatically falls back to the Binance public API.
