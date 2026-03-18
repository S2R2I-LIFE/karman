#!/bin/bash
# Setup script to fix permissions for Docker deployment
# Run this on the host before starting the container

echo "================================================"
echo "Kármán - Permission Setup"
echo "================================================"
echo ""

# Get the directory where this script is located
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$SCRIPT_DIR"

echo "Working directory: $SCRIPT_DIR"
echo ""

# Create necessary directories
echo "Creating directories..."
mkdir -p data logs output/generated-configs

# Set ownership to UID 1000 (cvpuser in container)
echo "Setting ownership to UID 1000..."
if command -v sudo &> /dev/null && [ "$(id -u)" -ne 0 ]; then
    sudo chown -R 1000:1000 data logs output
    sudo chmod -R 777 data logs output
else
    chown -R 1000:1000 data logs output
    chmod -R 777 data logs output
fi

# If database exists, ensure it's writable
if [ -f "data/custom-cvp.db" ]; then
    echo "Making database writable..."
    if command -v sudo &> /dev/null && [ "$(id -u)" -ne 0 ]; then
        sudo chmod 666 data/custom-cvp.db
    else
        chmod 666 data/custom-cvp.db
    fi
fi

echo ""
echo "✓ Permissions set successfully!"
echo ""
echo "Directory permissions:"
ls -la data logs output | grep -E "^d"
echo ""
echo "You can now run: docker compose up -d"
echo "================================================"
