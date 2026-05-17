# syntax=docker/dockerfile:1.6

# ---------- builder ----------
FROM python:3.11-slim AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    UV_LINK_MODE=copy \
    UV_COMPILE_BYTECODE=1

# Install uv
RUN pip install --no-cache-dir uv==0.11.7

WORKDIR /app

# Copy project metadata first for better layer caching
COPY pyproject.toml ./
COPY README.md ./

# Resolve and install dependencies into a project-local venv.
# Pre-install CPU-only torch to avoid pulling nvidia-* (huge, fails on arm64
# without GPU). sentence-transformers will use this build.
RUN uv venv /app/.venv && \
    . /app/.venv/bin/activate && \
    uv pip install --no-cache --index-url https://download.pytorch.org/whl/cpu \
        torch==2.4.1 && \
    uv pip install --no-cache -r pyproject.toml

# Copy source
COPY app ./app
COPY scripts ./scripts
COPY vendor ./vendor

# ---------- runtime ----------
FROM python:3.11-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/app/.venv/bin:$PATH" \
    HF_HOME=/root/.cache/huggingface \
    TRANSFORMERS_OFFLINE=0 \
    OMP_NUM_THREADS=2 \
    TOKENIZERS_PARALLELISM=false

# curl for healthcheck and bash for entrypoint
RUN apt-get update && \
    apt-get install -y --no-install-recommends curl ca-certificates && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy installed venv and source from builder
COPY --from=builder /app/.venv /app/.venv
COPY --from=builder /app/app /app/app
COPY --from=builder /app/scripts /app/scripts
COPY --from=builder /app/vendor /app/vendor
COPY pyproject.toml README.md ./

# Default data dir (mounted as volume)
RUN mkdir -p /app/data

EXPOSE 8000

# uvicorn launches the FastAPI app
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
