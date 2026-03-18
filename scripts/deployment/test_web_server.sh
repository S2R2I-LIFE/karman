#!/bin/bash
# Quick test to verify web server can see configlets

echo "Testing Web Server Configuration..."
echo ""

# Test from project root
cd /home/b/cvp/custom-cvp

# Start server in background
python3 web/app.py > /tmp/web_test.log 2>&1 &
SERVER_PID=$!

echo "Started web server (PID: $SERVER_PID)"
echo "Waiting for server to initialize..."
sleep 3

# Check if server is running
if ! kill -0 $SERVER_PID 2>/dev/null; then
    echo "ERROR: Server failed to start"
    cat /tmp/web_test.log
    exit 1
fi

# Check the logs for initialization
echo ""
echo "=== Server Initialization ==="
grep "\[INIT\]" /tmp/web_test.log

echo ""
echo "=== Testing Configlets Endpoint ==="

# Make a test request
curl -s http://localhost:5000/api/configlets 2>/dev/null | python3 -m json.tool | head -20

# Kill the test server
kill $SERVER_PID 2>/dev/null

echo ""
echo "Test complete!"
