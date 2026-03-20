# =============================================================================
# NEXUS — Multi-stage Dockerfile
# =============================================================================
# For future containerized / prod deployments. No GPU dependencies.
# Build:  docker build -t nexus .
# Run:    docker run -p 8000:8000 --env-file .env nexus
# =============================================================================

# ---------------------------------------------------------------------------
# Stage 1: Builder — install Python dependencies with uv
# ---------------------------------------------------------------------------
FROM python:3.12-slim AS builder

# System deps required for building Python packages
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Install uv (fast Python package manager)
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

WORKDIR /build

# Copy dependency specification first (cache layer)
COPY pyproject.toml ./
COPY README.md* ./

# Create venv and install deps
RUN uv venv /opt/venv
ENV VIRTUAL_ENV=/opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Install CPU-only PyTorch + torchvision first (no CUDA bloat — saves ~2GB)
# Pin versions to avoid transformers/torchvision compatibility issues
RUN uv pip install --no-cache \
    "torch==2.6.0+cpu" "torchvision==0.21.0+cpu" \
    --index-url https://download.pytorch.org/whl/cpu

# Install project deps (torch already satisfied from CPU index above)
RUN uv pip install --no-cache .

# ---------------------------------------------------------------------------
# Stage 2: Runtime — lean production image
# ---------------------------------------------------------------------------
FROM python:3.12-slim AS runtime

# Runtime system deps only
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy installed Python environment from builder
COPY --from=builder /opt/venv /opt/venv
ENV VIRTUAL_ENV=/opt/venv
ENV PATH="/opt/venv/bin:$PATH"
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

WORKDIR /app

# Copy application code
COPY app/ ./app/
COPY workers/ ./workers/
COPY migrations/ ./migrations/
COPY scripts/ ./scripts/
COPY alembic.ini* ./

# Non-root user for security
RUN useradd --create-home --shell /bin/bash nexus
USER nexus

EXPOSE 8000

# Default: run the FastAPI server
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
