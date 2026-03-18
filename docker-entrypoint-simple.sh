#!/bin/bash
set -e

echo "Starting Kármán..."

# Wait a moment
sleep 2

# Run the application
exec "$@"
