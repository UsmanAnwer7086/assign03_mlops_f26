# syntax=docker/dockerfile:1
# Build from the repo root:  docker build -f app/Dockerfile -t btc-forecast .

# ---------- Stage 1: build dependencies into a virtualenv ----------
FROM python:3.10-slim AS builder
ENV PIP_NO_CACHE_DIR=1 PIP_DISABLE_PIP_VERSION_CHECK=1
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"
WORKDIR /build
# Copy requirements first so this layer is cached until dependencies change
COPY requirements.txt .
RUN pip install -r requirements.txt

# ---------- Stage 2: slim runtime image ----------
FROM python:3.10-slim AS runtime
# libgomp1 is required by xgboost
RUN apt-get update \
    && apt-get install -y --no-install-recommends libgomp1 \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --system --uid 10001 --no-create-home appuser

ENV PATH="/opt/venv/bin:$PATH" \
    PYTHONPATH=/app \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PORT=5000 \
    MODEL_DIR=/app/models \
    DATA_DIR=/app/models/data

COPY --from=builder /opt/venv /opt/venv
WORKDIR /app
COPY app/app.py ./app.py
COPY src ./src
RUN mkdir -p /app/models && chown -R appuser /app

USER 10001
EXPOSE 5000
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import os,urllib.request as u; u.urlopen('http://localhost:%s/health' % os.environ.get('PORT','5000'), timeout=3)"

CMD ["sh", "-c", "exec gunicorn --bind 0.0.0.0:${PORT} --workers 2 --timeout 60 --access-logfile - app:app"]
