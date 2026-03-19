# Kármán — Self-Hosted Arista Network Management Platform

Kármán is a self-hosted alternative to Arista CloudVision Portal (CVP). It provides a web-based dashboard for managing Arista EOS devices via eAPI, SSH, and gNMI — without requiring a CVP license.

**Features at a glance:**
- Live device telemetry dashboard (interfaces, CPU, memory, temperature)
- Configlet management with SHA256 versioning and change history
- Change control (tasks) with approval workflow and rollback
- Per-device Metrics tab with Prometheus-backed interface graphs
- LLDP topology discovery
- CLI browser and MIB browser
- In-app notifications + email alerts
- User management with role-based access (admin / standard)

---

## Requirements

| Component | Minimum |
|-----------|---------|
| OS | Linux (Ubuntu 22.04+ recommended) |
| CPU | 2 cores |
| RAM | 2 GB |
| Disk | 10 GB |
| Python | 3.11+ (bare-metal only) |
| Docker | 24+ with Compose v2 (Docker install only) |

Network reachability to managed devices on:
- **eAPI**: TCP 443 (HTTPS) or 80 (HTTP)
- **SSH**: TCP 22
- **gNMI/TerminAttr**: TCP 6030

---

## Option 1 — Docker (recommended)

### 1. Clone the repository

```bash
git clone <repo-url> kárman
cd kárman
```

### 2. Configure environment

```bash
cp .env.example .env   # if .env.example exists, otherwise edit .env directly
```

Edit `.env` — at minimum set:

```ini
# Generate with: python3 -c "import secrets; print(secrets.token_hex(32))"
SECRET_KEY=replace-with-a-random-64-char-hex-string

# Credentials Kármán uses to connect to your Arista devices
DEFAULT_DEVICE_USERNAME=admin
DEFAULT_DEVICE_PASSWORD=yourpassword

# Port Kármán listens on (host port, container always binds 5000)
# Change if something else is already on 5000
BIND_ADDRESS=0.0.0.0:5000
```

All other defaults are fine for a lab environment.

### 3. Build and start

```bash
docker compose up -d --build
```

This starts four services:
| Container | Role | Port |
|-----------|------|------|
| `custom-cvp-docker` | Flask web app | 5000 |
| `karman-gnmic` | gNMI dial-in collector | — |
| `karman-gnmic-listener` | gNMI dial-out receiver | 9910 |
| `karman-prometheus` | Time-series DB | 9091 |

### 4. Open the UI

Navigate to `http://<server-ip>:5000`

The first user to register is automatically granted admin access — no approval needed.

### 5. Useful commands

```bash
# View logs
docker logs custom-cvp-docker -f

# Restart after code changes (volumes are live-mounted — no rebuild needed)
docker compose restart custom-cvp

# Full rebuild (after requirements.txt or Dockerfile changes)
docker compose up -d --build

# Stop everything
docker compose down

# Stop and remove all data (destructive)
docker compose down -v
```

---

## Option 2 — Bare Metal / Virtual Machine

### 1. Install Python 3.11

```bash
# Ubuntu / Debian
sudo apt update && sudo apt install -y python3.11 python3.11-venv python3-pip git curl
```

### 2. Clone and create virtualenv

```bash
git clone <repo-url> /opt/karman
cd /opt/karman
python3.11 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 3. Configure environment

```bash
cp .env .env.local   # keep original as reference
```

Edit `.env` (the app reads this file directly):

```ini
SECRET_KEY=replace-with-random-hex
FLASK_ENV=production
DATABASE_PATH=/opt/karman/data/custom-cvp.db
DEFAULT_DEVICE_USERNAME=admin
DEFAULT_DEVICE_PASSWORD=yourpassword
PROMETHEUS_URL=http://localhost:9091
```

### 4. Create required directories

```bash
mkdir -p /opt/karman/data /opt/karman/logs /opt/karman/output
```

### 5. Run with gunicorn

```bash
source /opt/karman/.venv/bin/activate
gunicorn \
  --bind 0.0.0.0:5000 \
  --workers 4 \
  --timeout 120 \
  --access-logfile /opt/karman/logs/access.log \
  --error-logfile /opt/karman/logs/error.log \
  web.app:app
```

### 6. (Optional) systemd service

```ini
# /etc/systemd/system/karman.service
[Unit]
Description=Kármán Network Management Platform
After=network.target

[Service]
Type=simple
User=www-data
WorkingDirectory=/opt/karman
EnvironmentFile=/opt/karman/.env
ExecStart=/opt/karman/.venv/bin/gunicorn \
  --bind 0.0.0.0:5000 \
  --workers 4 \
  --timeout 120 \
  --access-logfile /opt/karman/logs/access.log \
  --error-logfile /opt/karman/logs/error.log \
  web.app:app
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now karman
sudo systemctl status karman
```

### 7. Monitoring stack (bare metal)

For the Metrics tab and interface history graphs, you also need **gnmic** and **Prometheus**.

**Prometheus:**
```bash
# Download from https://github.com/prometheus/prometheus/releases
wget https://github.com/prometheus/prometheus/releases/download/v3.2.1/prometheus-3.2.1.linux-amd64.tar.gz
tar xzf prometheus-3.2.1.linux-amd64.tar.gz
sudo mv prometheus-3.2.1.linux-amd64/prometheus /usr/local/bin/

# Use the config from this repo
prometheus \
  --config.file=/opt/karman/monitoring/prometheus/prometheus.yml \
  --web.listen-address=:9091 \
  --storage.tsdb.retention.time=30d &
```

**gnmic:**
```bash
# Download from https://github.com/openconfig/gnmic/releases
curl -sL https://github.com/openconfig/gnmic/releases/latest/download/gnmic_linux_x86_64 \
  -o /usr/local/bin/gnmic && chmod +x /usr/local/bin/gnmic

GNMIC_USERNAME=admin GNMIC_PASSWORD=yourpassword \
  gnmic subscribe --config /opt/karman/monitoring/gnmic/gnmic.yml &
```

---

## Environment Variables Reference

| Variable | Default | Description |
|----------|---------|-------------|
| `SECRET_KEY` | `change-me-in-production` | Flask session secret — **change this** |
| `FLASK_ENV` | `production` | `production` or `development` |
| `DATABASE_PATH` | `/app/data/custom-cvp.db` | SQLite DB path |
| `DEFAULT_DEVICE_USERNAME` | `admin` | Username for device connections |
| `DEFAULT_DEVICE_PASSWORD` | _(empty)_ | Password for device connections |
| `PROMETHEUS_URL` | `http://localhost:9091` | Prometheus base URL |
| `PROMETHEUS_PORT` | `9091` | Prometheus listen port |
| `TELEGRAF_METRICS_PORT` | `9273` | gnmic Prometheus metrics port |
| `GNMIC_INGEST_METRICS_PORT` | `9274` | gnmic-listener metrics port |
| `LOG_LEVEL` | `INFO` | Logging level |

---

## First Time Setup

1. Open `http://<server>:5000` and register — you become admin automatically.
2. Go to **Devices → Add Device** and enter your device's hostname, IP, and management type.
   - Kármán auto-detects the management type by probing TCP ports 443, 22, and 6030.
3. The dashboard begins polling immediately. Telemetry refreshes every ~30 seconds.
4. To configure email alerts: **Admin → Settings → Email**.

---

## Device Prerequisites (EOS)

### eAPI (HTTPS/HTTP)
```
management api http-commands
   protocol https
   no shutdown
   vrf management
```
> Kármán automatically falls back from HTTPS to HTTP if the SSL handshake fails (common on vEOS-lab).

### SSH
```
username admin privilege 15 secret yourpassword
management ssh
   idle-timeout 60
   no shutdown
   vrf management
```

### gNMI / TerminAttr
```
# TerminAttr — specify VRF if management interface is in a VRF
daemon TerminAttr
   exec /usr/bin/TerminAttr -grpcaddr=mgmt/0.0.0.0:6030 -disableaaa
   no shutdown
```
> `management api gnmi` and TerminAttr **cannot share the same port**. Use one or the other.

---

## Architecture

```
Browser
  │
  ▼
Flask (web/app.py)  ─── SQLite (custom-cvp.db)
  │
  ├── eAPI connector    → Arista EOS port 443/80
  ├── SSH connector     → Arista EOS port 22
  ├── gNMI connector    → Arista EOS port 6030
  │
  └── Prometheus API ─── Prometheus ─── gnmic ─── Arista EOS gNMI
```

**Background telemetry** runs every ~30 seconds in a daemon thread, caching device status in SQLite. A DB-level lock prevents concurrent polls across gunicorn workers.

**Monitoring stack** (optional but needed for Metrics tab graphs):
- `gnmic` — dials out to devices on port 6030, exposes interface metrics on port 9273
- `gnmic-listener` — receives dial-out streams from TerminAttr on port 9910
- `Prometheus` — scrapes gnmic on port 9273/9274, retains 30 days of data

---

## Upgrading

```bash
git pull
docker compose up -d --build   # Docker
# or
pip install -r requirements.txt && sudo systemctl restart karman   # bare metal
```

Database migrations run automatically on startup — no manual schema changes needed.

---

## Troubleshooting

| Symptom | Likely cause | Fix |
|---------|-------------|-----|
| Device shows DOWN | No route, wrong credentials, or eAPI disabled | Check device eAPI config; verify IP reachability |
| `Collection timeout` | Too many devices / slow network | Increase `as_completed` timeout in `web/app.py` |
| Metrics tab shows no data | gnmic not running or wrong target IPs | Check `docker logs karman-gnmic` |
| 500 error on LLDP | Command returns text instead of JSON | Already handled — update to latest code |
| SSL handshake timeout | vEOS-lab HTTPS is slow | Automatic HTTP fallback handles this |

```bash
# Check all service logs
docker compose logs -f

# Check specific service
docker logs karman-gnmic -f

# Manually test device connectivity from inside container
docker exec custom-cvp-docker python3 -c "
import pyeapi
from pyeapi.client import Node
conn = pyeapi.connect(transport='http', host='10.0.0.1', username='admin', password='pass', port=80, timeout=10)
print(Node(conn).enable(['show version'])[0]['result']['modelName'])
"
```
