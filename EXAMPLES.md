# Configuration Examples

This document provides practical examples for common Arista configurations.

## Table of Contents

1. [Basic VLAN Configuration](#basic-vlan-configuration)
2. [MLAG Setup](#mlag-setup)
3. [BGP Underlay](#bgp-underlay)
4. [VXLAN/EVPN Overlay](#vxlan-evpn-overlay)
5. [Static Routes](#static-routes)
6. [Interface Configuration](#interface-configuration)

---

## Basic VLAN Configuration

### Device Variables (leaf1.yaml)

```yaml
hostname: leaf1-dc1
vlans:
  - id: 10
    name: Web-Servers
    state: active
  - id: 20
    name: App-Servers
    state: active
  - id: 30
    name: DB-Servers
    state: active
```

### Build Command

```bash
python builder.py \
  --device leaf1.yaml \
  --templates base/system.j2 layer2/vlans.j2
```

### Generated Output

```
vlan 10
   name Web-Servers
   state active
!
vlan 20
   name App-Servers
   state active
!
vlan 30
   name DB-Servers
   state active
!
```

---

## MLAG Setup

### Device Variables (leaf1.yaml)

```yaml
hostname: leaf1-dc1

mlag:
  enabled: true
  domain_id: MLAG_LEAF1_LEAF2
  peer_vlan: 4094
  peer_link_po: 2000
  peer_link_interfaces:
    - Ethernet1
    - Ethernet2
  local_ip: 10.255.252.0
  peer_ip: 10.255.252.1
  peer_subnet_mask: 31
  reload_delay:
    mlag: 300
    non_mlag: 330
```

### Build Command

```bash
python builder.py \
  --device leaf1.yaml \
  --templates layer2/mlag.j2
```

### Generated Output

```
vlan 4094
   name MLAG-PEER
   trunk group MLAG-PEER
!
interface Port-Channel2000
   description MLAG Peer Link
   switchport mode trunk
   switchport trunk group MLAG-PEER
!
interface Ethernet1
   description MLAG Peer Link Member
   channel-group 2000 mode active
!
interface Ethernet2
   description MLAG Peer Link Member
   channel-group 2000 mode active
!
interface Vlan4094
   description MLAG Peer L3 Interface
   ip address 10.255.252.0/31
!
mlag configuration
   domain-id MLAG_LEAF1_LEAF2
   local-interface Vlan4094
   peer-address 10.255.252.1
   peer-link Port-Channel2000
   reload-delay mlag 300
   reload-delay non-mlag 330
!
```

---

## BGP Underlay

### Device Variables (spine1.yaml)

```yaml
hostname: spine1-dc1

bgp:
  asn: 65100
  router_id: 10.0.100.1
  max_paths: 4
  ecmp_paths: 4
  neighbors:
    - ip: 10.1.1.1
      remote_asn: 65001
      description: "leaf1"
    - ip: 10.1.1.3
      remote_asn: 65002
      description: "leaf2"
  networks:
    - 10.0.100.1/32
```

### Build Command

```bash
python builder.py \
  --device spine1.yaml \
  --templates layer3/bgp.j2
```

### Generated Output

```
router bgp 65100
   router-id 10.0.100.1
   maximum-paths 4 ecmp 4
   !
   neighbor 10.1.1.1 remote-as 65001
   neighbor 10.1.1.1 description leaf1
   neighbor 10.1.1.3 remote-as 65002
   neighbor 10.1.1.3 description leaf2
   !
   address-family ipv4
      network 10.0.100.1/32
!
```

---

## VXLAN/EVPN Overlay

### Device Variables (leaf1.yaml)

```yaml
hostname: leaf1-dc1

vxlan:
  source_interface: Loopback1
  udp_port: 4789
  vlan_to_vni_maps:
    - vlan: 10
      vni: 10010
    - vlan: 20
      vni: 10020
    - vlan: 30
      vni: 10030
  vrf_to_vni_maps:
    - vrf: PROD
      vni: 50001

bgp:
  asn: 65001
  router_id: 10.0.1.1
  evpn_enabled: true
  neighbors:
    - ip: 10.0.100.1
      remote_asn: 65100
      description: "spine1-evpn"
      peer_group: EVPN-OVERLAY-PEERS
```

### Build Command

```bash
python builder.py \
  --device leaf1.yaml \
  --templates overlays/vxlan.j2 layer3/bgp.j2
```

### Generated Output

```
interface Vxlan1
   vxlan source-interface Loopback1
   vxlan udp-port 4789
   vxlan vlan 10 vni 10010
   vxlan vlan 20 vni 10020
   vxlan vlan 30 vni 10030
   vxlan vrf PROD vni 50001
!
router bgp 65001
   router-id 10.0.1.1
   maximum-paths 4 ecmp 4
   !
   neighbor 10.0.100.1 remote-as 65100
   neighbor 10.0.100.1 description spine1-evpn
   neighbor 10.0.100.1 peer group EVPN-OVERLAY-PEERS
   !
   address-family evpn
      neighbor EVPN-OVERLAY-PEERS activate
!
```

---

## Static Routes

### Device Variables (border1.yaml)

```yaml
hostname: border1-dc1

static_routes:
  - destination: 0.0.0.0/0
    next_hop: 192.168.1.1
    distance: 1
    name: Default-Route
  - destination: 10.0.0.0/8
    next_hop: 10.1.1.1
    vrf: MGMT
```

### Build Command

```bash
python builder.py \
  --device border1.yaml \
  --templates layer3/static-routes.j2
```

### Generated Output

```
ip route 0.0.0.0/0 192.168.1.1 1 name Default-Route
ip route vrf MGMT 10.0.0.0/8 10.1.1.1
!
```

---

## Interface Configuration

### Device Variables (leaf1.yaml)

```yaml
hostname: leaf1-dc1

interfaces:
  # Access port
  - name: Ethernet3
    description: "Server - web01"
    mode: access
    vlan: 10
    spanning_tree_portfast: true
    enabled: true

  # Trunk port
  - name: Ethernet4
    description: "Uplink to Aggregation"
    mode: trunk
    allowed_vlans: "10,20,30"
    native_vlan: 1
    enabled: true

  # Routed port
  - name: Ethernet10
    description: "P2P to Spine1"
    mode: routed
    ip_address: 10.1.1.1/31
    enabled: true

  # Disabled port
  - name: Ethernet48
    description: "Unused"
    enabled: false
```

### Build Command

```bash
python builder.py \
  --device leaf1.yaml \
  --templates base/interfaces.j2
```

### Generated Output

```
interface Ethernet3
   description Server - web01
   switchport mode access
   switchport access vlan 10
   spanning-tree portfast
   no shutdown
!
interface Ethernet4
   description Uplink to Aggregation
   switchport mode trunk
   switchport trunk allowed vlan 10,20,30
   switchport trunk native vlan 1
   no shutdown
!
interface Ethernet10
   description P2P to Spine1
   no switchport
   ip address 10.1.1.1/31
   no shutdown
!
interface Ethernet48
   description Unused
   shutdown
!
```

---

## Complete Leaf Switch Configuration

### Device Variables (leaf1.yaml)

```yaml
hostname: leaf1-dc1
domain_name: datacenter.local

dns_servers:
  - ip: 8.8.8.8
    vrf: management

ntp_servers:
  - ip: 10.0.0.1
    vrf: management
    prefer: true

local_users:
  - name: admin
    privilege: 15
    role: network-admin
    password_hash: $6$encrypted...

vlans:
  - id: 10
    name: Web-Tier
  - id: 20
    name: App-Tier

mlag:
  enabled: true
  domain_id: MLAG_LEAF1_LEAF2
  peer_vlan: 4094
  peer_link_po: 2000
  peer_link_interfaces: [Ethernet1, Ethernet2]
  local_ip: 10.255.252.0
  peer_ip: 10.255.252.1
  peer_subnet_mask: 31

bgp:
  asn: 65001
  router_id: 10.0.1.1
  neighbors:
    - ip: 10.1.1.0
      remote_asn: 65100
      description: spine1

interfaces:
  - name: Ethernet10
    description: "To Spine1"
    mode: routed
    ip_address: 10.1.1.1/31
    enabled: true
```

### Build Command

```bash
python builder.py \
  --device leaf1.yaml \
  --templates base/system.j2 layer2/vlans.j2 layer2/mlag.j2 layer3/bgp.j2 base/interfaces.j2 \
  --output leaf1-full.cfg
```

This generates a complete, production-ready configuration file.

---

## Bulk Configuration Generation

### Device List (device-list.yaml)

```yaml
devices:
  - variable_file: leaf1.yaml
    output_file: leaf1.cfg
  - variable_file: leaf2.yaml
    output_file: leaf2.cfg
  - variable_file: spine1.yaml
    output_file: spine1.cfg
  - variable_file: spine2.yaml
    output_file: spine2.cfg
```

### Build Command

```bash
python builder.py \
  --bulk device-list.yaml \
  --templates base/system.j2 layer2/vlans.j2 layer3/bgp.j2
```

This generates configurations for all devices in one command.

---

## Tips and Tricks

### 1. Using Global Variables

Define common settings once in `variables/global-vars/global-vars.yaml`:

```yaml
common_dns_servers:
  - ip: 8.8.8.8
    vrf: management
  - ip: 8.8.4.4
    vrf: management
```

Reference in device vars:
```yaml
dns_servers: "{{ common_dns_servers }}"
```

### 2. Conditional Configuration

Use Jinja2 conditionals in templates:

```jinja
{% if mlag.enabled %}
mlag configuration
   domain-id {{ mlag.domain_id }}
{% endif %}
```

### 3. Loops and Filters

```jinja
{% for interface in interfaces | selectattr('enabled', 'equalto', true) %}
interface {{ interface.name }}
   no shutdown
{% endfor %}
```

---

These examples should cover most common scenarios. For more complex configurations, combine multiple templates and leverage Jinja2's powerful templating features.
