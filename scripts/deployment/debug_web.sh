#!/bin/bash
# Quick diagnostic script for configlets display issue

echo "========================================"
echo "Kármán Configlets Diagnostic Tool"
echo "========================================"
echo ""

# Check if we're in the right directory
if [ ! -f "custom-cvp.db" ]; then
    echo "ERROR: custom-cvp.db not found!"
    echo "Please run this script from /home/b/cvp/custom-cvp"
    exit 1
fi

# 1. Check database
echo "1. Checking database..."
CONFIGLET_COUNT=$(python3 -c "from core.configlet import ConfigletManager; print(len(ConfigletManager('custom-cvp.db').list_configlets()))" 2>&1)
echo "   Configlets in database: $CONFIGLET_COUNT"

if [ "$CONFIGLET_COUNT" != "25" ]; then
    echo "   WARNING: Expected 25 configlets!"
fi

# 2. List first 5 configlets
echo ""
echo "2. Sample configlets:"
python3 -c "from core.configlet import ConfigletManager; [print(f'   - {name}') for name in ConfigletManager('custom-cvp.db').list_configlets()[:5]]"

# 3. Test web app in test mode
echo ""
echo "3. Testing web application..."
python3 -c "
import sys
from pathlib import Path
sys.path.insert(0, str(Path.cwd()))
from web.app import app, configlet_mgr

with app.test_client() as client:
    with client.session_transaction() as sess:
        sess['logged_in'] = True
        sess['username'] = 'test'

    response = client.get('/configlets')
    print(f'   HTTP Status: {response.status_code}')

    configlet_names = configlet_mgr.list_configlets()
    html = response.data.decode('utf-8')
    found = sum(1 for name in configlet_names if name in html)
    print(f'   Configlets in HTML: {found}/{len(configlet_names)}')

    if found == len(configlet_names):
        print('   ✓ All configlets are rendering in HTML')
    else:
        print('   ✗ Some configlets missing from HTML')

    # Check for error messages
    if 'No configlets found' in html:
        print('   ✗ ERROR: Page shows \"No configlets found\" message')
    else:
        print('   ✓ No error messages in HTML')
"

# 4. Check static files
echo ""
echo "4. Checking static files..."
if [ -f "web/static/css/style.css" ]; then
    echo "   ✓ style.css exists"
else
    echo "   ✗ style.css missing!"
fi

if [ -f "web/templates/configlets.html" ]; then
    echo "   ✓ configlets.html exists"
else
    echo "   ✗ configlets.html missing!"
fi

# 5. Check if server is running
echo ""
echo "5. Checking if web server is running..."
if lsof -i :5000 > /dev/null 2>&1; then
    echo "   ✓ Server is running on port 5000"
    echo ""
    echo "========================================"
    echo "NEXT STEPS:"
    echo "========================================"
    echo ""
    echo "The web server is running. Please:"
    echo ""
    echo "1. Open your browser to: http://localhost:5000/configlets/debug"
    echo "   This is a special debug page that shows exactly what data"
    echo "   the web app is seeing."
    echo ""
    echo "2. Check your browser's Developer Console (F12)"
    echo "   Look for any JavaScript errors that might prevent rendering."
    echo ""
    echo "3. Try the API endpoint: http://localhost:5000/api/configlets"
    echo "   This should return JSON with all 25 configlets."
    echo ""
    echo "4. If you see the cards in the HTML source (View Page Source)"
    echo "   but not on screen, it's likely a CSS/rendering issue."
    echo "   Try clearing your browser cache or using incognito mode."
    echo ""
else
    echo "   ✗ Server is not running"
    echo ""
    echo "========================================"
    echo "NEXT STEPS:"
    echo "========================================"
    echo ""
    echo "Start the web server:"
    echo "   ./start_web.sh"
    echo ""
    echo "Then visit: http://localhost:5000/configlets/debug"
    echo ""
fi

echo ""
echo "For detailed troubleshooting, see:"
echo "   TROUBLESHOOTING_CONFIGLETS.md"
echo ""
