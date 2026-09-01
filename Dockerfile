# syntax=docker/dockerfile:1

# ---------------------------------------------------------------------------
# Stage 1: build the SvelteKit frontend (Node only needed here).
# ---------------------------------------------------------------------------
FROM node:26-slim AS frontend
WORKDIR /app/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN --mount=type=cache,target=/root/.npm npm ci
COPY frontend/ ./
RUN npm run build

# ---------------------------------------------------------------------------
# Stage 2: build Python dependencies into a venv (compilers live here only).
# uv.lock pins every transitive version; --frozen refuses to resolve anew, so
# two builds of the same commit produce the same dependency tree.
# ---------------------------------------------------------------------------
FROM python:3.14-slim-bookworm AS builder
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    python3-dev \
    libffi-dev \
    libcairo2-dev \
    libpango1.0-dev \
    libgdk-pixbuf-2.0-dev \
    && rm -rf /var/lib/apt/lists/*

RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

WORKDIR /app
COPY pyproject.toml uv.lock README.md ./
COPY invoice_machine/ ./invoice_machine/
# uv is pinned to the version that wrote uv.lock (lock format revision 1).
RUN pip install --no-cache-dir uv==0.6.8 \
    && UV_PROJECT_ENVIRONMENT=/opt/venv uv sync --frozen --no-editable

# ---------------------------------------------------------------------------
# Stage 3: slim runtime image (no compilers, no Node, no build cruft).
# ---------------------------------------------------------------------------
FROM python:3.14-slim-bookworm AS runtime

# Runtime-only libraries for WeasyPrint + gosu for privilege drop.
RUN apt-get update && apt-get install -y --no-install-recommends \
    libcairo2 \
    libpango-1.0-0 \
    libpangocairo-1.0-0 \
    libgdk-pixbuf-2.0-0 \
    shared-mime-info \
    ca-certificates \
    gosu \
    && rm -rf /var/lib/apt/lists/*

ENV PATH="/opt/venv/bin:$PATH" \
    PYTHONUNBUFFERED=1
COPY --from=builder /opt/venv /opt/venv

WORKDIR /app
COPY invoice_machine/ ./invoice_machine/
COPY alembic.ini ./
COPY --from=frontend /app/frontend/dist/ ./invoice_machine/static/
COPY docker-entrypoint.sh /usr/local/bin/
RUN chmod +x /usr/local/bin/docker-entrypoint.sh

# Non-root user + data directories.
RUN groupadd --gid 1000 appuser \
    && useradd --uid 1000 --gid appuser --shell /bin/bash --create-home appuser \
    && mkdir -p /app/data/pdfs /app/data/logos /app/data/backups \
    && chown -R appuser:appuser /app/data

EXPOSE 8080

# start-period covers migrations (run in the entrypoint) + FTS rebuild on boot.
HEALTHCHECK --interval=30s --timeout=3s --start-period=20s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8080/health')"

ENTRYPOINT ["docker-entrypoint.sh"]
# Proxy-header flags are added by the entrypoint when TRUST_PROXY_HEADERS is
# on. Single worker: SQLite + the background scheduler assume one process.
# --no-access-log: the app logs one line per request with the request id.
CMD ["uvicorn", "invoice_machine.main:app", "--host", "0.0.0.0", "--port", "8080", "--no-access-log"]
