#!/bin/bash
# Kármán Web Interface Startup Script

# Colors for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

echo -e "${GREEN}=====================================${NC}"
echo -e "${GREEN}  Kármán Web Interface Startup  ${NC}"
echo -e "${GREEN}=====================================${NC}"
echo ""

# Check if Python 3 is installed
if ! command -v python3 &> /dev/null; then
    echo -e "${RED}Error: Python 3 is not installed${NC}"
    exit 1
fi

# Check if required packages are installed
echo -e "${YELLOW}Checking dependencies...${NC}"
python3 -c "import flask" 2>/dev/null
if [ $? -ne 0 ]; then
    echo -e "${YELLOW}Flask not found. Installing dependencies...${NC}"
    pip3 install -r requirements.txt
fi

# Set environment variables if not already set
if [ -z "$SECRET_KEY" ]; then
    export SECRET_KEY=$(python3 -c "import secrets; print(secrets.token_hex(32))")
    echo -e "${YELLOW}Generated new SECRET_KEY${NC}"
fi

# Default to development mode unless specified
if [ -z "$FLASK_ENV" ]; then
    export FLASK_ENV=development
fi

# Check if database exists
if [ ! -f "custom-cvp.db" ]; then
    echo -e "${YELLOW}Database not found. Initializing...${NC}"
    python3 cli/orchestrator_cli.py inventory list > /dev/null 2>&1
fi

# Start the web server
echo ""
echo -e "${GREEN}Starting Kármán Web Interface...${NC}"
echo -e "${GREEN}URL: http://localhost:5000${NC}"
echo -e "${GREEN}Press Ctrl+C to stop${NC}"
echo ""

# Run from project root to ensure correct paths
python3 web/app.py
