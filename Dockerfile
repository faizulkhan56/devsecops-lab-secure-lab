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

# Health check
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:5000/api/health')" || exit 1

# Production server (no debug mode)
CMD ["gunicorn", "--bind", "0.0.0.0:5000", "--workers", "2", "app:app"]
