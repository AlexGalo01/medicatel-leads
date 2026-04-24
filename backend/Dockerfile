FROM python:3.12-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# Node.js (para OpenCLI) + Chromium (OpenCLI lo usa vía CDP) + build-essential.
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    ca-certificates \
    gnupg \
    chromium \
    && curl -fsSL https://deb.nodesource.com/setup_22.x | bash - \
    && apt-get install -y --no-install-recommends nodejs \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml /app/pyproject.toml
COPY src /app/src

RUN pip install --upgrade pip && pip install .

# OpenCLI: adapters determinísticos para Google Search / Maps / directorios.
RUN npm install -g @jackwener/opencli

RUN useradd --create-home --shell /bin/bash appuser
RUN mkdir -p /app/exports /data/chrome-profile && chown -R appuser:appuser /app /data
USER appuser

EXPOSE 8000

CMD ["uvicorn", "mle.api.app:app", "--host", "0.0.0.0", "--port", "8000"]
