# Kármán - Deployment Checklist

## ✅ Pre-Deployment Cleanup (COMPLETED)

- [x] Removed 10 old database backup files
- [x] Removed corrupted root database file
- [x] Cleaned Python cache directories (__pycache__)
- [x] Removed compiled Python files (*.pyc, *.pyo)
- [x] Cleaned generated config files
- [x] Archived 19 development documentation files to `docs/archive/`
- [x] Organized 17 development scripts to `scripts/development/`
- [x] Organized 6 deployment scripts to `scripts/deployment/`
- [x] Created .dockerignore for efficient builds
- [x] Created .gitignore for version control
- [x] Created directory structure documentation

## 📋 Deployment Steps

### 1. Verify Environment

On the Docker host (192.168.2.38):
```bash
# Check Docker is running
docker --version
docker compose version

# Verify network route
ip route show | grep 172.100.100.0
# Should show: 172.100.100.0/24 via 192.168.2.153 dev pnet0
```

### 2. Deploy to Remote Server

```bash
# On your local machine, copy to remote server
rsync -avz --exclude='data/' --exclude='logs/' --exclude='output/' \
  /home/b/cvp/custom-cvp/ user@192.168.2.38:/opt/unetlab/custom-cvp/

# OR use scp
scp -r /home/b/cvp/custom-cvp/ user@192.168.2.38:/opt/unetlab/
```

### 3. On Remote Server (192.168.2.38)

```bash
cd /opt/unetlab/custom-cvp

# Ensure directories exist with correct permissions
mkdir -p data logs output/generated-configs
chmod 777 data logs output

# Build the Docker image
docker compose build --no-cache

# Start the container
docker compose up -d

# Watch logs for successful startup
docker logs -f custom-cvp-docker
```

### 4. Verify Deployment

```bash
# Check container is running
docker ps | grep custom-cvp

# Check logs show successful startup
docker logs custom-cvp-docker | grep "Default admin user created"

# Test web interface
curl http://192.168.2.38:5000/health

# Test from switches (on 192.168.2.153)
curl http://192.168.2.38:5000/health
```

### 5. First Login

1. Open browser: `http://192.168.2.38:5000`
2. Login with default credentials:
   - Username: `admin`
   - Password: `admin`
3. **IMMEDIATELY** go to Settings and change password
4. Test all features:
   - [ ] Dashboard loads
   - [ ] Device list works
   - [ ] Configlets load
   - [ ] CLI Browser accessible
   - [ ] Tasks page works
   - [ ] Settings page (theme toggle)
   - [ ] Dark mode works

### 6. Test Device Actions

From a device detail page:
- [ ] Sync Configuration button works
- [ ] Compliance Check button works
- [ ] Assign Configlet button works
- [ ] Connect button opens connection info

### 7. Test Configlet Actions

From a configlet detail page:
- [ ] Export downloads file
- [ ] Copy to Clipboard works
- [ ] Delete configlet works (with confirmation)

### 8. Test Builder

From the builder page:
- [ ] Build configuration works
- [ ] Validate button checks syntax
- [ ] Deploy creates task
- [ ] Create Task works

### 9. Production Hardening

```bash
# Set environment variables
cat > .env << EOF
SECRET_KEY=$(openssl rand -hex 32)
DEFAULT_USERNAME=admin
DEFAULT_PASSWORD=change-me-now
DEVICE_USERNAME=admin
DEVICE_PASSWORD=your-device-password
LOG_LEVEL=INFO
EOF

# Restart with new environment
docker compose down
docker compose up -d

# Verify new secret key is loaded
docker exec custom-cvp-docker env | grep SECRET_KEY
```

### 10. Backup Strategy

```bash
# Create backup script
cat > /opt/unetlab/custom-cvp/backup.sh << 'EOF'
#!/bin/bash
DATE=$(date +%Y%m%d_%H%M%S)
BACKUP_DIR="/opt/backups/custom-cvp"
mkdir -p $BACKUP_DIR

# Backup database
cp data/custom-cvp.db $BACKUP_DIR/custom-cvp-$DATE.db

# Keep only last 7 days
find $BACKUP_DIR -name "*.db" -mtime +7 -delete

echo "Backup completed: $BACKUP_DIR/custom-cvp-$DATE.db"
EOF

chmod +x /opt/unetlab/custom-cvp/backup.sh

# Add to cron (daily at 2 AM)
echo "0 2 * * * /opt/unetlab/custom-cvp/backup.sh" | crontab -
```

## 🎯 Post-Deployment Verification

### System Check
- [ ] Container running on host network (192.168.2.38:5000)
- [ ] Can reach switches at 172.100.100.2 and 172.100.100.3
- [ ] Switches can reach container at 192.168.2.38:5000
- [ ] Database persisted in `data/` directory
- [ ] Logs writing to `logs/` directory

### Feature Check
- [ ] All 4 device action buttons work
- [ ] All 3 configlet action buttons work
- [ ] All 3 builder action buttons work
- [ ] Settings page accessible
- [ ] Dark mode toggle works
- [ ] Theme persists across sessions

### Security Check
- [ ] Default password changed
- [ ] SECRET_KEY is randomized
- [ ] Device credentials set in environment
- [ ] .env file has proper permissions (600)

## 🔧 Troubleshooting

### Container won't start
```bash
# Check logs
docker logs custom-cvp-docker

# Check database permissions
ls -la data/

# Rebuild fresh
docker compose down
docker compose build --no-cache
docker compose up -d
```

### Database errors
```bash
# Verify migrations ran
docker exec custom-cvp-docker python /app/migrations/add_user_auth.py /app/data/custom-cvp.db verify

# Check database file
docker exec custom-cvp-docker ls -lh /app/data/
```

### Can't reach switches
```bash
# Verify route on host
ip route show | grep 172.100.100.0

# Test from container
docker exec custom-cvp-docker ping -c 3 172.100.100.2

# Add route if missing
sudo ip route add 172.100.100.0/24 via 192.168.2.153
```

### Switches can't reach container
```bash
# Test from switches (on VM at 192.168.2.153)
ssh admin@172.100.100.2 "curl -I http://192.168.2.38:5000/health"

# Verify host network mode
docker inspect custom-cvp-docker | grep NetworkMode
# Should show: "NetworkMode": "host"
```

## 📊 Monitoring

### Check container health
```bash
# Container status
docker ps

# Resource usage
docker stats custom-cvp-docker

# Recent logs
docker logs --tail 100 custom-cvp-docker
```

### Application logs
```bash
# Access logs (Gunicorn)
tail -f logs/access.log

# Error logs
tail -f logs/error.log
```

## 🎉 Deployment Complete!

Access your Kármán instance at:
**http://192.168.2.38:5000**

Default credentials (CHANGE IMMEDIATELY):
- Username: `admin`
- Password: `admin`

All features are now working:
✅ Device management with sync, compliance check, assign configlet, connect
✅ Configlet management with delete, export, copy
✅ Builder with validation, deployment, task creation
✅ Dark mode with light/dark/auto themes
✅ Settings page with user preferences
✅ User authentication and access control
✅ Full API endpoints
✅ CLI browser with progressive disclosure
