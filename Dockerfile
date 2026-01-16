# syntax=docker/dockerfile:1
FROM python:3.11-slim-bookworm

# WeasyPrint requires these system libraries (Cairo, Pango, GDK-Pixbuf)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    python3-dev \
    libcairo2 \
    libcairo2-dev \
    libpango-1.0-0 \
    libpango1.0-dev \
    libpangocairo-1.0-0 \
    libgdk-pixbuf-2.0-0 \
    libgdk-pixbuf-2.0-dev \
    libffi-dev \
    shared-mime-info \
    curl \
    ca-certificates \
    gnupg \
    && rm -rf /var/lib/apt/lists/*

# Install Node.js 20.x via NodeSource
RUN mkdir -p /etc/apt/keyrings \
    && curl -fsSL https://deb.nodesource.com/gpgkey/nodesource-repo.gpg.key | gpg --dearmor -o /etc/apt/keyrings/nodesource.gpg \
    && echo "deb [signed-by=/etc/apt/keyrings/nodesource.gpg] https://deb.nodesource.com/node_20.x nodistro main" > /etc/apt/sources.list.d/nodesource.list \
    && apt-get update \
    && apt-get install -y nodejs \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python dependencies directly (faster rebuild when only code changes)
RUN pip install --no-cache-dir \
    "fastapi>=0.109.0" \
    "uvicorn[standard]>=0.27.0" \
    "sqlalchemy>=2.0.25" \
    "aiosqlite>=0.19.0" \
    "weasyprint>=60.1" \
    "pydantic>=2.5.0" \
    "python-multipart>=0.0.6" \
    "jinja2>=3.1.3" \
    "pydantic-settings>=2.1.0"

# Copy backend code
COPY invoicely/ ./invoicely/

# Copy frontend and build
COPY frontend/package.json ./frontend/
RUN --mount=type=cache,target=/root/.npm \
    cd frontend && npm install --prefer-offline

COPY frontend/ ./frontend/
RUN cd frontend && npm run build

# Copy built frontend to static directory
RUN mkdir -p invoicely/static && \
    cp -r frontend/dist/* invoicely/static/

# Create data directory
RUN mkdir -p /app/data/pdfs /app/data/logos

# Expose port
EXPOSE 8080

# Health check
HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8080/health')"

# Run the application
CMD ["uvicorn", "invoicely.main:app", "--host", "0.0.0.0", "--port", "8080"]
