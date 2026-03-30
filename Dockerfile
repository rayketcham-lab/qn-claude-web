FROM python:3.12-slim

# Install system dependencies
# curl is needed for the HEALTHCHECK
# tmux is needed for persistent terminal sessions
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        curl \
        tmux \
    && rm -rf /var/lib/apt/lists/*

# Create non-root user for runtime
RUN groupadd -r app && useradd -r -g app -d /home/app -m app

WORKDIR /app

# Copy vendored Python dependencies first (layer-cache friendly)
COPY --chown=app:app vendor/ vendor/

# Copy application source
COPY --chown=app:app app.py requirements.txt ./
COPY --chown=app:app static/ static/
COPY --chown=app:app templates/ templates/

# Copy service/startup helpers (referenced by install paths; not used at runtime
# inside the container but kept for parity with the bare-metal layout)
COPY --chown=app:app qn-code-assistant.service start.sh ./

# Pre-create runtime directories with correct ownership
RUN mkdir -p sessions backups certs user-data \
    && chown -R app:app sessions backups certs user-data \
    && chmod 750 sessions backups certs

# Switch to non-root user
USER app

EXPOSE 5001

# Health check — polls the /api/health endpoint every 30 s
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:5001/api/health || exit 1

ENV PYTHONUNBUFFERED=1

CMD ["python3", "app.py"]
