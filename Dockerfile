# Build stage
FROM python:3.12-slim AS builder

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    UV_COMPILE_BYTECODE=1

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    ca-certificates \
    git \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

RUN curl -LsSf https://astral.sh/uv/install.sh | sh
ENV PATH="/root/.local/bin:$PATH"

COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

COPY . .
RUN uv sync --frozen --no-dev

# Runtime stage
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PATH="/app/.venv/bin:$PATH" \
    NEXUS_HOME=/data/.nexus

WORKDIR /app

# Install runtime dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Create non-root user
RUN groupadd -g 1000 nexus && \
    useradd -u 1000 -g nexus -s /bin/sh -m nexus && \
    mkdir -p /data/.nexus && \
    chown -R nexus:nexus /app /data

COPY --from=builder --chown=nexus:nexus /app/.venv /app/.venv
COPY --from=builder --chown=nexus:nexus /app /app

USER nexus

VOLUME ["/data"]
EXPOSE 8516 9192

# Entrypoint for CLI usage
CMD ["python", "scripts/engine/nexus_cli.py", "status"]
