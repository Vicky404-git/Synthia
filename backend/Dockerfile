FROM python:3.13-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    HF_HUB_DISABLE_TELEMETRY=1 \
    STT_CACHE_DIR=/home/synthia/.cache/synthia

WORKDIR /app

# curl: container healthcheck. libgomp1: OpenMP runtime required by the
# CTranslate2/ONNX Runtime wheels that back local Faster-Whisper. Audio is
# decoded by PyAV, which ships its own FFmpeg libraries in the wheel.
RUN apt-get update \
    && apt-get install -y --no-install-recommends curl libgomp1 \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app

# Pre-create the model cache owned by the unprivileged user. The model itself is
# NEVER downloaded at build time; it is fetched on first transcription.
RUN useradd --create-home --uid 10001 synthia \
    && mkdir -p /home/synthia/.cache/synthia \
    && chown -R synthia:synthia /app /home/synthia/.cache
USER synthia

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -fsS "http://127.0.0.1:${PORT:-8000}/health" || exit 1

# Bind to 0.0.0.0 and respect the platform-provided PORT (Render, Fly, etc.).
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000} --proxy-headers --forwarded-allow-ips='*'"]
