
## Network Configuration (Remote Server Only)

### One-time setup on EVE-NG host (192.168.2.38):

The switches are at 172.100.100.0/24 and accessible via Ubuntu VM at 192.168.2.153.

**Add persistent route:**

```bash
# Option 1: Using systemd (recommended)
cat > /etc/systemd/system/eve-switch-route.service << 'EOFSERVICE'
[Unit]
Description=Add route to containerlab switches
After=network.target

[Service]
Type=oneshot
ExecStart=/sbin/ip route add 172.100.100.0/24 via 192.168.2.153 dev pnet0
RemainAfterExit=yes

[Install]
WantedBy=multi-user.target
EOFSERVICE

systemctl daemon-reload
systemctl enable eve-switch-route.service
systemctl start eve-switch-route.service
```

**Or Option 2: Using rc.local (alternative):**

```bash
cat >> /etc/rc.local << 'EOFRC'
# Route to containerlab switches
ip route add 172.100.100.0/24 via 192.168.2.153 dev pnet0 2>/dev/null || true
EOFRC

chmod +x /etc/rc.local
```

**Verify route:**
```bash
ip route show | grep 172.100
ping -c 3 172.100.100.2
```

### Ubuntu VM (192.168.2.153) - IP Forwarding:

**Enable IP forwarding permanently:**
```bash
echo "net.ipv4.ip_forward = 1" | sudo tee -a /etc/sysctl.conf
sudo sysctl -p

# Add iptables rules
sudo iptables -A FORWARD -s 192.168.2.0/24 -d 172.100.100.0/24 -j ACCEPT
sudo iptables -A FORWARD -s 172.100.100.0/24 -d 192.168.2.0/24 -j ACCEPT
sudo iptables -A FORWARD -m state --state ESTABLISHED,RELATED -j ACCEPT

# Make iptables persistent
sudo apt-get install iptables-persistent -y
sudo iptables-save > /etc/iptables/rules.v4
```

### Switch Configuration:

**Enable eAPI on switches (172.100.100.2 and .3):**
```bash
# On each switch:
Cli -c "configure
management api http-commands
   no shutdown
   protocol http
"
```
