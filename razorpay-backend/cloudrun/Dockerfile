# Legendary Branding — Razorpay Cloud Run Backend
# Base: Python 3.12 slim (minimal attack surface)

FROM python:3.12-slim

# Non-root user for security
RUN adduser --disabled-password --gecos "" appuser

WORKDIR /app

# Install deps first (layer cache optimization)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy app
COPY main.py .
COPY sftp/ ./sftp/

# Switch to non-root
USER appuser

# Cloud Run injects PORT env var
ENV PORT=8080

# Gunicorn: 2 workers, 4 threads each — lightweight for Cloud Run min=1 instance
CMD ["gunicorn", "--bind", "0.0.0.0:8080", "--workers", "2", "--threads", "4", "--timeout", "30", "main:app"]
