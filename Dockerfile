# GCP Bot — Cloud Run Dockerfile
FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Cloud Run sets PORT env variable (default 8080)
ENV PORT=8080

# Run uvicorn on the PORT provided by Cloud Run
CMD uvicorn api.main:app --host 0.0.0.0 --port $PORT
