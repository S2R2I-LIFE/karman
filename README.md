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
| `KARMAN_BASE_URL` | `http://localhost:5000` | Public URL used in email notification links — set to your server's IP or hostname |
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

What you configure on the switch depends on which management type you select in Kármán. You can enable multiple protocols on the same device — Kármán will use whichever type is set in the inventory.

---

### Management interface / VRF (all types)

Most Arista switches keep the management port in a dedicated `management` VRF. Make sure it is configured before enabling any of the APIs below:

```
vrf instance management

interface Management0
   vrf management
   ip address 192.168.1.10/24

ip route vrf management 0.0.0.0/0 192.168.1.1

! Allow the switch to reach Kármán (and vice versa)
```

> If your switches use the **default VRF** for management (common in lab/vEOS-lab builds), omit the `vrf management` keywords from all configs below.

---

### eAPI — HTTP/HTTPS (recommended for most deployments)

Kármán uses eAPI to collect telemetry (`show version`, `show interfaces status`, `show processes top once`, `show system environment temperature`) and to push configuration changes.

**With management VRF:**
```
management api http-commands
   protocol https
   no shutdown
   vrf management
```

**Without management VRF (default VRF / vEOS-lab):**
```
management api http-commands
   protocol https
   no shutdown
```

**HTTP only (no TLS — lab use only):**
```
management api http-commands
   protocol http
   no shutdown
```

> Kármán automatically falls back from HTTPS to HTTP if the TLS handshake fails or times out. This is normal on vEOS-lab which does not have a valid certificate.

Verify eAPI is working from the switch CLI:
```
show management api http-commands
```

---

### SSH

Used as a fallback when eAPI is unavailable, or when a device is explicitly set to SSH management type. Kármán uses Netmiko to parse `show` command text output.

```
! Create a user with privilege 15
username admin privilege 15 secret 0 yourpassword

! Enable SSH on the management VRF
management ssh
   idle-timeout 60
   no shutdown
   vrf management
```

**Without management VRF:**
```
management ssh
   idle-timeout 60
   no shutdown
```

Verify:
```
show management ssh
```

---

### gNMI / TerminAttr (for interface Metrics tab and streaming telemetry)

gNMI is required for the **Metrics tab** — real-time interface graphs and link flap history. Kármán connects to port 6030 on each device.

There are two ways to expose gNMI on an Arista switch:

#### Option A — TerminAttr (recommended, works on vEOS-lab without CVP)

TerminAttr is the Arista streaming agent. It exposes gNMI on port 6030 independently of CVP.

**With management VRF:**
```
daemon TerminAttr
   exec /usr/bin/TerminAttr \
      -grpcaddr=mgmt/0.0.0.0:6030 \
      -disableaaa
   no shutdown
```

**Without management VRF / using default VRF (most lab setups):**
```
daemon TerminAttr
   exec /usr/bin/TerminAttr \
      -grpcaddr=default/0.0.0.0:6030 \
      -disableaaa
   no shutdown
```

> **VRF must be specified in `-grpcaddr`** — using `0.0.0.0:6030` without a VRF name will bind to the default VRF only and may not be reachable from the management VRF, or vice versa. Match the VRF to whichever VRF your management IP lives in.

> **`-disableaaa`** skips AAA authentication on the gRPC port. Required on vEOS-lab where local AAA can interfere. Remove it in production if you want gNMI auth enforced.

Verify TerminAttr is running:
```
show daemon TerminAttr
```

#### Option B — `management api gnmi` (EOS native, no TerminAttr needed)

```
management api gnmi
   transport grpc default
      vrf management
   no shutdown
```

> **Do not run `management api gnmi` and TerminAttr on the same port (6030).** They will conflict. Use one or the other per device.

Verify:
```
show management api gnmi
```

#### TLS note

By default, vEOS-lab TerminAttr runs without TLS. Kármán's gNMI connector automatically detects this (SSL probe → falls back to plaintext). For production devices with TLS, no code changes are needed — Kármán will complete the TLS handshake normally.

---

### What data each protocol provides

| Data | eAPI | SSH | gNMI |
|------|------|-----|------|
| EOS version / model | Yes | Yes | No (vEOS-lab) |
| Interface up/down count | Yes | Yes | Yes |
| CPU / memory | Yes | Yes | No (vEOS-lab) |
| Temperature sensors | Yes | Yes | No (vEOS-lab) |
| Interface Metrics graphs | No | No | **Yes** |
| Link flap history | No | No | **Yes** |
| LLDP topology | Yes | Yes | No |
| Config push | Yes | Yes | No |

> On production hardware with CVP, gNMI exposes version and temperature via OpenConfig paths. On vEOS-lab without CVP those paths return empty — Kármán uses `eos_native` paths for interface status which are always available.

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

## Karman-Link — Local Agent (Switch Ingest)

Karman-Link bridges a factory-reset or unconfigured Arista switch to Kármán from an engineer's
laptop, without needing the switch to be on the management network first.

### How it works

1. Cable your laptop's ethernet port to the switch's **Management0** port.
2. Generate an API key in **Admin → Agent Keys**.
3. Run the agent on your laptop:

```bash
cd karman-link
pip install -r requirements.txt
python karman_link.py --server https://karman.example.com --key <api_key>
```

4. The agent auto-discovers the switch at `192.168.0.1` (Arista factory default) and appears on
   the **Ingest** page in Kármán.
5. Choose a workflow in the UI:

| Workflow | When to use |
|----------|-------------|
| **New Switch** | Factory-reset hardware. Agent connects as `admin` (no password) over HTTP and pushes management IP, eAPI, SSH, and optionally TerminAttr. |
| **Adopt Existing** | Switch already has an IP and credentials. Agent connects with your creds and pushes only the missing Kármán integration config (eAPI / SSH / TerminAttr). |

6. Once provisioning completes, run **Ingest** to collect `show version`, interfaces, LLDP,
   running-config, environment, and BGP summary.
7. Click **Add to Inventory** to register the device in Kármán with all discovered metadata
   pre-filled.

### CLI flags

| Flag | Default | Description |
|------|---------|-------------|
| `--server` | _(required)_ | Kármán server URL, e.g. `http://10.0.0.1:5000` |
| `--key` | _(required)_ | API key from Admin → Agent Keys |
| `--switch-ip` | auto (192.168.0.1) | Override switch discovery IP |
| `--debug` | off | Verbose logging |

### Testing in a lab (EVE-NG / GNS3)

vEOS-lab nodes do not auto-start eAPI on `192.168.0.1` like physical hardware. To test the
**New Switch** flow in a lab:

- Run karman-link directly on the EVE-NG host — it has direct IP reachability to all nodes.
- Use `--switch-ip <veos-mgmt-ip>` to skip factory-IP discovery.
- Give the vEOS node a minimal startup config so eAPI HTTP is already listening when the agent connects:

```
management api http-commands
   protocol http
   no shutdown
interface Management0
   ip address 192.168.100.50/24
ip route 0.0.0.0/0 192.168.100.1
```

The **Adopt Existing** workflow works against any running vEOS node with no special setup — just
provide its IP and credentials in the UI.

> **Note:** After the New Switch provisioning pushes a new management IP to a vEOS node, the
> original IP remains reachable in EVE-NG (it's a VM). On real hardware the laptop cable comes out
> and only the new IP is reachable — this difference is cosmetic for testing purposes.

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
