#!/bin/bash
# Complete reset and fresh start script

echo "========================================"
echo "Kármán - Complete Reset"
echo "========================================"
echo ""

# Stop everything
echo "1. Stopping containers..."
docker compose down 2>/dev/null

# Remove old images
echo "2. Removing old images..."
docker rmi $(docker images | grep custom-cvp | awk '{print $3}') 2>/dev/null || true

# Clean database (backup first)
echo "3. Backing up and cleaning database..."
if [ -f "data/custom-cvp.db" ]; then
    cp data/custom-cvp.db data/custom-cvp.db.backup-$(date +%Y%m%d-%H%M%S)
    rm data/custom-cvp.db
    echo "   Database backed up and removed"
fi

# Fix permissions
echo "4. Setting up permissions..."
mkdir -p data logs output/generated-configs
chmod -R 777 data logs output 2>/dev/null || sudo chmod -R 777 data logs output

# Fix line endings on all shell scripts
echo "5. Fixing line endings..."
find . -maxdepth 1 -name "*.sh" -exec sed -i 's/\r$//' {} \;

# Use simple Dockerfile
echo "6. Preparing simple configuration..."
cp Dockerfile Dockerfile.backup
cp Dockerfile.simple Dockerfile
cp docker-entrypoint.sh docker-entrypoint.sh.backup
cp docker-entrypoint-simple.sh docker-entrypoint.sh

# Build fresh
echo "7. Building fresh image..."
docker compose build --no-cache

# Start
echo "8. Starting container..."
docker compose up -d

echo ""
echo "========================================"
echo "✓ Reset complete!"
echo "========================================"
echo ""
echo "Waiting for container to start..."
sleep 5

echo "Checking status..."
docker ps | grep custom-cvp

echo ""
echo "View logs:"
echo "  docker logs -f custom-cvp-docker"
echo ""
echo "Access at: http://192.168.2.38:5000"
echo ""
echo "First user to register becomes admin!"
echo "========================================"
