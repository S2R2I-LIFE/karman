#!/bin/bash
# Kármán - Quick Deployment Script

set -e

# Colors for output
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

echo -e "${BLUE}========================================"
echo "Kármán - Quick Deployment"
echo -e "========================================${NC}"
echo ""

# Check if Docker is installed
if ! command -v docker &> /dev/null; then
    echo -e "${RED}Error: Docker is not installed${NC}"
    echo "Please install Docker first: https://docs.docker.com/engine/install/"
    exit 1
fi

# Check if Docker Compose is installed
if ! command -v docker compose &> /dev/null; then
    echo -e "${RED}Error: Docker Compose is not installed${NC}"
    echo "Please install Docker Compose: https://docs.docker.com/compose/install/"
    exit 1
fi

echo -e "${GREEN}✓ Docker installed:${NC} $(docker --version)"
echo -e "${GREEN}✓ Docker Compose installed:${NC} $(docker compose version)"
echo ""

# Create required directories
echo -e "${BLUE}Creating required directories...${NC}"
mkdir -p data logs output/generated-configs
echo -e "${GREEN}✓ Directories created${NC}"
echo ""

# Check if .env exists
if [ ! -f .env ]; then
    echo -e "${YELLOW}! No .env file found${NC}"
    echo -e "${BLUE}Creating .env from template...${NC}"

    if [ -f .env.example ]; then
        cp .env.example .env

        # Generate random secret key
        SECRET_KEY=$(python3 -c "import secrets; print(secrets.token_hex(32))" 2>/dev/null || openssl rand -hex 32)

        # Update .env with generated secret
        if [ "$(uname)" = "Darwin" ]; then
            # macOS
            sed -i '' "s/SECRET_KEY=.*/SECRET_KEY=$SECRET_KEY/" .env
        else
            # Linux
            sed -i "s/SECRET_KEY=.*/SECRET_KEY=$SECRET_KEY/" .env
        fi

        echo -e "${GREEN}✓ .env file created with random secret key${NC}"
        echo -e "${YELLOW}! Please review and edit .env before deploying to production${NC}"
    else
        echo -e "${RED}Error: .env.example not found${NC}"
        exit 1
    fi
else
    echo -e "${GREEN}✓ .env file exists${NC}"
fi
echo ""

# Check if database exists
if [ ! -f data/custom-cvp.db ]; then
    echo -e "${YELLOW}! Database not found in data/ directory${NC}"

    if [ -f custom-cvp.db ]; then
        echo -e "${BLUE}Copying database from root directory...${NC}"
        cp custom-cvp.db data/custom-cvp.db
        echo -e "${GREEN}✓ Database copied${NC}"
    else
        echo -e "${YELLOW}! No database found - will be created on first run${NC}"
    fi
else
    DB_SIZE=$(du -h data/custom-cvp.db | cut -f1)
    echo -e "${GREEN}✓ Database found:${NC} $DB_SIZE"
fi
echo ""

# Build the container
echo -e "${BLUE}Building Docker container...${NC}"
if docker compose build; then
    echo -e "${GREEN}✓ Container built successfully${NC}"
else
    echo -e "${RED}Error: Failed to build container${NC}"
    exit 1
fi
echo ""

# Start the application
echo -e "${BLUE}Starting Kármán...${NC}"
if docker compose up -d; then
    echo -e "${GREEN}✓ Kármán started${NC}"
else
    echo -e "${RED}Error: Failed to start Kármán${NC}"
    exit 1
fi
echo ""

# Wait for health check
echo -e "${BLUE}Waiting for application to be ready...${NC}"
RETRIES=30
COUNTER=0

while [ $COUNTER -lt $RETRIES ]; do
    if curl -s -f http://localhost:5000/health > /dev/null 2>&1; then
        echo -e "${GREEN}✓ Application is healthy${NC}"
        break
    fi

    echo -n "."
    sleep 2
    COUNTER=$((COUNTER + 1))
done
echo ""

if [ $COUNTER -eq $RETRIES ]; then
    echo -e "${RED}Warning: Health check timeout${NC}"
    echo "Application may still be starting. Check logs with: docker compose logs -f"
else
    echo ""
    echo -e "${GREEN}========================================"
    echo "✓ Deployment Complete!"
    echo -e "========================================${NC}"
    echo ""
    echo -e "${BLUE}Access the application at:${NC}"
    echo "  http://localhost:5000"
    echo ""

    # Get credentials from .env
    USERNAME=$(grep DEFAULT_USERNAME .env | cut -d'=' -f2 | tr -d ' ')
    PASSWORD=$(grep DEFAULT_PASSWORD .env | cut -d'=' -f2 | tr -d ' ')

    echo -e "${BLUE}Default credentials:${NC}"
    echo "  Username: ${USERNAME:-admin}"
    echo "  Password: ${PASSWORD:-admin}"
    echo ""
    echo -e "${YELLOW}! Change these credentials after first login!${NC}"
    echo ""
    echo -e "${BLUE}Useful commands:${NC}"
    echo "  View logs:        docker compose logs -f"
    echo "  Stop:             docker compose down"
    echo "  Restart:          docker compose restart"
    echo "  Shell access:     docker compose exec custom-cvp bash"
    echo ""
fi

# Show status
echo -e "${BLUE}Container status:${NC}"
docker compose ps
echo ""

exit 0
