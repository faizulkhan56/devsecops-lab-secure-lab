# SECURE Dockerfile — Production-ready
# Multi-stage build, slim base, non-root user

# --- Stage 1: Builder ---
FROM python:3.11-slim AS builder

WORKDIR /build

COPY requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

# --- Stage 2: Runtime ---
FROM python:3.11-slim

# Security: Create non-root user
RUN groupadd -r appuser && useradd -r -g appuser -d /app -s /sbin/nologin appuser

WORKDIR /app

# Copy only installed packages from builder
COPY --from=builder /install /usr/local

# Copy only application code (not .env, .git, etc. — handled by .dockerignore)
COPY app.py .

# Security: Switch to non-root user
USER appuser

EXPOSE 5000

# Health check: 127.0.0.1 avoids IPv6 localhost quirks; urlopen timeout avoids hanging workers.
# start-period allows init_db retries before marking unhealthy.
HEALTHCHECK --interval=30s --timeout=5s --start-period=60s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:5000/api/health', timeout=4)" || exit 1

# --timeout/--preload: fewer WORKER TIMEOUT "no URI read" issues; single init_db before fork.
CMD ["gunicorn", "--bind", "0.0.0.0:5000", "--workers", "2", "--timeout", "120", "--graceful-timeout", "30", "--preload", "app:app"]
