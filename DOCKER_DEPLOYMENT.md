# Kármán - Docker Deployment Guide

**Version:** 1.0.0
**Date:** 2026-01-21

---

## Overview

This guide covers deploying Kármán as a containerized management device in your lab environment.

---

## Quick Start

### 1. Prerequisites

**On your lab management host:**
- Docker Engine 20.10+ installed
- Docker Compose 2.0+ installed
- 2GB RAM minimum (4GB recommended)
- 10GB disk space
- Network connectivity to your Arista devices

**Check versions:**
```bash
docker --version
docker compose version
```

### 2. Clone or Copy Application

```bash
# If using git
git clone <repository-url> /opt/custom-cvp
cd /opt/custom-cvp

# Or copy the application directory
cp -r /home/b/cvp/custom-cvp /opt/custom-cvp
cd /opt/custom-cvp
```

### 3. Configure Environment

```bash
# Copy environment template
cp .env.example .env

# Edit with your preferences
nano .env
```

**Minimum configuration:**
```bash
SECRET_KEY=your-random-secret-key-here
DEFAULT_USERNAME=admin
DEFAULT_PASSWORD=ChangeMe123!
FLASK_ENV=production
```

**Generate secure secret key:**
```bash
python3 -c "import secrets; print(secrets.token_hex(32))"
```

### 4. Prepare Data Directory

```bash
# Create required directories
mkdir -p data logs output/generated-configs

# Copy existing database (if you have one)
cp custom-cvp.db data/custom-cvp.db

# Set permissions
chmod 755 data logs output
```

### 5. Build and Deploy

```bash
# Build the container
docker compose build

# Start the application
docker compose up -d

# View logs
docker compose logs -f
```

### 6. Access the Application

**Web Interface:**
```
http://<your-lab-host-ip>:5000
```

**Default credentials:**
- Username: `admin`
- Password: `admin` (or whatever you set in .env)

---

## Architecture

### Container Structure

```
┌─────────────────────────────────────┐
│   Kármán Container              │
│                                     │
│  ┌──────────────────────────────┐  │
│  │  Flask Web Application       │  │
│  │  - Port 5000                 │  │
│  │  - Gunicorn WSGI Server      │  │
│  └──────────────────────────────┘  │
│                                     │
│  ┌──────────────────────────────┐  │
│  │  SQLite Database             │  │
│  │  - /app/data/custom-cvp.db   │  │
│  └──────────────────────────────┘  │
│                                     │
│  ┌──────────────────────────────┐  │
│  │  Configlet Builder           │  │
│  │  - Jinja2 Templates          │  │
│  │  - YAML Variables            │  │
│  └──────────────────────────────┘  │
└─────────────────────────────────────┘
         │
         │ Port 5000
         ▼
    Lab Network
         │
         ├─── Arista Leaf Switches
         ├─── Arista Spine Switches
         └─── Other Network Devices
```

### Volume Mounts

| Container Path | Host Path | Purpose |
|----------------|-----------|---------|
| `/app/data` | `./data` | SQLite database (persistent) |
| `/app/output` | `./output` | Generated configurations |
| `/app/logs` | `./logs` | Application logs |
| `/app/templates` | `./templates` | Jinja2 templates (read-only) |
| `/app/variables` | `./variables` | Device variables (read-only) |

---

## Network Configuration

### Default Network Settings

**Docker Compose creates:**
- Network: `cvp-network`
- Subnet: `172.20.0.0/16`
- Driver: `bridge`

### Port Mappings

| Service | Container Port | Host Port | Protocol |
|---------|---------------|-----------|----------|
| Web UI | 5000 | 5000 | HTTP |

### Connect to Lab Network

To connect the container to your existing lab network:

**Option 1: Bridge to Physical Interface**

Edit `docker-compose.yml`:
```yaml
networks:
  cvp-network:
    driver: macvlan
    driver_opts:
      parent: eth0  # Your lab network interface
    ipam:
      config:
        - subnet: 10.0.0.0/24  # Your lab subnet
          gateway: 10.0.0.1
```

Then assign a static IP:
```yaml
services:
  custom-cvp:
    networks:
      cvp-network:
        ipv4_address: 10.0.0.100
```

**Option 2: Host Network Mode** (simplest for lab)

Edit `docker-compose.yml`:
```yaml
services:
  custom-cvp:
    network_mode: host
    # Remove ports section - not needed in host mode
```

Application will be accessible at `http://<host-ip>:5000`

---

## Management Commands

### Start/Stop/Restart

```bash
# Start
docker compose up -d

# Stop
docker compose down

# Restart
docker compose restart

# View status
docker compose ps
```

### View Logs

```bash
# Follow logs
docker compose logs -f

# View last 100 lines
docker compose logs --tail=100

# Service-specific logs
docker compose logs custom-cvp

# Export logs
docker compose logs > custom-cvp.log
```

### Execute Commands in Container

```bash
# Open shell
docker compose exec custom-cvp bash

# Run builder
docker compose exec custom-cvp python3 builder.py --device leaf1.yaml --templates [...]

# Check database
docker compose exec custom-cvp ls -lh /app/data/

# View Python version
docker compose exec custom-cvp python3 --version
```

### Update Container

```bash
# Pull latest code/changes
git pull  # or copy updated files

# Rebuild and restart
docker compose down
docker compose build --no-cache
docker compose up -d
```

---

## Backup and Restore

### Backup Database

```bash
# Manual backup
docker compose exec custom-cvp cp /app/data/custom-cvp.db /app/data/custom-cvp.db.backup

# Copy to host
docker cp custom-cvp:/app/data/custom-cvp.db ./backup-$(date +%Y%m%d-%H%M%S).db

# Automated backup script
cat > backup.sh << 'EOF'
#!/bin/bash
DATE=$(date +%Y%m%d-%H%M%S)
docker compose exec custom-cvp sqlite3 /app/data/custom-cvp.db ".backup '/app/data/backup-$DATE.db'"
docker cp custom-cvp:/app/data/backup-$DATE.db ./backups/
echo "Backup completed: backup-$DATE.db"
EOF
chmod +x backup.sh
```

### Restore Database

```bash
# Copy backup to container
docker cp backup-20260121-120000.db custom-cvp:/app/data/

# Restore in container
docker compose exec custom-cvp cp /app/data/backup-20260121-120000.db /app/data/custom-cvp.db

# Restart application
docker compose restart
```

### Backup Entire Application

```bash
# Create tarball of all persistent data
tar czf custom-cvp-backup-$(date +%Y%m%d).tar.gz \
  data/ \
  output/ \
  logs/ \
  templates/ \
  variables/ \
  .env

# Restore
tar xzf custom-cvp-backup-20260121.tar.gz
```

---

## Monitoring

### Health Checks

**Built-in health endpoint:**
```bash
curl http://localhost:5000/health
```

**Expected response:**
```json
{
  "status": "healthy",
  "timestamp": "2026-01-21T23:30:00",
  "database": "connected",
  "version": "1.0.0"
}
```

**Monitor health:**
```bash
# Continuous monitoring
watch -n 5 'curl -s http://localhost:5000/health | jq'

# Docker health status
docker inspect custom-cvp --format='{{.State.Health.Status}}'
```

### Resource Usage

```bash
# Container stats
docker stats custom-cvp

# Detailed resource usage
docker compose exec custom-cvp top

# Disk usage
docker compose exec custom-cvp df -h
```

### Application Logs

**Log locations in container:**
- Application: `/app/logs/error.log`
- Access: `/app/logs/access.log`
- Gunicorn: stdout/stderr (captured by Docker)

**View logs:**
```bash
# Application errors
docker compose exec custom-cvp tail -f /app/logs/error.log

# Web access logs
docker compose exec custom-cvp tail -f /app/logs/access.log

# Combined
docker compose logs -f --tail=100 custom-cvp
```

---

## Troubleshooting

### Container Won't Start

**Check logs:**
```bash
docker compose logs custom-cvp
```

**Common issues:**

1. **Port 5000 already in use:**
   ```bash
   # Check what's using port 5000
   sudo netstat -tulpn | grep 5000

   # Change port in docker-compose.yml
   ports:
     - "5001:5000"  # Map to different host port
   ```

2. **Permission issues:**
   ```bash
   # Fix permissions
   sudo chown -R 1000:1000 data/ logs/ output/
   chmod 755 data/ logs/ output/
   ```

3. **Database not found:**
   ```bash
   # Check if database exists
   ls -la data/custom-cvp.db

   # Copy from root if needed
   cp custom-cvp.db data/
   ```

### Health Check Failing

```bash
# Check if Flask is running
docker compose exec custom-cvp ps aux | grep gunicorn

# Test health endpoint from inside container
docker compose exec custom-cvp curl http://localhost:5000/health

# Check database
docker compose exec custom-cvp ls -la /app/data/custom-cvp.db
```

### Can't Access Web UI

```bash
# Verify container is running
docker compose ps

# Check port mapping
docker port custom-cvp

# Test from host
curl http://localhost:5000/health

# Check firewall
sudo ufw status
sudo iptables -L | grep 5000
```

### Performance Issues

```bash
# Check resource limits
docker stats custom-cvp

# Increase Gunicorn workers in docker-compose.yml
environment:
  - GUNICORN_WORKERS=8  # Increase from 4

# Allocate more resources
docker compose down
docker compose up -d --scale custom-cvp=1 --force-recreate
```

### Database Locked

```bash
# Check for active connections
docker compose exec custom-cvp lsof /app/data/custom-cvp.db

# Restart to clear locks
docker compose restart
```

---

## Security Best Practices

### Change Default Credentials

**Before production deployment:**
```bash
# Edit .env
nano .env

# Set strong passwords
DEFAULT_USERNAME=cvpadmin
DEFAULT_PASSWORD=$(python3 -c "import secrets; print(secrets.token_urlsafe(20))")
SECRET_KEY=$(python3 -c "import secrets; print(secrets.token_hex(32))")
```

### Network Security

**Restrict access to management network:**

1. **Use firewall rules:**
   ```bash
   sudo ufw allow from 10.0.0.0/24 to any port 5000 proto tcp
   sudo ufw deny 5000
   ```

2. **Use reverse proxy (nginx):**
   ```yaml
   # docker-compose.yml
   services:
     nginx:
       image: nginx:alpine
       ports:
         - "443:443"
       volumes:
         - ./nginx.conf:/etc/nginx/nginx.conf:ro
         - ./certs:/etc/nginx/certs:ro

     custom-cvp:
       # Remove exposed ports
       expose:
         - "5000"
   ```

3. **Enable HTTPS:**
   - Use nginx/traefik as TLS termination proxy
   - Mount SSL certificates
   - Redirect HTTP to HTTPS

### Container Hardening

**Run as non-root (already configured):**
```dockerfile
USER cvpuser  # UID 1000
```

**Read-only filesystem (optional):**
```yaml
services:
  custom-cvp:
    read_only: true
    tmpfs:
      - /tmp
      - /app/logs
```

---

## Production Deployment

### Recommended Configuration

```yaml
# docker-compose.prod.yml
version: '3.8'

services:
  custom-cvp:
    build: .
    restart: always

    environment:
      - FLASK_ENV=production
      - SECRET_KEY=${SECRET_KEY}
      - GUNICORN_WORKERS=8
      - LOG_LEVEL=WARNING

    volumes:
      - /data/custom-cvp:/app/data
      - /data/custom-cvp/output:/app/output
      - /var/log/custom-cvp:/app/logs

    networks:
      - management

    deploy:
      resources:
        limits:
          cpus: '2.0'
          memory: 4G
        reservations:
          cpus: '1.0'
          memory: 2G

    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:5000/health"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 60s

    logging:
      driver: "json-file"
      options:
        max-size: "10m"
        max-file: "3"

networks:
  management:
    external: true
```

**Deploy:**
```bash
docker compose -f docker-compose.prod.yml up -d
```

### High Availability

For HA deployment, consider:

1. **Load Balancer:** HAProxy or nginx upstream
2. **Shared Storage:** NFS for database and configs
3. **Database Replication:** Use PostgreSQL instead of SQLite
4. **Container Orchestration:** Kubernetes or Docker Swarm

---

## Integration with Lab Environment

### EVE-NG / GNS3 Integration

**Add container as management node:**

1. **EVE-NG:**
   - Add "Docker" node
   - Select `custom-cvp` image
   - Connect to management network
   - Start node

2. **GNS3:**
   - Add Docker container
   - Link to management cloud
   - Configure port forwarding

### Arista cEOS Integration

**Connect to cEOS containers:**

```yaml
# docker-compose.yml with cEOS
services:
  custom-cvp:
    # ... existing config ...
    networks:
      - lab-network

  leaf1:
    image: ceos:latest
    networks:
      - lab-network
    environment:
      - CEOS=1

  leaf2:
    image: ceos:latest
    networks:
      - lab-network

networks:
  lab-network:
    driver: bridge
```

### ContainerLab Integration

```yaml
# containerlab.yml
name: arista-lab

topology:
  nodes:
    custom-cvp:
      kind: linux
      image: custom-cvp:latest
      ports:
        - 5000:5000

    leaf1:
      kind: ceos
      image: ceos:4.29.2F

    spine1:
      kind: ceos
      image: ceos:4.29.2F

  links:
    - endpoints: ["custom-cvp:eth1", "leaf1:eth0"]
    - endpoints: ["custom-cvp:eth1", "spine1:eth0"]
```

**Deploy:**
```bash
sudo containerlab deploy -t containerlab.yml
```

---

## Maintenance

### Regular Tasks

**Weekly:**
- Check logs for errors
- Verify backups completed
- Review disk usage
- Update device inventory

**Monthly:**
- Update container image
- Rotate logs
- Clean old backups
- Review security settings

**Scripts:**

```bash
# /opt/custom-cvp/maintenance.sh
#!/bin/bash

# Weekly maintenance script
DATE=$(date +%Y%m%d-%H%M%S)
LOG="/var/log/custom-cvp-maintenance.log"

echo "[$DATE] Starting maintenance" >> $LOG

# Backup database
docker compose exec custom-cvp cp /app/data/custom-cvp.db /app/data/backup-$DATE.db
echo "[$DATE] Database backed up" >> $LOG

# Clean old logs
find ./logs -name "*.log" -mtime +30 -delete
echo "[$DATE] Old logs cleaned" >> $LOG

# Check health
HEALTH=$(curl -s http://localhost:5000/health | jq -r .status)
echo "[$DATE] Health check: $HEALTH" >> $LOG

# Rotate backups (keep last 30 days)
find ./data -name "backup-*.db" -mtime +30 -delete
echo "[$DATE] Old backups cleaned" >> $LOG

echo "[$DATE] Maintenance complete" >> $LOG
```

**Add to cron:**
```bash
# Edit crontab
crontab -e

# Run weekly on Sunday at 2 AM
0 2 * * 0 /opt/custom-cvp/maintenance.sh
```

---

## Appendix

### Environment Variables Reference

| Variable | Default | Description |
|----------|---------|-------------|
| `FLASK_ENV` | `production` | Flask environment (development/production) |
| `SECRET_KEY` | Random | Flask secret key for sessions |
| `DATABASE_PATH` | `/app/data/custom-cvp.db` | SQLite database path |
| `DEFAULT_USERNAME` | `admin` | Default admin username |
| `DEFAULT_PASSWORD` | `admin` | Default admin password |
| `LOG_LEVEL` | `INFO` | Logging level (DEBUG/INFO/WARNING/ERROR) |
| `GUNICORN_WORKERS` | `4` | Number of Gunicorn worker processes |
| `GUNICORN_TIMEOUT` | `120` | Worker timeout in seconds |

### Port Reference

| Port | Service | Purpose |
|------|---------|---------|
| 5000 | Flask/Gunicorn | Web UI and API |

### File Structure

```
/opt/custom-cvp/
├── Dockerfile                 # Container build instructions
├── docker-compose.yml         # Compose configuration
├── .env                       # Environment variables
├── .dockerignore             # Files to exclude from build
├── requirements.txt          # Python dependencies
├── data/                     # Persistent database
│   └── custom-cvp.db
├── logs/                     # Application logs
│   ├── access.log
│   └── error.log
├── output/                   # Generated configurations
│   └── generated-configs/
├── templates/                # Jinja2 templates
│   ├── base/
│   ├── layer2/
│   ├── layer3/
│   └── overlays/
├── variables/                # Device variables
│   └── device-vars/
└── web/                      # Web application
    ├── app.py
    ├── static/
    └── templates/
```

---

## Support

### Documentation
- **README.md** - Application overview
- **DOCKER_DEPLOYMENT.md** - This file
- **BUILDER_QUICK_START.md** - Configlet builder guide
- **CONFIGLET_BUILDER_COMPLETE.md** - Complete builder documentation

### Logs Location
- Container logs: `docker compose logs`
- Application logs: `./logs/error.log`
- Access logs: `./logs/access.log`

### Common Issues
See "Troubleshooting" section above

---

## Status: Production Ready ✅

- ✅ Dockerfile created
- ✅ Docker Compose configuration
- ✅ Health check endpoint
- ✅ Volume mounts for persistence
- ✅ Non-root user (security)
- ✅ Gunicorn production server
- ✅ Logging configured
- ✅ Documentation complete

**The application is ready for containerized deployment in your lab environment!**
