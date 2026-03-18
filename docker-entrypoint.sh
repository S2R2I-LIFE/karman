#!/bin/bash
# Kármán Docker Entrypoint Script

set -e

echo "========================================"
echo "Kármán Container Starting"
echo "========================================"

# Environment variables
DB_PATH="${DATABASE_PATH:-/app/data/custom-cvp.db}"
DB_DIR="$(dirname "$DB_PATH")"

# Ensure data directory exists
if [ ! -d "$DB_DIR" ]; then
    echo "[INIT] Creating data directory: $DB_DIR"
    mkdir -p "$DB_DIR"
fi

# Try to fix permissions (will fail if not writable, but that's ok)
echo "[INIT] Checking directory permissions..."
chmod 777 "$DB_DIR" 2>/dev/null || echo "[INIT] Warning: Could not set data directory permissions (may need host-side fix)"
chmod 777 /app/logs 2>/dev/null || echo "[INIT] Warning: Could not set logs directory permissions (may need host-side fix)"
chmod 777 /app/output 2>/dev/null || echo "[INIT] Warning: Could not set output directory permissions (may need host-side fix)"

# Check if database is writable
if [ -f "$DB_PATH" ]; then
    if [ ! -w "$DB_PATH" ]; then
        echo "[INIT] ERROR: Database file is not writable!"
        echo "[INIT] Run on host: sudo chmod 666 $DB_PATH"
        echo "[INIT] Or: sudo chown -R 1000:1000 /opt/unetlab/custom-cvp/data"
    fi
fi

# Check if database exists
if [ ! -f "$DB_PATH" ]; then
    echo "[INIT] Database not found at: $DB_PATH"
    echo "[INIT] Checking for database in /app root..."

    if [ -f "/app/custom-cvp.db" ]; then
        echo "[INIT] Found database in /app, copying to data directory..."
        cp /app/custom-cvp.db "$DB_PATH"
        echo "[INIT] Database copied successfully"
    else
        echo "[INIT] No existing database found"
        echo "[INIT] Database will be created on first run"
    fi
else
    echo "[INIT] Database found at: $DB_PATH"
    DB_SIZE=$(stat -f%z "$DB_PATH" 2>/dev/null || stat -c%s "$DB_PATH" 2>/dev/null || echo "unknown")
    echo "[INIT] Database size: $DB_SIZE bytes"
fi

# Ensure output directories exist
echo "[INIT] Creating output directories..."
mkdir -p /app/output/generated-configs
mkdir -p /app/logs

# Set permissions
chmod 755 /app/output /app/output/generated-configs /app/logs 2>/dev/null || true

# Display configuration
echo ""
echo "========================================"
echo "Configuration:"
echo "========================================"
echo "Database:     $DB_PATH"
echo "Output:       /app/output/generated-configs"
echo "Logs:         /app/logs"
echo "Flask Env:    ${FLASK_ENV:-production}"
echo "Workers:      ${GUNICORN_WORKERS:-4}"
echo "========================================"
echo ""

# Wait for any database locks to clear
sleep 2

# Execute the main command
echo "[INIT] Starting application..."
echo "[INIT] Note: First user to register will be granted administrator access"
exec "$@"
