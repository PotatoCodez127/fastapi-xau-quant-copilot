# Dockerfile
# ==========================================
# STAGE 1: Compilation Builder Engine
# ==========================================
FROM python:3.11-slim AS builder

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    POETRY_HOME="/opt/poetry" \
    POETRY_VIRTUALENVS_IN_PROJECT=true \
    POETRY_NO_INTERACTION=1

# Install building tools required for heavy C-extension compilations (e.g., chromadb/hnswlib)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    gcc \
    g++ \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install deterministic package manager
RUN curl -sSL https://install.python-poetry.org | python3 -
ENV PATH="$POETRY_HOME/bin:$PATH"

WORKDIR /build

# Copy configuration bounds to pre-build dependency layers
COPY pyproject.toml ./
RUN poetry install --no-root --only main

# ==========================================
# STAGE 2: Lightweight Production Runtime
# ==========================================
FROM python:3.11-slim AS runner

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PATH="/app/.venv/bin:$PATH"

WORKDIR /app

# Install runtime system level library constraints
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Create dedicated non-root execution user profile
RUN groupadd -g 10001 quant && \
    useradd -u 10001 -g quant -m -s /bin/bash quantuser

# Copy virtual environment layer from the build step
COPY --from=builder /build/.venv /app/.venv

# Copy system components and static interface layouts
COPY config.py main.py ./
COPY src/ ./src/
COPY templates/ ./templates/

# Provision isolated persistent volumes with strict permission scopes
RUN mkdir -p /app/data && chown -R quantuser:quant /app/data

USER quantuser

EXPOSE 5000

HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:5000/ || exit 1

ENTRYPOINT ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "5000"]