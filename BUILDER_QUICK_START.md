# Configlet Builder - Quick Start Guide

---

## Build a Complete Configuration (Recommended)

```bash
cd /home/b/cvp/custom-cvp

python3 builder.py \
  --device leaf1.yaml \
  --templates \
    base/system.j2 \
    base/interfaces.j2 \
    layer2/vlans.j2 \
    layer2/mlag.j2 \
    layer2/spanning-tree.j2 \
    layer3/static-routes.j2 \
    layer3/bgp-complete.j2 \
    overlays/vxlan.j2 \
  --output leaf1-dc1.cfg
```

**Output:** `output/generated-configs/leaf1-dc1.cfg`

---

## Build Multiple Devices

```bash
# Create variable files for each device
cp variables/device-vars/leaf1.yaml variables/device-vars/leaf2.yaml
cp variables/device-vars/leaf1.yaml variables/device-vars/spine1.yaml

# Edit each file with device-specific values
nano variables/device-vars/leaf2.yaml
nano variables/device-vars/spine1.yaml

# Build all configurations
python3 builder.py --device leaf1.yaml --templates [templates] --output leaf1.cfg
python3 builder.py --device leaf2.yaml --templates [templates] --output leaf2.cfg
python3 builder.py --device spine1.yaml --templates [templates] --output spine1.cfg
```

---

## Template Selection Guide

### For Leaf Switches (EVPN-VXLAN)
Use all templates:
- `base/system.j2`
- `base/interfaces.j2`
- `layer2/vlans.j2`
- `layer2/mlag.j2`
- `layer2/spanning-tree.j2`
- `layer3/static-routes.j2`
- `layer3/bgp-complete.j2`
- `overlays/vxlan.j2`

### For Spine Switches (BGP Underlay + EVPN Route Reflector)
Skip MLAG and VXLAN:
- `base/system.j2`
- `base/interfaces.j2`
- `layer3/static-routes.j2`
- `layer3/bgp-complete.j2`

### For Access Switches (Layer 2 Only)
Skip Layer 3:
- `base/system.j2`
- `base/interfaces.j2`
- `layer2/vlans.j2`
- `layer2/mlag.j2`
- `layer2/spanning-tree.j2`

---

## Required Variables for Each Template

### base/system.j2
```yaml
hostname: leaf1-dc1
domain_name: datacenter.local
dns_servers: [...]
ntp_servers: [...]
logging_servers: [...]
local_users: [...]
```

### base/interfaces.j2
```yaml
loopback_interfaces: [...]  # NEW - Required for VXLAN!
interfaces: [...]
```

### layer2/vlans.j2
```yaml
vlans: [...]
```

### layer2/mlag.j2
```yaml
mlag:
  enabled: true
  domain_id: MLAG_DOMAIN
  peer_vlan: 4094
  peer_link_po: 2000
  peer_link_interfaces: [...]
  local_ip: 10.255.252.0
  peer_ip: 10.255.252.1
```

### layer3/static-routes.j2
```yaml
static_routes: [...]  # Optional
```

### layer3/bgp-complete.j2
```yaml
bgp:
  asn: 65001
  router_id: 10.0.1.1
  peer_groups: [...]  # NEW - Required!
  neighbors: [...]
  networks: [...]
evpn:  # Optional - for EVPN overlay
  asn: 65001
  peers: [...]
```

### overlays/vxlan.j2
```yaml
vxlan:
  source_interface: Loopback1
  udp_port: 4789
  vlan_to_vni_maps: [...]
```

---

## Common Issues & Solutions

### Issue: "Loopback1 does not exist"
**Solution:** Add loopback_interfaces to your YAML:
```yaml
loopback_interfaces:
  - name: Loopback0
    description: "Router ID"
    ip_address: 10.0.1.1/32
  - name: Loopback1
    description: "VTEP Source"
    ip address: 10.0.1.1/32
```

### Issue: "BGP peer group not defined"
**Solution:** Add peer_groups to bgp section:
```yaml
bgp:
  peer_groups:
    - name: SPINE-PEERS
      send_community: true
      maximum_routes: 12000
```

### Issue: "Duplicate router bgp sections"
**Solution:** Use `bgp-complete.j2` instead of both `bgp.j2` and `evpn.j2`

---

## File Locations

**Templates:** `/home/b/cvp/custom-cvp/templates/`
**Variables:** `/home/b/cvp/custom-cvp/variables/device-vars/`
**Output:** `/home/b/cvp/custom-cvp/output/generated-configs/`

---

## Validation

After building, validate your configuration:

```bash
# Check syntax (basic)
grep -c "^!" output/generated-configs/leaf1-dc1.cfg

# Look for duplicates
grep "^router bgp" output/generated-configs/leaf1-dc1.cfg

# Verify loopbacks exist
grep "^interface Loopback" output/generated-configs/leaf1-dc1.cfg

# Check VXLAN source
grep "vxlan source-interface" output/generated-configs/leaf1-dc1.cfg
```

Expected:
- Only ONE "router bgp" line
- TWO loopback interfaces (Loopback0 and Loopback1)
- VXLAN source references existing Loopback1

---

## Deploy to Switch

```bash
# Copy to switch
scp output/generated-configs/leaf1-dc1.cfg admin@leaf1-dc1:/mnt/flash/

# On switch
leaf1-dc1# configure replace flash:leaf1-dc1.cfg

# Or apply incrementally
leaf1-dc1# copy flash:leaf1-dc1.cfg running-config
```

---

## Need Help?

See detailed documentation:
- `CONFIGLET_BUILDER_COMPLETE.md` - Full setup and fixes
- `CONFIGLET_BUILDER_ISSUES.md` - Common problems and solutions
- `CONFIGLET_BUILDER_FIXES_APPLIED.md` - What was fixed
