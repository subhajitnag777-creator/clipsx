# syntax=docker/dockerfile:1
FROM python:3.11-slim

# Install system dependencies (FFmpeg, git, build essentials)
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    curl \
    git \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy dependency requirements
COPY requirements.txt .

# Install Python packages
RUN pip install --no-cache-dir -r requirements.txt

# Copy application source
COPY . .

# Environment defaults
ENV PYTHONUNBUFFERED=1 \
    PORT=2100 \
    HOST=0.0.0.0 \
    CLIPSX_FETCH_MODEL=0 \
    CLIPSX_UPDATE_CHECK=0

EXPOSE 2100

# Healthcheck
HEALTHCHECK --interval=30s --timeout=5s --start-period=5s --retries=3 \
    CMD curl -f http://127.0.0.1:2100/healthz || exit 1

# Start Clips X Studio
CMD ["python", "-m", "studio.server"]
