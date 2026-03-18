# Configlet Builder Issues and Fixes

**Date:** 2026-01-21
**Status:** IDENTIFIED

---

## Issues Found

### 1. Missing Configuration Sections (Empty Output)

The following templates render empty because required variables are not defined in `leaf1.yaml`:

#### A. Static Routes Template
- **Template:** `templates/layer3/static-routes.j2`
- **Issue:** No `static_routes` variable in leaf1.yaml
- **Impact:** Empty "Static Routes" section

#### B. OSPF Template
- **Template:** `templates/layer3/ospf.j2`
- **Issue:** No `ospf` variable in leaf1.yaml
- **Impact:** Empty "OSPF Configuration" section

#### C. EVPN Template
- **Template:** `templates/overlays/evpn.j2`
- **Issue:** No `evpn` variable in leaf1.yaml
- **Impact:** Empty "EVPN Configuration" section

---

### 2. BGP Peer Group Not Defined

**Issue:** BGP configuration references peer group "SPINE-PEERS" but never defines it.

**Current Output:**
```
neighbor 10.1.1.0 peer group SPINE-PEERS
neighbor 10.1.2.0 peer group SPINE-PEERS
```

**Problem:** Peer group must be defined before being assigned to neighbors.

**Expected:**
```
neighbor SPINE-PEERS peer group
neighbor SPINE-PEERS send-community
neighbor SPINE-PEERS maximum-routes 12000
!
neighbor 10.1.1.0 remote-as 65100
neighbor 10.1.1.0 peer group SPINE-PEERS
```

**Root Cause:** BGP template (layer3/bgp.j2) doesn't include peer group definitions.

---

### 3. Missing Loopback Interfaces

**Issue:** VXLAN configuration references `Loopback1` but no loopback interfaces are configured.

**Current Output:**
```
interface Vxlan1
   vxlan source-interface Loopback1  ← Loopback1 doesn't exist!
```

**Problem:**
- No Loopback0 interface (typically used for router-id: 10.0.1.1)
- No Loopback1 interface (referenced by VXLAN)

**Expected:**
```
interface Loopback0
   description Router ID
   ip address 10.0.1.1/32
!
interface Loopback1
   description VTEP Source
   ip address 10.0.1.1/32
```

**Root Cause:**
- `interfaces` variable in leaf1.yaml doesn't include loopback interfaces
- Interfaces template only loops through `interfaces` list

---

## Solutions

### Solution 1: Add Missing Variables to leaf1.yaml

Add the following sections to make all templates render properly:

```yaml
# Loopback Interfaces
loopback_interfaces:
  - name: Loopback0
    description: "Router ID"
    ip_address: 10.0.1.1/32
  - name: Loopback1
    description: "VTEP Source"
    ip_address: 10.0.1.1/32

# Static Routes (if needed)
static_routes:
  - destination: 0.0.0.0/0
    next_hop: 10.0.0.1
    vrf: management
    name: "Default Route Management"

# OSPF Configuration (if using OSPF instead of BGP)
# ospf:
#   process_id: 1
#   router_id: 10.0.1.1
#   max_paths: 4
#   networks:
#     - prefix: 10.1.1.0/31
#       area: 0.0.0.0
#     - prefix: 10.1.2.0/31
#       area: 0.0.0.0
#   passive_interfaces:
#     - Loopback0
#     - Loopback1

# EVPN Configuration
evpn:
  asn: 65001
  peers:
    - ip: 10.0.100.1
      remote_asn: 65100
      update_source: Loopback0
      multihop: 3
    - ip: 10.0.100.2
      remote_asn: 65100
      update_source: Loopback0
      multihop: 3
```

---

### Solution 2: Fix BGP Template to Define Peer Groups

Update `templates/layer3/bgp.j2` to define peer groups before using them:

```jinja
!
! BGP Configuration
!
router bgp {{ bgp.asn }}
   router-id {{ bgp.router_id }}
   maximum-paths {{ bgp.max_paths | default(4) }} ecmp {{ bgp.ecmp_paths | default(4) }}
   {% if bgp.distance %}
   distance bgp {{ bgp.distance.external }} {{ bgp.distance.internal }} {{ bgp.distance.local }}
   {% endif %}
   !
   {% if bgp.peer_groups %}
   {% for pg in bgp.peer_groups %}
   neighbor {{ pg.name }} peer group
   {% if pg.remote_asn %}
   neighbor {{ pg.name }} remote-as {{ pg.remote_asn }}
   {% endif %}
   {% if pg.send_community %}
   neighbor {{ pg.name }} send-community
   {% endif %}
   {% if pg.maximum_routes %}
   neighbor {{ pg.name }} maximum-routes {{ pg.maximum_routes }}
   {% endif %}
   {% endfor %}
   !
   {% endif %}
   {% for neighbor in bgp.neighbors %}
   neighbor {{ neighbor.ip }} remote-as {{ neighbor.remote_asn }}
   neighbor {{ neighbor.ip }} description {{ neighbor.description }}
   {% if neighbor.peer_group %}
   neighbor {{ neighbor.ip }} peer group {{ neighbor.peer_group }}
   {% endif %}
   ...
```

And update leaf1.yaml:

```yaml
bgp:
  asn: 65001
  router_id: 10.0.1.1
  max_paths: 4
  ecmp_paths: 4
  peer_groups:
    - name: SPINE-PEERS
      send_community: true
      maximum_routes: 12000
  neighbors:
    - ip: 10.1.1.0
      remote_asn: 65100
      description: "spine1"
      peer_group: SPINE-PEERS
    ...
```

---

### Solution 3: Update Interfaces Template to Include Loopbacks

Modify `templates/base/interfaces.j2` to also render loopback interfaces:

```jinja
!
! Interface Configuration
!
{% if loopback_interfaces %}
{% for interface in loopback_interfaces %}
interface {{ interface.name }}
   {% if interface.description %}
   description {{ interface.description }}
   {% endif %}
   {% if interface.ip_address %}
   ip address {{ interface.ip_address }}
   {% endif %}
!
{% endfor %}
{% endif %}
{% for interface in interfaces %}
interface {{ interface.name }}
   ...
{% endfor %}
```

---

## Priority Fixes

### HIGH PRIORITY (Breaks Functionality)

1. **Missing Loopback Interfaces** - VXLAN will not work without Loopback1
2. **BGP Peer Groups** - Configuration may be rejected by EOS

### MEDIUM PRIORITY (Optional Features)

3. **Static Routes** - Only needed if static routing is required
4. **OSPF** - Only needed if using OSPF instead of BGP
5. **EVPN** - Only needed for overlay networking

---

## Recommended Action Plan

### Immediate Fixes (Required)

1. Add loopback_interfaces to leaf1.yaml:
   ```yaml
   loopback_interfaces:
     - name: Loopback0
       description: "Router ID"
       ip_address: 10.0.1.1/32
     - name: Loopback1
       description: "VTEP Source"
       ip_address: 10.0.1.1/32
   ```

2. Update interfaces.j2 template to render loopbacks

3. Add BGP peer group definition to leaf1.yaml:
   ```yaml
   bgp:
     peer_groups:
       - name: SPINE-PEERS
         send_community: true
         maximum_routes: 12000
   ```

4. Update bgp.j2 template to define peer groups

### Optional Additions (Based on Design)

5. Add EVPN configuration if using VXLAN with EVPN control plane
6. Add static routes if needed for management or default routing
7. Add OSPF configuration if using OSPF instead of BGP underlay

---

## Testing After Fixes

After implementing fixes, verify:

```bash
# Rebuild configuration
cd /home/b/cvp/custom-cvp
python3 builder.py --device leaf1.yaml --templates base/system.j2 base/interfaces.j2 layer2/vlans.j2 layer2/mlag.j2 layer2/spanning-tree.j2 layer3/static-routes.j2 layer3/bgp.j2 layer3/ospf.j2 overlays/evpn.j2 overlays/vxlan.j2

# Check output for:
- ✓ Loopback0 and Loopback1 interfaces present
- ✓ BGP peer group SPINE-PEERS defined before use
- ✓ EVPN configuration present (if evpn variable added)
- ✓ Static routes present (if static_routes variable added)
```

---

## Files to Modify

1. **variables/device-vars/leaf1.yaml** - Add missing variables
2. **templates/base/interfaces.j2** - Add loopback interface support
3. **templates/layer3/bgp.j2** - Add peer group definition support

---

## Status: DOCUMENTED

- ✅ Issues identified
- ✅ Root causes documented
- ✅ Solutions provided
- ⏳ Fixes need to be implemented
