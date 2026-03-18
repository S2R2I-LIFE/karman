#!/bin/bash
# Kármán Web Interface - Production Startup with Gunicorn

# Colors for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

echo -e "${GREEN}=====================================================${NC}"
echo -e "${GREEN}  Kármán Web Interface (Production Mode)        ${NC}"
echo -e "${GREEN}=====================================================${NC}"
echo ""

# Check if gunicorn is installed
if ! command -v gunicorn &> /dev/null; then
    echo -e "${YELLOW}Installing gunicorn...${NC}"
    pip3 install gunicorn
fi

# Check if .env file exists
if [ -f ".env" ]; then
    echo -e "${GREEN}Loading environment from .env${NC}"
    export $(cat .env | xargs)
else
    echo -e "${YELLOW}No .env file found. Using defaults${NC}"
    if [ -z "$SECRET_KEY" ]; then
        export SECRET_KEY=$(python3 -c "import secrets; print(secrets.token_hex(32))")
    fi
fi

# Set production environment
export FLASK_ENV=production

# Configuration
WORKERS=${WORKERS:-4}
BIND_ADDRESS=${BIND_ADDRESS:-0.0.0.0:5000}
LOG_LEVEL=${LOG_LEVEL:-info}

echo ""
echo -e "${GREEN}Starting Kármán with Gunicorn...${NC}"
echo -e "${GREEN}Workers: $WORKERS${NC}"
echo -e "${GREEN}Binding to: $BIND_ADDRESS${NC}"
echo -e "${GREEN}Log level: $LOG_LEVEL${NC}"
echo ""

# Start gunicorn
cd web
gunicorn \
    --workers $WORKERS \
    --bind $BIND_ADDRESS \
    --log-level $LOG_LEVEL \
    --access-logfile ../logs/access.log \
    --error-logfile ../logs/error.log \
    --timeout 120 \
    app:app
