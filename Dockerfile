# Multi-stage build for Python API using approved Ubuntu 24.04 base
FROM ubuntu:24.04 as builder

# Install system dependencies for building including Python 3.13
RUN apt-get update && apt-get install -y \
    software-properties-common \
    && add-apt-repository ppa:deadsnakes/ppa \
    && apt-get update \
    && apt-get install -y \
    python3.13 \
    python3.13-dev \
    python3.13-venv \
    python3-pip \
    build-essential \
    git \
    pkg-config \
    libpq-dev \
    libsndfile1-dev \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/*

# Create and activate virtual environment with Python 3.13
RUN python3.13 -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Set working directory
WORKDIR /app

# Copy requirements and source code for installation
COPY pyproject.toml /app/
COPY ambient_scribe /app/ambient_scribe/
RUN pip install --no-cache-dir --upgrade pip setuptools wheel
RUN pip install --no-cache-dir -e .

# Production stage using approved Ubuntu 24.04 base
FROM ubuntu:24.04

# Install runtime dependencies including Python 3.13
RUN apt-get update && apt-get install -y \
    software-properties-common \
    && add-apt-repository ppa:deadsnakes/ppa \
    && apt-get update \
    && apt-get install -y \
    python3.13 \
    python3.13-venv \
    libsndfile1 \
    libpq-dev \
    ffmpeg \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Create non-root user
RUN groupadd -r appuser && useradd -r -g appuser appuser

# Copy virtual environment from builder
COPY --from=builder /opt/venv /opt/venv

# Set environment variables
ENV PATH="/opt/venv/bin:$PATH"
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

# Set working directory
WORKDIR /app

# Copy application code
COPY ambient_scribe /app/ambient_scribe/
COPY templates /app/templates/
COPY alembic /app/alembic/
COPY alembic.ini /app/alembic.ini

# Create necessary directories and set permissions
RUN mkdir -p /app/uploads /app/logs \
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
