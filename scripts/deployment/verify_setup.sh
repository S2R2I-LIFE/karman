#!/bin/bash
# Verification script for Kármán setup

echo "===================================="
echo "Kármán Setup Verification"
echo "===================================="
echo ""

# Check database
if [ -f "custom-cvp.db" ]; then
    echo "✓ Database exists: custom-cvp.db"
    DB_SIZE=$(ls -lh custom-cvp.db | awk '{print $5}')
    echo "  Size: $DB_SIZE"
else
    echo "✗ Database not found!"
    exit 1
fi

# Check Python dependencies
echo ""
echo "Checking Python dependencies..."
python3 -c "import flask" 2>/dev/null && echo "✓ Flask installed" || echo "✗ Flask not installed"
python3 -c "import yaml" 2>/dev/null && echo "✓ PyYAML installed" || echo "✗ PyYAML not installed"
python3 -c "import jinja2" 2>/dev/null && echo "✓ Jinja2 installed" || echo "✗ Jinja2 not installed"

# Count database contents
echo ""
echo "Database Contents:"
CONFIGLET_COUNT=$(python3 -c "from core.configlet import ConfigletManager; print(len(ConfigletManager('custom-cvp.db').list_configlets()))")
echo "  Configlets: $CONFIGLET_COUNT"

DEVICE_COUNT=$(python3 -c "from core.inventory import InventoryManager; print(len(InventoryManager('custom-cvp.db').get_all_devices()))" 2>/dev/null || echo "0")
echo "  Devices: $DEVICE_COUNT"

# List first 10 configlets
if [ "$CONFIGLET_COUNT" -gt 0 ]; then
    echo ""
    echo "Sample Configlets:"
    python3 -c "from core.configlet import ConfigletManager; [print(f'  - {name}') for name in ConfigletManager('custom-cvp.db').list_configlets()[:10]]"
fi

# Check web files
echo ""
echo "Web Interface Files:"
[ -f "web/app.py" ] && echo "✓ web/app.py exists" || echo "✗ web/app.py missing"
[ -f "web/templates/configlets.html" ] && echo "✓ configlets.html exists" || echo "✗ configlets.html missing"
[ -f "start_web.sh" ] && echo "✓ start_web.sh exists" || echo "✗ start_web.sh missing"

echo ""
echo "===================================="
echo "Setup verification complete!"
echo "===================================="
echo ""
echo "To start the web interface:"
echo "  ./start_web.sh"
echo ""
echo "Then visit: http://localhost:5000"
echo "  - Login with any username/password"
echo "  - Click 'Configlets' in the navigation"
echo ""
