FROM node:20.18.1-bookworm-slim@sha256:b2c8e0eb8a6aeeae33b2711f8f516003e27ee45804e270468d937b3214f2f0cc AS web
WORKDIR /build/frontend
COPY frontend/package*.json ./
RUN npm ci --ignore-scripts --no-audit --no-fund
COPY frontend/ ./
RUN npm run build
WORKDIR /build/mcp
COPY adapters/playwright-mcp/package*.json ./
RUN npm ci --ignore-scripts --no-audit --no-fund

FROM python:3.11.11-slim-bookworm@sha256:081075da77b2b55c23c088251026fb69a7b2bf92471e491ff5fd75c192fd38e5
RUN apt-get update && apt-get install -y --no-install-recommends chromium nodejs ca-certificates && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY requirements-browser-use.lock ./
RUN pip install --no-cache-dir -r requirements-browser-use.lock
COPY workbench/ workbench/
COPY portal/ portal/
COPY fixtures/ fixtures/
COPY --from=web /build/frontend/dist/ frontend/dist/
COPY --from=web /build/mcp/node_modules/ adapters/playwright-mcp/node_modules/
COPY adapters/playwright-mcp/server.cjs adapters/playwright-mcp/server.cjs
RUN useradd --uid 10001 --create-home workbench && mkdir /data && chown workbench:workbench /data
USER workbench
ENV CHROMIUM_PATH=/usr/bin/chromium ANONYMIZED_TELEMETRY=false PYTHONUNBUFFERED=1
EXPOSE 18120
CMD ["python","-m","workbench.server","--host","0.0.0.0","--port","18120","--database","/data/workbench.db"]
