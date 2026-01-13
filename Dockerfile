# Multi-stage build for Python API using approved Ubuntu 24.04 base
# Build stage
FROM python:3.13.11-slim AS builder

WORKDIR /app

# Install build dependencies
RUN apt-get update && apt-get install -y \
    build-essential \
    git \
    pkg-config \
    libpq-dev \
    libsndfile1-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and source code for installation
COPY pyproject.toml /app/
COPY ambient_scribe /app/ambient_scribe/
RUN pip install --no-cache-dir --upgrade pip setuptools wheel
RUN pip install --no-cache-dir -e .

# Runtime stage
FROM python:3.13.11-slim

# Install runtime dependencies
RUN apt-get update && apt-get install -y \
    libpq5 \
    libsndfile1 \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Copy installed Python packages and executables from builder
COPY --from=builder /usr/local/lib/python3.13/site-packages /usr/local/lib/python3.13/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin
COPY --from=builder /app /app

# Copy additional application files
COPY templates /app/templates/
COPY alembic /app/alembic/
COPY alembic.ini /app/alembic.ini

# Create non-root user and set permissions
RUN groupadd -r appuser && useradd -r -g appuser appuser \
    && mkdir -p /app/uploads /app/logs \
    && chown -R appuser:appuser /app \
    && chmod -R 755 /app

# Switch to non-root user
USER appuser

# Expose port
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD python -c "import requests; requests.get('http://localhost:8000/api/health/', timeout=5)"

# Run the application
CMD ["uvicorn", "ambient_scribe.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "4"]