# ── Stage 1: Build deps ──────────────────────────────────────────────
FROM python:3.12-slim AS builder

ENV PYTHONDONTWRITEBYTECODE=1

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir uv

# Install Python deps (cached until pyproject.toml changes)
COPY pyproject.toml .
RUN mkdir -p src/mle && touch src/mle/__init__.py \
    && uv pip install --system --no-cache .

# Install actual source
COPY src /app/src
RUN uv pip install --system --no-cache --no-deps .

# ── Stage 2: Playwright browser (rarely changes) ────────────────────
FROM python:3.12-slim AS playwright

ENV PLAYWRIGHT_BROWSERS_PATH=/ms-playwright

# Install playwright package + chromium + system deps in one layer
RUN pip install --no-cache-dir playwright \
    && python -m playwright install chromium --with-deps \
    && rm -rf /var/lib/apt/lists/* /root/.cache

# ── Stage 3: Runtime ─────────────────────────────────────────────────
FROM python:3.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PLAYWRIGHT_BROWSERS_PATH=/ms-playwright

WORKDIR /app

# Copy Playwright browser + system deps (cached — almost never changes)
COPY --from=playwright /ms-playwright /ms-playwright
COPY --from=playwright /usr/lib /usr/lib

# Copy installed Python packages from builder
COPY --from=builder /usr/local/lib/python3.12/site-packages /usr/local/lib/python3.12/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

# Non-root user
RUN useradd --create-home --shell /bin/bash appuser \
    && mkdir -p /app/exports /data/chrome-profile \
    && chown -R appuser:appuser /app /data

USER appuser

EXPOSE 8000

CMD ["uvicorn", "mle.api.app:app", "--host", "0.0.0.0", "--port", "8000"]
