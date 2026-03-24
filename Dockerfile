# Kármán - Docker Image
# Multi-stage build for optimized image size

# Stage 1: Base with dependencies
FROM python:3.12-slim as base

# Set working directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    git \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first for better caching
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Stage 2: Application
FROM python:3.12-slim

# Set working directory
WORKDIR /app

# Install runtime dependencies
RUN apt-get update && apt-get install -y \
    curl \
    dnsmasq \
    procps \
    && rm -rf /var/lib/apt/lists/*

# Copy Python dependencies from base stage
COPY --from=base /usr/local/lib/python3.12/site-packages /usr/local/lib/python3.12/site-packages
COPY --from=base /usr/local/bin/pip* /usr/local/bin/
COPY --from=base /usr/local/bin/python* /usr/local/bin/
COPY --from=base /usr/local/bin/gunicorn /usr/local/bin/

# Create application user (non-root for security)
RUN useradd -m -u 1000 cvpuser && \
    mkdir -p /app/data /app/output /app/logs && \
    chown -R cvpuser:cvpuser /app

# Copy application files
COPY . .

# Fix line endings and permissions for shell scripts (as root before switching users)
RUN apt-get update && apt-get install -y dos2unix && \
    find /app -type f -name "*.sh" -exec dos2unix {} \; && \
    find /app -type f -name "*.sh" -exec chmod +x {} \; && \
    rm -rf /var/lib/apt/lists/*

# Verify entrypoint exists and is executable
RUN ls -la /app/docker-entrypoint.sh && \
    test -x /app/docker-entrypoint.sh || (echo "ERROR: Entrypoint not executable" && exit 1)

# Create necessary directories with correct permissions
RUN mkdir -p \
    /app/data \
    /app/output/generated-configs \
    /app/logs \
    /app/web/static \
    /app/web/templates && \
    chown -R cvpuser:cvpuser /app

# Grant dnsmasq the capabilities it needs to run as non-root
# (bind to privileged port 67, raw/broadcast sockets for DHCP)
RUN apt-get update && apt-get install -y libcap2-bin && \
    setcap 'cap_net_bind_service,cap_net_raw,cap_net_admin+ep' /usr/sbin/dnsmasq && \
    rm -rf /var/lib/apt/lists/*

# Switch to non-root user
USER cvpuser

# Expose Flask port
EXPOSE 5000

# Environment variables
ENV FLASK_APP=web/app.py
ENV FLASK_ENV=production
ENV PYTHONUNBUFFERED=1
ENV DATABASE_PATH=/app/data/custom-cvp.db

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD curl -f http://localhost:5000/health || exit 1

# Entrypoint
ENTRYPOINT ["/app/docker-entrypoint.sh"]

# Default command
CMD ["python", "-m", "gunicorn", "--bind", "0.0.0.0:5000", "--workers", "4", "--timeout", "120", "--access-logfile", "/app/logs/access.log", "--error-logfile", "/app/logs/error.log", "web.app:app"]
