# CLAUDE.md — Custom CVP Project Guide

## What This Is
Flask-based network management platform for Arista devices ("Kármán / Custom CVP").
Self-hosted alternative to Arista CloudVision Portal.
Working directory: `/opt/unetlab/custom-cvp`

---

## Tech Stack
- **Backend:** Python 3.11, Flask 2.0, SQLite (`custom-cvp.db`)
- **Frontend:** Jinja2 templates, Bootstrap 5 dark mode, Chart.js, canvas starfield UI
- **Device connectivity:** pyeapi (eAPI/HTTPS), netmiko (SSH), pygnmi (gNMI/TerminAttr), cvprac (CVP)
- **Monitoring:** gnmic → Prometheus → queried by Flask `/api/metrics/<hostname>`
- **Deployment:** Docker Compose — 3 services: `custom-cvp`, `gnmic`, `prometheus`

---

## Directory Layout
```
web/app.py              Main Flask app (~2,760 lines) — all routes + startup init
web/email_sender.py     EmailSender class (DB-backed SMTP settings)
web/auth_decorators.py  @login_required, @admin_required decorators
web/templates/          Jinja2 HTML templates
web/static/             CSS (style.css, cli-browser.css), JS, images
core/inventory.py       InventoryManager — devices, roles, sites, gnmi_port
core/configlet.py       ConfigletManager — configs with SHA256 versioning + file storage
core/task.py            TaskManager — change control lifecycle (PENDING→COMPLETED/FAILED)
core/user.py            UserManager — auth, lockout, access requests, audit log
core/notification.py    NotificationManager — in-app notification queue
core/telemetry.py       Telemetry parsing — interfaces, CPU, temp, gNMI eos_native
core/topology.py        TopologyDiscovery — LLDP-based network graph
core/cli_browser.py     CLIBrowserManager — Arista CLI command DB + progressive disclosure
core/cli_navigator.py   CLINavigator — command syntax validation
core/mib_browser.py     MIBBrowserManager — SNMP MIB browser
connectors/             Device drivers (see Connectors section)
monitoring/gnmic/       gnmic.yml — gNMI streaming config
monitoring/prometheus/  prometheus.yml — scrape config
docker-compose.yml      3-service stack definition
.env                    Secrets, ports, credentials (never commit changes here)
```

---

## Application Bootstrap
`web/app.py` initializes 9 manager singletons at startup:
```python
inventory_manager    = InventoryManager(db_path)
configlet_manager    = ConfigletManager(db_path, configlet_dir)
task_manager         = TaskManager(db_path)
user_manager         = UserManager(db_path)
notification_manager = NotificationManager(db_path)
email_sender         = EmailSender(db_path)
cli_browser_manager  = CLIBrowserManager(db_path)
# + builder, validator
```
All managers wrap SQLite with business logic. DB path from `DATABASE_PATH` env var or default `custom-cvp.db`.

---

## Database Schema (SQLite)

### Device Inventory
```sql
devices            (hostname PK, ip_address, model, serial_number, eos_version,
                    management_type, role, site, container, cvp_managed,
                    last_seen, compliance_status, config_hash, gnmi_port)
device_configlets  (device_hostname FK, configlet_name, priority)
device_tags        (device_hostname FK, tag_key, tag_value)
```

### Configlets
```sql
configlets         (name PK, description, configlet_type, config_hash,
                    created_at, updated_at, version)
configlet_history  (id PK, configlet_name, version, config_hash,
                    changed_at, changed_by, change_reason)
```

### Tasks
```sql
tasks              (task_id PK, task_type, description, status,
                    created_at, created_by, executed_at, executed_by,
                    devices JSON, config_changes JSON, results JSON, rollback_info JSON)
task_logs          (id PK, task_id FK, timestamp, device, log_level, message)
```

### Users & Auth
```sql
users              (user_id PK, username UNIQUE, email, full_name, password_hash,
                    is_admin, is_active, created_at, approved_at, approved_by,
                    last_login, failed_login_attempts, account_locked_until)
access_requests    (request_id PK, username, email, full_name, reason,
                    requested_at, status, reviewed_at, reviewed_by, rejection_reason)
auth_audit_log     (log_id PK, timestamp, event_type, username, ip_address,
                    details JSON, success)
```

### Other Tables
```sql
notification_queue (notification_id PK, user_id, notification_type, title,
                    message, related_id, is_read, created_at, read_at)
app_settings       (key PK, value)          -- SMTP and other admin settings
email_log          (recipient_email, subject, email_type, sent_at,
                    success, error_message, related_request_id)
cli_modes          (mode_id PK, mode_name UNIQUE, mode_category, parent_mode_id, description)
cli_commands       (command_id PK, mode_id FK, command_text, command_base,
                    has_no_prefix, has_default_prefix, line_number,
                    technology_tags JSON, action_tags JSON)
cli_tokens         (token_id PK, command_id FK, position, token_type,
                    token_value, is_optional, parent_token_id)
```

---

## Connectors

| File | Protocol | Port | Library |
|------|----------|------|---------|
| `eapi_connector.py` | HTTPS/eAPI | 443 | pyeapi |
| `netmiko_connector.py` | SSH | 22 | netmiko |
| `gnmi_connector.py` | gRPC/gNMI | 6030 | pygnmi |
| `cvp_connector.py` | HTTPS/REST | — | cvprac |

**gNMI connector specifics:**
- Auto-TLS detection: SSL probe → TOFU cert trust, or falls back to `insecure=True` (vEOS-lab)
- `_GNMIclient` subclass silences UNIMPLEMENTED Capabilities RPC (vEOS-lab behavior)
- Management type enum: `DeviceType.GNMI_MANAGED = "gnmi"` in `core/inventory.py`

**Device type auto-detection** (TCP probing at add-time):
- Port 443 open → eAPI
- Port 22 open → SSH
- Port 6030 open → gNMI/TerminAttr

---

## Key Routes (web/app.py)

### Auth
- `GET/POST /login`, `/logout`, `/register`
- First user auto-becomes admin; subsequent users → pending access request
- 5 failed attempts = 30-min lockout

### Devices
- `GET /devices`, `POST /devices/add`, `GET /devices/<hostname>`, `POST /devices/<hostname>/edit`
- `POST /api/detect-management-type` — TCP probe to determine management type
- `POST /devices/<hostname>/sync` — Pull running config → create/update configlet
- `POST /api/devices/<hostname>/execute` — Run CLI (blocked: reload, write erase, configure terminal, etc.)

### Configlets
- `GET /configlets`, `POST /configlets/create`, `GET /configlets/<name>`, `POST /configlets/<name>/edit`
- Files stored in `./configlets/<name>.cfg`

### Tasks
- `GET /tasks`, `POST /tasks/create`, `GET /tasks/<id>`
- `POST /tasks/<id>/execute`, `/cancel`, `/delete`

### Telemetry & Monitoring
- `GET /api/telemetry/devices` — Concurrent collection (ThreadPoolExecutor, 10s/device, 35s total)
- `GET /api/metrics/<hostname>?range=1h|6h|24h` — Query Prometheus for gNMI interface data
- `GET /api/devices/status` — Fast TCP port checks

### Admin
- `GET /admin/access-requests`, `POST /admin/access-requests/<id>/approve|reject`
- `GET /settings`, `POST /admin/settings/email`
- `GET /health` — Docker health check

### Notifications
- `GET /api/notifications` — Polled every 30s by navbar bell
- `POST /api/notifications/mark-all-read`

---

## UI Architecture

### Standalone Pages (no base.html)
Space theme: canvas starfield with shooting stars from all 4 edges, glassmorphism card.
- `login.html`, `register.html`, `access_pending.html`, `404.html`, `500.html`

### Authenticated Pages (extend base.html)
- Dark mode: Bootstrap `data-bs-theme="dark"`, static twinkling starfield via canvas
- Toggled by MutationObserver; canvas `#starfield-bg` hidden in light mode
- `[data-bs-theme="dark"] body { background: transparent }` — canvas IS the background
- `[data-bs-theme="dark"] .badge.bg-warning { color: #1a1200 !important }` — fixes white-on-yellow

### Dashboard Device Cards
- `cardSize` global: `normal` (2/row) or `compact` (4/row)
- `tempUnit` global: `F` by default, click any badge to toggle °C/°F
- `viewGrouped` global: collapsible site groups; `siteCollapsed` Map persists state
- Sort priority: DOWN=0, critical temp=1, warning temp=2, interfaces down=3, normal=4
- Sites with DOWN devices: always expanded + red border; warning sites: expanded + orange

### Interface Telemetry Card (device_detail.html)
- Only shown when `management_type == 'gnmi'`
- Chart.js stepped line chart, `type: 'linear'` x-axis with manual `fmtTs()` formatter
- Link flaps table below chart

---

## gNMI / eos_native Path Details
- Interface status path: `eos_native:/Sysdb/interface/status/eth/phy/slice/1/intfStatus`
- Response: each interface = separate `notification`; interface name = last segment of `notification['prefix']`
- `operStatus` values: `intfOperUp` = up, anything else = down
- Skip notifications where prefix last segment starts with `_` or equals `intfStatus`
- OpenConfig paths return `{}` on vEOS-lab without CVP — must use `eos_native` origin

## gnmic Metrics in Prometheus
- `gnmic_Sysdb_interface_status_eth_phy_slice_1_intfStatus_<EthernetN>_active`
- `gnmic_Sysdb_interface_status_eth_phy_slice_1_intfStatus_<EthernetN>_linkStatusChanges`

---

## Email System
- `EmailSender` in `web/email_sender.py`
- Settings read from `app_settings` table (overrides env vars)
- `POST /admin/settings/email` saves: smtp_host, smtp_port, smtp_username, smtp_password, smtp_use_tls, from_email, email_enabled
- Checkbox absence in form POST = false (standard HTML behavior — handled explicitly)
- Sends on: access request submitted, request approved, request rejected

---

## Environment Variables (.env)
```
SECRET_KEY                Flask session secret
FLASK_ENV                 production | development
DATABASE_PATH             Path to SQLite DB
WORKERS                   Gunicorn workers (default 4)
BIND_ADDRESS              e.g. 0.0.0.0:5000
DEFAULT_DEVICE_USERNAME   Device login
DEFAULT_DEVICE_PASSWORD   Device password
GNMIC_USERNAME            gNMI/TerminAttr username (expanded in gnmic.yml)
GNMIC_PASSWORD            gNMI/TerminAttr password
PROMETHEUS_URL            e.g. http://localhost:9091
PROMETHEUS_PORT           Prometheus listen port (default 9091)
TELEGRAF_METRICS_PORT     gnmic Prometheus metrics port (default 9273)
GNMIC_METRICS_PORT        Same as above
SMTP_ENABLED / SMTP_*     Email fallback (overridden by DB settings)
```

---

## Access Control Workflow
1. User registers (no "reason" field) → `access_request` row created
2. All admins receive in-app notification + email
3. Admin approves/rejects at `/admin/access-requests/<id>/approve|reject`
4. User receives approval/rejection email
5. **First registered user becomes admin automatically** (no approval needed)

---

## Dependency & Package Update Policy
Before committing any changes, check online sources for available updates to dependencies and packages used in this project. The goal is to stay current and competitive with the latest tooling.

**What to check:**
- `requirements.txt` — verify PyPI latest versions for all packages (Flask, pyeapi, netmiko, pygnmi, cvprac, gunicorn, etc.)
- `docker-compose.yml` — check Docker Hub / GitHub Container Registry for newer image tags:
  - `ghcr.io/openconfig/gnmic` — check https://github.com/openconfig/gnmic/releases
  - `prom/prometheus` — check https://github.com/prometheus/prometheus/releases
  - Base Python image in `Dockerfile` — check for newer `python:3.x-slim` releases
- Any JS libraries loaded via CDN in templates (Bootstrap, Chart.js, etc.)

**How to check:**
- Use WebSearch or WebFetch to look up latest stable releases before pinning versions
- Prefer pinned versions (not `latest` tags) for reproducibility, but keep them current
- Note any breaking changes in release notes before upgrading major versions
- Update `requirements.txt` with new versions and note what changed in the commit message

---

## Important Constraints & Gotchas
- **Do NOT use `event-add-tag` processor in gnmic config** — `tags` field expects list of strings, not map
- **TerminAttr + `management api gnmi` cannot share the same port** — use one or the other
- **TerminAttr grpcaddr must specify VRF** if mgmt interface is in a VRF: `-grpcaddr=mgmt/0.0.0.0:6030`
- **Capabilities RPC returns UNIMPLEMENTED** on vEOS-lab — handled by `_GNMIclient` subclass
- `import time` is at top-level in `app.py` (needed for Prometheus query range calculations)
- gnmic env var expansion works in `gnmic.yml` via `${VAR}` syntax
- Reason field removed from register form and backend validation in `core/user.py`

---

## Zero Touch Provisioning (ZTP) — Current State (as of 2026-03-25)

### What's Built and Working
ZTP is fully end-to-end functional. A switch with no startup config boots, gets a DHCP lease
from Kármán's built-in Python server, downloads and runs the ZTP script, registers itself in
inventory with a permanent management IP, writes its own `interface Management1` stanza, and
reloads onto that permanent IP. The device then appears in the dashboard within ~30s.

### Key Files
```
core/dhcp_server.py       Pure-Python DHCP server (NEW) — Arista-only vendor-class filter
core/ztp_manager.py       ZTPManager — settings, leases, script generation, mgmt IP pool
web/templates/ztp.html    ZTP admin page — DHCP control, lease table, pool config
```

### Python DHCP Server (`core/dhcp_server.py`)
- `PythonDHCPServer(get_settings_fn)` — thread-based, pure UDP/raw sockets
- Responds **only** to packets with option 60 (vendor-class) containing `"Arista"` — all other
  clients silently ignored (UCG-Ultra / router continues serving them normally)
- Full DISCOVER → OFFER → REQUEST → ACK flow
- Option 67 (boot file) always set to `<karman_url>/ztp/script`
- Option 12 (client hostname) captured and stored in `_Pool` per MAC
- Falls back to dnsmasq if Python server fails to bind port 67
- `docker-compose.yml`: `user: root`, `cap_add: [NET_BIND_SERVICE, NET_RAW, NET_ADMIN]`
- `Dockerfile`: `setcap` on dnsmasq binary

### Management IP Pool
- Configured via ZTP settings page: enable toggle, start/end IP, prefix length, gateway, iface
- `ZTPManager.allocate_mgmt_ip()` — thread-safe, scans `devices` table to skip used IPs
- ZTP script calls `register()` **first** (before `apply_base_config()`) to get permanent IP
- `apply_base_config()` prepends `interface Management1` stanza if pool is enabled
- Switch reloads onto permanent IP; Kármán registers device with that IP from the start
- Default management interface: `Management1` (vEOS uses Management1, not Management0)

### ZTP Script Flow (on-switch Python)
1. `main()` → `register(url, dhcp_ip)` → POST `/api/devices/register` → returns `{mgmt_ip, mgmt_prefix, mgmt_gateway}`
2. If `mgmt_ip` returned → `config_ip = mgmt_ip`, else fall back to DHCP IP
3. `apply_base_config(hostname, config_ip)` — writes startup-config with Management1 if pool enabled
4. Switch reloads with permanent IP

### `/api/devices/register` Route Behavior
- Allocates permanent IP from pool (if enabled)
- Probes `ip` (DHCP IP) for management type — NOT the permanent IP (switch still has DHCP IP at this point)
- Returns `{success, mgmt_ip, mgmt_prefix, mgmt_gateway}`
- If device already exists: returns existing `mgmt_ip` (idempotent)

### ZTP Lease Table (`ztp_leases` DB table)
- Columns: `mac_address PK, ip_address, device_hostname, first_seen, last_seen, registered, ignored`
- `ignored` column added via `ALTER TABLE` migration in `ZTPManager._init_db()`
- Ignore/unignore routes: `POST /api/ztp/leases/<mac>/ignore` and `/unignore`
- Delete route: `POST /api/ztp/leases/<mac>/delete`
- `delete_lease_by_hostname(hostname)` called from `delete_device` route — cleans up lease on inventory deletion
- UI: ignored rows hidden by default, "Show ignored" toggle in card header, faded with Unignore+Delete buttons

### ZTP Settings Keys (in `app_settings` table)
| Key | Purpose |
|-----|---------|
| `ztp_enabled` | Master on/off |
| `ztp_karman_url` | Base URL injected into script as option 67 and `__KARMAN_URL__` |
| `ztp_dhcp_interface` | Network interface to bind DHCP server on |
| `ztp_dhcp_range_start/end` | IP pool for ZTP DHCP leases |
| `ztp_dhcp_netmask/gateway/dns` | DHCP offer options |
| `ztp_mgmt_pool_enabled` | Whether to allocate permanent management IPs |
| `ztp_mgmt_pool_start/end` | Permanent IP range |
| `ztp_mgmt_prefix` | Subnet prefix length (default `24`) |
| `ztp_mgmt_gateway` | Gateway written into Management1 stanza |
| `ztp_mgmt_iface` | Management interface name (default `Management1`) |

### Known Gotchas
- **DHCP probe timing**: During ZTP the switch only has its DHCP IP — probe management type
  against the DHCP IP, not the permanent IP. The `api_device_register` route does this correctly.
- **`timeago` filter**: Handles `int`/`float` Unix timestamps via `datetime.fromtimestamp()`.
  Do NOT pipe through `| int` in templates — the filter handles raw floats directly.
- **Lease orphans**: Deleting a device from inventory now auto-deletes its ZTP lease. Previously
  ignored leases (set before deletion) were NOT auto-cleaned — must be manually deleted or will
  show up in the lease table after device is gone.
- **Port 67 bind**: Requires `user: root` in docker-compose.yml and `NET_BIND_SERVICE` cap.
  If Python server fails to bind, check `docker logs custom-cvp-docker` for the OSError.

---

## Planned Next Features (from plan file `mossy-moseying-perlis.md`)

Four features are designed and ready to implement:

1. **Threshold Alerting** — `core/alert_manager.py` (new), alert_rules + alert_events tables,
   background loop every 30s, email + in-app notifications, admin UI at `/admin/alerts`

2. **Scheduled Config Backups** — `_do_device_backup()` helper, background loop checks schedule,
   `last_backup_at` column on devices, "Last Backup" column in device list

3. **Compliance / Drift Detection** — SHA256 diff on running config, `config_prev_<hostname>` in
   app_settings for before/after diff, `/compliance` page with unified diff modal

4. **BGP Dashboard** — fleet-wide BGP peer status from telemetry cache, filter bar, state-change
   notifications, `/bgp` page

See plan file for full schema, routes, templates, and implementation order.
