# Kármán — Self-Hosted Arista Network Management

Self-hosted alternative to Arista CloudVision Portal. Manages Arista EOS devices via eAPI, SSH, and gNMI.

---

## Requirements

- Docker 24+ with Compose v2
- Linux host with network reachability to your devices
- Ports open to devices: **443/80** (eAPI), **22** (SSH), **6030** (gNMI)

---

## Install

```bash
git clone <repo-url> karman
cd karman
```

Edit `.env` — three values matter:

```ini
SECRET_KEY=        # python3 -c "import secrets; print(secrets.token_hex(32))"
DEFAULT_DEVICE_USERNAME=admin
DEFAULT_DEVICE_PASSWORD=yourpassword
```

```bash
docker compose up -d --build
```

Open `http://<server-ip>:5000`. First user to register becomes admin.

---

## Services

| Container | Purpose | Port |
|-----------|---------|------|
| `custom-cvp-docker` | Web UI + API | 5000 |
| `karman-gnmic` | gNMI dial-in collector | — |
| `karman-gnmic-listener` | gNMI dial-out receiver | 9910 |
| `karman-prometheus` | Metrics storage | 9091 |

---

## Device Config (EOS)

Minimum config for each management type. Use whichever protocols you want — Kármán auto-detects on add.

**eAPI (recommended):**
```
management api http-commands
   protocol https
   no shutdown
```

**SSH:**
```
username admin privilege 15 secret yourpassword
management ssh
   no shutdown
```

**gNMI / TerminAttr (required for Metrics graphs):**
```
daemon TerminAttr
   exec /usr/bin/TerminAttr -grpcaddr=default/0.0.0.0:6030 -allowed-ips=0.0.0.0/0 -disableaaa
   no shutdown
```

> If management is in a VRF, replace `default` with `mgmt` in `-grpcaddr`.
> Do **not** run `management api gnmi` and TerminAttr on the same port.

---

## Zero Touch Provisioning

Boot a new switch with no startup config → it gets DHCP option 67 → downloads and runs the ZTP script → registers itself in Kármán with a permanent management IP.

**Enable:** Admin → Zero Touch Provisioning

1. Set **Kármán Base URL** to `http://<your-server-ip>:5000`
2. Enable **Built-in DHCP Server**, set interface/range/gateway
3. Enable **Management IP Pool** — set a static IP range (e.g. `192.168.2.10`–`192.168.2.50`)
4. Start the DHCP server
5. Boot a switch — it appears in inventory within ~60 seconds

The built-in Python DHCP server responds **only to Arista vendor-class packets** — it does not interfere with your existing router or other devices.

---

## ZTP Script (manual / external DHCP)

If you have your own DHCP server, point option 67 at the script URL and skip the built-in server:

```
# dnsmasq
dhcp-match=set:arista,option:vendor-class,Arista
dhcp-boot=tag:arista,http://<karman-ip>:5000/ztp/script
```

---

## Useful Commands

```bash
# Logs
docker logs custom-cvp-docker -f

# Restart after code changes (live-mounted — no rebuild needed)
docker compose restart custom-cvp

# Full rebuild (after Dockerfile or requirements.txt changes)
docker compose up -d --build

# Stop
docker compose down

# Stop + delete all data
docker compose down -v
```

---

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `SECRET_KEY` | — | Flask session secret — **set this** |
| `DEFAULT_DEVICE_USERNAME` | `admin` | Device login username |
| `DEFAULT_DEVICE_PASSWORD` | — | Device login password |
| `KARMAN_BASE_URL` | `http://localhost:5000` | Public URL (used in email links) |
| `DATABASE_PATH` | `/app/data/custom-cvp.db` | SQLite DB path |
| `PROMETHEUS_URL` | `http://localhost:9091` | Prometheus URL |
| `PROMETHEUS_PORT` | `9091` | Prometheus listen port |
| `TELEGRAF_METRICS_PORT` | `9273` | gnmic metrics port |
| `LOG_LEVEL` | `INFO` | Logging verbosity |

---

## Upgrade

```bash
git pull
docker compose up -d --build
```

DB migrations run automatically on startup.

---

## Troubleshooting

| Symptom | Fix |
|---------|-----|
| Device shows DOWN | Check eAPI config on switch; verify IP reachability |
| Metrics tab empty | `docker logs karman-gnmic` — check target IPs and credentials |
| DHCP server won't start | Ensure `NET_BIND_SERVICE` cap and `user: root` in `docker-compose.yml` |
| Switch hits Arista cloud ZTP URL | Another DHCP server is winning — verify option 60 vendor-class in tcpdump |
| Switch gets wrong IP after reload | Enable Management IP Pool in ZTP settings |
| 500 on any page | `docker logs custom-cvp-docker --tail=100` — look for Traceback |
| BGP page empty | Wait one telemetry cycle (~30s) — cache warms on first poll |
