# Troubleshooting: Configlets Not Displaying

## Issue Description
The dashboard shows 25 configlets exist, but the configlets page appears empty.

## Quick Diagnosis Steps

### Step 1: Access the Debug Page

Start the web server and navigate to the debug page:

```bash
# From /home/b/cvp/custom-cvp directory
./start_web.sh

# Then visit in your browser:
http://localhost:5000/configlets/debug
```

This page will show you:
- How many configlets are in the database
- How many configlets were passed to the template
- The raw data for the first 10 configlets
- API test results

### Step 2: Check the API Endpoint

While logged into the web interface, visit:
```
http://localhost:5000/api/configlets
```

This should return JSON data showing all 25 configlets. If this works, the problem is in the frontend rendering.

### Step 3: Check Browser Console

1. Open the configlets page: `http://localhost:5000/configlets`
2. Open browser developer tools (F12)
3. Check the Console tab for JavaScript errors
4. Check the Network tab to see if requests are failing

### Step 4: Verify Database Directly

From the command line:

```bash
cd /home/b/cvp/custom-cvp

python3 -c "from core.configlet import ConfigletManager; \
cm = ConfigletManager('custom-cvp.db'); \
names = cm.list_configlets(); \
print(f'Total: {len(names)}'); \
[print(f'{i+1}. {name}') for i, name in enumerate(names[:10])]"
```

This should show 25 configlets total and list the first 10.

## Common Causes and Fixes

### Cause 1: Browser Cache Issue

**Symptoms:** Dashboard shows data but pages appear empty

**Fix:**
1. Clear browser cache (Ctrl+Shift+Delete)
2. Do a hard refresh (Ctrl+F5)
3. Try in incognito/private browsing mode

### Cause 2: Static Files Not Loading

**Symptoms:** Page loads but has no styling, configlets appear as plain text

**Fix:**
```bash
# Check if static files exist
ls -la /home/b/cvp/custom-cvp/web/static/css/style.css

# Verify static files are being served
curl http://localhost:5000/static/css/style.css
```

If the file doesn't exist or curl fails, restart the web server from the correct directory:
```bash
cd /home/b/cvp/custom-cvp
./start_web.sh
```

### Cause 3: Database Path Issue

**Symptoms:** Different data on different pages

**Fix:**
```bash
# Check if there are multiple database files
find /home/b/cvp/custom-cvp -name "*.db"

# Should only show: /home/b/cvp/custom-cvp/custom-cvp.db
```

If multiple databases exist, ensure the web app is using the correct one.

### Cause 4: Template Rendering Error

**Symptoms:** Page loads but configlet cards don't appear

**Fix:**
Check the Flask logs for errors:
```bash
# If running in terminal, check the output
# If running with start_web.sh, check:
tail -f logs/app.log
```

### Cause 5: Container/Row CSS Issue

**Symptoms:** HTML exists but is not visible

**Fix:**
Check the page source (View Page Source) and search for "col-md-6 col-lg-4". If you find the configlet cards in the source but don't see them, it's a CSS rendering issue.

Try adding this to your browser console:
```javascript
document.querySelectorAll('.col-md-6.col-lg-4').forEach(el => {
    console.log(el.innerHTML);
});
```

If this shows the configlets, they exist but are hidden. Inspect the CSS.

## Verification Commands

### Check Everything at Once

Run this comprehensive check:

```bash
cd /home/b/cvp/custom-cvp
./verify_setup.sh
```

This will verify:
- Database exists and has content
- Python dependencies are installed
- Web interface files exist
- Sample configlets list

### Manual Web Test

```bash
cd /home/b/cvp/custom-cvp

# Test the web app
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
    print(f'Status: {response.status_code}')

    configlet_names = configlet_mgr.list_configlets()
    print(f'DB has: {len(configlet_names)} configlets')

    html = response.data.decode('utf-8')
    found = sum(1 for name in configlet_names if name in html)
    print(f'HTML contains: {found} configlet names')

    if found == len(configlet_names):
        print('✓ SUCCESS: All configlets are in the HTML')
    else:
        print('✗ PROBLEM: Configlets missing from HTML')
"
```

## Expected Output

When working correctly:
1. Dashboard shows "25 Configlets"
2. Clicking "Configlets" shows a grid of 25 cards
3. Each card shows:
   - Configlet name (e.g., "ACL-Start-BorderLeaf1")
   - Type badge ("static" or "builder")
   - Line count
   - View and Edit buttons

## Still Not Working?

If after trying all the above steps you still see an empty configlets page:

1. **Take a screenshot** of:
   - The empty configlets page
   - The browser developer console (F12)
   - The network tab showing requests

2. **Capture the HTML source**:
   - Right-click on the page
   - Select "View Page Source"
   - Search for "col-md-6 col-lg-4"
   - Copy that section

3. **Check server logs**:
   ```bash
   tail -50 logs/app.log
   ```

4. **Restart with debug mode**:
   ```bash
   cd /home/b/cvp/custom-cvp
   export FLASK_ENV=development
   export FLASK_DEBUG=1
   cd web
   python3 app.py
   ```

   Watch the console output when you access /configlets

## Quick Fix: Reload Configlets

If all else fails, try reimporting the configlets:

```bash
cd /home/b/cvp/custom-cvp

# Backup current database
cp custom-cvp.db custom-cvp.db.backup

# Re-import CVP configlets
python3 import_cvp_configlets.py

# Restart web server
./start_web.sh
```

This will ensure all 25 configlets are properly in the database.
