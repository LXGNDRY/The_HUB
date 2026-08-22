# ── Stage 1: Build ──
FROM python:3.12-slim AS builder

WORKDIR /app
COPY app/requirements.txt /tmp/hub-requirements.txt
RUN pip install --user --no-cache-dir -r /tmp/hub-requirements.txt

# ── Stage 2: Runtime ──
FROM python:3.12-slim

WORKDIR /app

# Copy installed packages from builder
COPY --from=builder /root/.local /root/.local
ENV PATH=/root/.local/bin:$PATH

RUN groupadd --system hub && useradd --system --gid hub --home-dir /app hub

# Copy application code
COPY . .

# Cloud Run assigns PORT env var (default 8080)
ENV PORT=8080
EXPOSE 8080

USER hub

CMD exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT} --workers 1
