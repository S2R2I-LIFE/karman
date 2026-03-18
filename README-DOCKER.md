# Kármán - Docker Quick Start

Deploy Kármán as a containerized management device in minutes.

---

## One-Line Deployment

```bash
./deploy.sh
```

This script will:
- ✅ Check Docker/Docker Compose installation
- ✅ Create required directories
- ✅ Generate .env configuration
- ✅ Copy existing database
- ✅ Build container image
- ✅ Start the application
- ✅ Verify health

---

## Manual Deployment

### 1. Prerequisites

- Docker Engine 20.10+
- Docker Compose 2.0+
- 2GB RAM minimum
- 10GB disk space

### 2. Setup

```bash
# Create directories
mkdir -p data logs output/generated-configs

# Copy database (if you have one)
cp custom-cvp.db data/

# Configure environment
cp .env.example .env
nano .env  # Edit as needed
```

### 3. Deploy

```bash
# Build and start
docker compose up -d

# View logs
docker compose logs -f

# Check health
curl http://localhost:5000/health
```

### 4. Access

**URL:** http://localhost:5000

**Default credentials:**
- Username: `admin`
- Password: `admin`

**⚠️ Change these immediately!**

---

## Management Commands

```bash
# Start/Stop
docker compose up -d
docker compose down

# Restart
docker compose restart

# View logs
docker compose logs -f

# Shell access
docker compose exec custom-cvp bash

# Check status
docker compose ps
```

---

## Network Configuration

### Lab Network Integration

**Option 1: Host Network (Simplest)**

Edit `docker-compose.yml`:
```yaml
services:
  custom-cvp:
    network_mode: host
```

Application available at: `http://<host-ip>:5000`

**Option 2: Bridge to Physical Interface**

Edit `docker-compose.yml`:
```yaml
networks:
  cvp-network:
    driver: macvlan
    driver_opts:
      parent: eth0
    ipam:
      config:
        - subnet: 10.0.0.0/24
          gateway: 10.0.0.1

services:
  custom-cvp:
    networks:
      cvp-network:
        ipv4_address: 10.0.0.100
```

---

## Lab Integrations

### EVE-NG

1. Add Docker container node
2. Select `custom-cvp:latest` image
3. Connect to management network
4. Start node
5. Access at container IP

### ContainerLab

```yaml
name: arista-lab

topology:
  nodes:
    mgmt:
      kind: linux
      image: custom-cvp:latest
      ports:
        - 5000:5000

    leaf1:
      kind: ceos
      image: ceos:latest

  links:
    - endpoints: ["mgmt:eth1", "leaf1:eth0"]
```

Deploy:
```bash
sudo containerlab deploy -t lab.yml
```

### GNS3

1. Add Docker container
2. Link custom-cvp image
3. Connect to management cloud
4. Configure port mapping

---

## Backup & Restore

### Backup

```bash
# Database
docker cp custom-cvp:/app/data/custom-cvp.db ./backup-$(date +%Y%m%d).db

# Complete backup
tar czf backup.tar.gz data/ output/ logs/ .env
```

### Restore

```bash
# Copy database
cp backup-20260121.db data/custom-cvp.db

# Restore all
tar xzf backup.tar.gz

# Restart
docker compose restart
```

---

## Troubleshooting

### Can't access web UI

```bash
# Check container status
docker compose ps

# Check logs
docker compose logs custom-cvp

# Test health
curl http://localhost:5000/health
```

### Port 5000 in use

Edit `docker-compose.yml`:
```yaml
ports:
  - "5001:5000"  # Use port 5001 instead
```

### Database issues

```bash
# Check database exists
ls -la data/custom-cvp.db

# Copy from root
cp custom-cvp.db data/

# Fix permissions
chmod 644 data/custom-cvp.db
```

### Container won't start

```bash
# View detailed logs
docker compose logs --tail=100 custom-cvp

# Rebuild
docker compose down
docker compose build --no-cache
docker compose up -d
```

---

## Production Deployment

### Security Checklist

- [ ] Change default admin password
- [ ] Set strong SECRET_KEY in .env
- [ ] Enable firewall rules
- [ ] Use HTTPS (reverse proxy)
- [ ] Restrict network access
- [ ] Enable log rotation
- [ ] Setup automated backups
- [ ] Configure resource limits

### Recommended .env

```bash
SECRET_KEY=<generate-random-32-bytes>
FLASK_ENV=production
DEFAULT_USERNAME=cvpadmin
DEFAULT_PASSWORD=<strong-password>
LOG_LEVEL=WARNING
GUNICORN_WORKERS=8
```

---

## Resources

**Documentation:**
- Full deployment guide: `DOCKER_DEPLOYMENT.md`
- Builder quick start: `BUILDER_QUICK_START.md`
- Configlet builder: `CONFIGLET_BUILDER_COMPLETE.md`

**Support:**
- Health endpoint: `http://localhost:5000/health`
- Application logs: `docker compose logs`
- Container shell: `docker compose exec custom-cvp bash`

---

## Quick Reference

| Command | Purpose |
|---------|---------|
| `./deploy.sh` | One-line deployment |
| `docker compose up -d` | Start application |
| `docker compose down` | Stop application |
| `docker compose logs -f` | View logs |
| `docker compose restart` | Restart application |
| `docker compose ps` | Check status |
| `curl localhost:5000/health` | Health check |

---

**Status: Ready for deployment** ✅

Access: http://localhost:5000
Credentials: admin / admin (change immediately!)
