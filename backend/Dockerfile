FROM python:3.12-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# System deps: build tools + Node.js (no apt chromium — playwright manages its own below)
RUN --mount=type=cache,target=/var/cache/apt,sharing=locked \
    --mount=type=cache,target=/var/lib/apt,sharing=locked \
    apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    ca-certificates \
    gnupg \
    && curl -fsSL https://deb.nodesource.com/setup_22.x | bash - \
    && apt-get install -y --no-install-recommends nodejs

# uv: much faster than pip
RUN pip install --no-cache-dir uv

# --- Python deps layer (cached until pyproject.toml changes) ---
COPY pyproject.toml .
# Stub src so setuptools can resolve the package, then install all dependencies
RUN mkdir -p src/mle && touch src/mle/__init__.py \
    && uv pip install --system --no-cache .

# Copy real source and re-install only the local package (deps already cached above)
COPY src /app/src
RUN uv pip install --system --no-cache --no-deps .

# --- Node/npm layer for playwright_tool (cached until package-lock.json changes) ---
COPY playwright_tool/package.json playwright_tool/package-lock.json /app/playwright_tool/
RUN --mount=type=cache,target=/root/.npm \
    cd /app/playwright_tool && npm ci --omit=dev

COPY playwright_tool /app/playwright_tool
RUN cd /app/playwright_tool && npm run build && chmod +x /app/playwright_tool/bin/mle-search

# Single Chromium install via Playwright (includes all system deps via --with-deps)
# Symlink to /usr/bin/chromium so playwright_tool finds it at its hardcoded default path
ENV PLAYWRIGHT_BROWSERS_PATH=/ms-playwright
RUN python -m playwright install chromium --with-deps \
    && ln -s "$(find /ms-playwright -name 'chrome' -type f | head -1)" /usr/bin/chromium

RUN useradd --create-home --shell /bin/bash appuser
RUN mkdir -p /app/exports /data/chrome-profile && chown -R appuser:appuser /app /data
USER appuser

EXPOSE 8000

CMD ["uvicorn", "mle.api.app:app", "--host", "0.0.0.0", "--port", "8000"]
