# Kármán Web Interface Documentation

## Overview

The Kármán Web Interface is a production-ready, full-featured dashboard for managing Arista network devices. Built with Flask, Bootstrap 5, and modern web technologies, it provides an intuitive graphical interface for all platform capabilities.

## Features

### ✅ Complete Feature Set

1. **Dashboard**
   - Real-time device statistics
   - Device distribution by role (pie chart)
   - Recent activity feed
   - Quick action buttons
   - System status monitoring

2. **Device Management**
   - Browse device inventory
   - Filter by role, site, management type
   - Add/edit/delete devices
   - View device details and assigned configlets
   - Device actions (sync, compliance check, connect)

3. **Configlet Management**
   - Browse all configlets
   - Search functionality
   - View configlet details and history
   - Create/edit configlets with syntax highlighting
   - Version history tracking
   - Import CVP configlets (25 production configs included)

4. **Configuration Builder**
   - Select device variables (YAML)
   - Choose from categorized templates (Base, Layer2, Layer3, Overlays)
   - Build configurations with one click
   - Preview generated configurations
   - Copy to clipboard or download
   - Deploy to devices

5. **Task Management**
   - Create change control tasks
   - Filter by status (pending, in-progress, completed, failed)
   - View task details and execution logs
   - Task approval workflow
   - Rollback capabilities

6. **API Endpoints**
   - RESTful API for automation
   - `/api/stats` - Platform statistics
   - `/api/topology` - Network topology data
   - JSON responses for easy integration

## Quick Start

### Development Mode

```bash
# Install dependencies (if not already done)
pip install -r requirements.txt

# Start the web server
./start_web.sh

# Or manually:
cd web
python3 app.py
```

Access at: **http://localhost:5000**

**Default Login:** Any username/password (authentication is basic for now)

### Production Mode

```bash
# Configure environment
cp .env.example .env
# Edit .env with your settings

# Start with Gunicorn
./start_web_production.sh
```

## Architecture

```
web/
├── app.py                 # Main Flask application
├── templates/             # HTML templates (Jinja2)
│   ├── base.html          # Base layout
│   ├── login.html         # Authentication
│   ├── dashboard.html     # Main dashboard
│   ├── devices.html       # Device management
│   ├── configlets.html    # Configlet management
│   ├── builder.html       # Configuration builder
│   ├── tasks.html         # Task management
│   └── ...
└── static/
    └── css/
        └── style.css      # Custom styling
```

## Page-by-Page Guide

### 1. Dashboard (`/`)

**Features:**
- Device count with CVP vs Custom breakdown
- Configlet count
- Pending tasks counter
- System status indicator
- Device distribution pie chart
- Recent activity timeline
- Quick action buttons

**Quick Actions:**
- Add Device
- New Configlet
- Build Config
- Create Task

### 2. Devices (`/devices`)

**Features:**
- Paginated device list
- Filter by role, site, management type
- Device status badges
- Inline actions (view, delete)

**Add Device (`/devices/add`):**
- Form for adding new devices
- Required fields: hostname, IP, role, site
- Optional: model, serial, EOS version, container
- Management type selection
- CVP managed checkbox

**Device Detail (`/devices/<hostname>`):**
- Full device information
- Assigned configlets list
- Action buttons (sync, compliance, connect)
- Tags display

### 3. Configlets (`/configlets`)

**Features:**
- Grid view of all configlets
- Search by name
- Type badges (static, template, builder)
- Line count display
- Quick view/edit access

**View Configlet (`/configlets/<name>`):**
- Syntax-highlighted configuration
- Version history table
- Export and copy functions
- Edit button

**Create/Edit Configlet:**
- Name and description fields
- Type selection
- Large text area for configuration
- Change reason for updates

### 4. Configuration Builder (`/builder`)

**Features:**
- Device variable file selector
- Template selection by category:
  - **Base:** system.j2, interfaces.j2
  - **Layer2:** vlans.j2, mlag.j2, spanning-tree.j2
  - **Layer3:** bgp.j2, ospf.j2, static-routes.j2
  - **Overlays:** vxlan.j2, evpn.j2
- Output filename customization
- Build button

**Builder Result (`/builder/build`):**
- Generated configuration preview
- Copy to clipboard
- Download as file
- Deploy to device
- Validation option

### 5. Tasks (`/tasks`)

**Features:**
- Task list with status filtering
- Task cards with metadata
- Status badges (color-coded)
- Quick access to details

**Task Detail (`/tasks/<id>`):**
- Full task information
- Target devices list
- Execution logs (real-time)
- Action buttons (execute, rollback, retry)
- Task timeline

**Create Task (`/tasks/create`):**
- Task type selection
- Description text area
- Device selection (click badges to add)
- Validation before submission

## API Usage

### Get Platform Statistics

```bash
curl http://localhost:5000/api/stats
```

Response:
```json
{
  "devices": {
    "total": 25,
    "cvp_managed": 5,
    "custom_managed": 20
  },
  "configlets": {
    "total": 32
  },
  "tasks": {
    "total": 15,
    "pending": 3,
    "completed": 12
  }
}
```

### Get Network Topology

```bash
curl http://localhost:5000/api/topology
```

Response:
```json
{
  "nodes": [
    {
      "id": "leaf1-dc1",
      "label": "leaf1-dc1",
      "role": "leaf",
      "site": "datacenter1",
      "ip": "192.168.1.11",
      "cvp_managed": false
    }
  ],
  "links": []
}
```

## Security Considerations

### Current Implementation (Development)

- Simple session-based authentication
- Any username/password accepted
- Session timeout: 8 hours
- CSRF protection via Flask-WTF (recommended to add)

### Production Recommendations

1. **Authentication:**
   - Integrate with LDAP/Active Directory
   - Use OAuth2 for single sign-on
   - Implement role-based access control (RBAC)

2. **HTTPS:**
   - Use reverse proxy (Nginx/Apache)
   - Configure SSL certificates
   - Force HTTPS redirects

3. **Session Security:**
   - Use secure session cookies
   - Implement session fixation protection
   - Add CSRF tokens to forms

4. **Input Validation:**
   - Sanitize all user inputs
   - Validate file uploads
   - Prevent SQL injection (using parameterized queries)

### Example Nginx Configuration

```nginx
server {
    listen 443 ssl;
    server_name customcvp.example.com;

    ssl_certificate /path/to/cert.pem;
    ssl_certificate_key /path/to/key.pem;

    location / {
        proxy_pass http://127.0.0.1:5000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

## Customization

### Branding

Edit `/web/templates/base.html`:
```html
<a class="navbar-brand" href="{{ url_for('dashboard') }}">
    <i class="bi bi-cloud-arrow-up-fill"></i> Your Company Name
</a>
```

### Color Scheme

Edit `/web/static/css/style.css`:
```css
:root {
    --primary-color: #your-color;
    --secondary-color: #your-color;
}
```

### Add Custom Pages

1. Create route in `app.py`:
```python
@app.route('/custom')
@login_required
def custom_page():
    return render_template('custom.html')
```

2. Create template in `/web/templates/custom.html`

3. Add to navigation in `base.html`

## Troubleshooting

### Port Already in Use

```bash
# Find process using port 5000
lsof -i :5000

# Kill the process or use different port
export PORT=5001
python3 app.py
```

### Database Locked

```bash
# Check for other processes
ps aux | grep python

# Reset database (caution: deletes data)
rm custom-cvp.db
python3 cli/orchestrator_cli.py inventory list
```

### Templates Not Found

```bash
# Ensure you're in the correct directory
cd /path/to/custom-cvp
python3 web/app.py
```

### Static Files Not Loading

```bash
# Check static directory exists
ls -la web/static/css/

# Verify permissions
chmod -R 755 web/static/
```

## Performance Optimization

### For Large Deployments (1000+ devices)

1. **Enable Caching:**
   - Add Flask-Caching
   - Cache dashboard statistics
   - Cache device lists

2. **Database Optimization:**
   - Add indexes to SQLite tables
   - Consider PostgreSQL for production

3. **Pagination:**
   - Implement pagination for device/configlet lists
   - Lazy load data in tables

4. **Background Tasks:**
   - Use Celery for long-running operations
   - Queue config deployments
   - Async task execution

## Monitoring

### Application Logs

```bash
# Development
tail -f logs/app.log

# Production (with Gunicorn)
tail -f logs/access.log
tail -f logs/error.log
```

### Health Check Endpoint

```bash
curl http://localhost:5000/api/stats
```

## Future Enhancements

- [ ] Real-time device connectivity status
- [ ] Network topology visualization (D3.js/Cytoscape)
- [ ] Configuration diff viewer
- [ ] Batch operations
- [ ] Scheduled tasks/cron jobs
- [ ] Audit log viewer
- [ ] WebSocket for live updates
- [ ] Mobile-responsive improvements
- [ ] Dark mode toggle
- [ ] Export reports (PDF/Excel)

## Support

For issues or questions:
1. Check this documentation
2. Review the main README.md
3. Check application logs
4. Consult the Flask documentation

## License

Internal use - customize as needed for your organization.

---

**Built with:**
- Flask 2.0+
- Bootstrap 5.3
- Chart.js 4.0
- Bootstrap Icons

**Compatible with:**
- Python 3.8+
- SQLite 3
- Modern browsers (Chrome, Firefox, Safari, Edge)
