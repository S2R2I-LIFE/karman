# CVP Configlets - Imported from CloudVision Portal

This document describes the configlets that have been imported from Arista CloudVision Portal (CVP) exports.

## Overview

**Total Configlets Imported: 25**

These configlets include pre-built configurations from Arista's ATD (Arista Test Drive) labs and production-ready templates for common network scenarios.

## Configlet Categories

### 1. ACL Starter Configurations (10 configlets)

Basic interface and IP configurations for spine-leaf topology:

- `ACL-Start-Leaf1` through `ACL-Start-Leaf4` - Leaf switch base configs
- `ACL-Start-Spine1` through `ACL-Start-Spine4` - Spine switch base configs
- `ACL-Start-BorderLeaf1`, `ACL-Start-BorderLeaf2` - Border leaf configs

**Use Case:** Initial setup of leaf and spine switches with basic IP addressing and loopback interfaces.

**Example (viewing a configlet):**
```bash
python cli/orchestrator_cli.py configlet show ACL-Start-Leaf1
```

### 2. Infrastructure Configuration (1 configlet)

- `ATD-INFRA` - Arista Test Drive infrastructure configuration
  - VRF MGMT
  - TerminAttr daemon (CVP streaming)
  - CLI aliases
  - AAA configuration
  - RADIUS integration
  - Management API setup

**Use Case:** Standard infrastructure setup for lab or production environments with CVP integration.

### 3. Border Leaf Configurations (4 configlets)

Two different approaches for border leaf switches:

**Multicast Routing:**
- `BorderLeaf1-Multicast-Start`
- `BorderLeaf2-Multicast-Start`

**OSPF Multi-Area:**
- `BorderLeaf1-OSPFMultiArea-Start`
- `BorderLeaf2-OSPFMultiArea-Start`

**Use Case:** Edge connectivity with either multicast BGP or OSPF multi-area designs.

### 4. Day 2 Operations - Production Ready (9 configlets)

Complete EVPN/VXLAN configurations for production deployments:

**Leaf Switches:**
- `Day2Ops-Leaf1-start` through `Day2Ops-Leaf4-start`
  - MLAG configuration
  - VXLAN/EVPN setup
  - BGP underlay and overlay
  - VRFs and VNIs
  - Complete fabric configuration

**Spine Switches:**
- `Day2Ops-Spine1-start` through `Day2Ops-Spine4-start`
  - BGP route reflector configuration
  - EVPN address family
  - Underlay routing

**Host Configuration:**
- `Day2Ops-host1-start` - Server/host configuration with MLAG

**Use Case:** Production-ready EVPN/VXLAN fabric configurations with MLAG for high availability.

### 5. Configlet Builder (1 configlet)

- `Base-Builder` - Python-based ConfigletBuilder
  - Dynamically generates hostname and management IP based on device serial number
  - Includes DNS, routing, and API configuration
  - Supports 11 different device types

**Use Case:** Automated ZTP (Zero Touch Provisioning) configuration based on device identity.

## Using CVP Configlets

### Viewing Configlets

```bash
# List all configlets
python cli/orchestrator_cli.py configlet list

# View specific configlet
python cli/orchestrator_cli.py configlet show Day2Ops-Leaf1-start

# View configlet history
python cli/orchestrator_cli.py configlet history ATD-INFRA
```

### Applying Configlets to Devices

#### Method 1: Direct Copy to Device Variables

Extract the configlet and use as reference for your Jinja2 templates:

```bash
# Export configlet to file
python cli/orchestrator_cli.py configlet show ACL-Start-Leaf1 > /tmp/leaf1-base.cfg
```

#### Method 2: Use as Static Configlet

Apply directly to a device using eAPI:

```python
from connectors.eapi_connector import EAPIConnector
from core.configlet import ConfigletManager

# Get configlet
configlet_mgr = ConfigletManager()
configlet = configlet_mgr.get_configlet('Day2Ops-Leaf1-start')

# Connect to device
conn = EAPIConnector('192.168.1.11', 'admin', 'password')
conn.connect()

# Apply configuration
config_lines = [line.strip() for line in configlet.config.split('\n')
                if line.strip() and not line.startswith('!')]
conn.apply_config(config_lines)
conn.save_config()
```

#### Method 3: Convert to Jinja2 Template

Extract common patterns and create reusable templates:

1. Identify variable sections
2. Create corresponding Jinja2 template
3. Create device variable file
4. Build configuration

### Importing Additional CVP Exports

If you have more CVP configlet exports:

```bash
# List what's in the export
python import_cvp_configlets.py --list /path/to/CVP/ExportedConfigletsData/

# Import all configlets
python import_cvp_configlets.py --import /path/to/CVP/ExportedConfigletsData/

# Import only specific configlets
python import_cvp_configlets.py --import /path/to/CVP/ExportedConfigletsData/ --filter "EVPN"

# Overwrite existing configlets
python import_cvp_configlets.py --import /path/to/CVP/ExportedConfigletsData/ --overwrite
```

## Example Workflows

### Workflow 1: Lab Setup

Use the ACL-Start configlets for initial lab setup:

```bash
# View the configuration
python cli/orchestrator_cli.py configlet show ACL-Start-Leaf1

# Apply to lab device
# (Use eAPI connector as shown above)
```

### Workflow 2: Production Fabric Deployment

Use Day2Ops configlets as reference for production:

```bash
# Review the Day2Ops configurations
for i in 1 2 3 4; do
    python cli/orchestrator_cli.py configlet show "Day2Ops-Leaf${i}-start" > leaf${i}-reference.cfg
done

# Use these as reference to build your Jinja2 templates
# with appropriate variables for your environment
```

### Workflow 3: Using ConfigletBuilder (Base-Builder)

The Base-Builder is a Python script that can be adapted:

```bash
# View the builder script
python cli/orchestrator_cli.py configlet show Base-Builder

# Adapt the Python logic for your environment
# This script maps device serial numbers to hostnames and IPs
```

## Configlet Details

### Day2Ops Leaf Configuration Features

The Day2Ops leaf configlets include:

- **VLANs:** 100 (Host_Network_100), 200 (Host_Network_200), 4094 (MLAG_PEER)
- **VRF:** TENANT vrf instance
- **MLAG:** Full MLAG configuration with reload delays
- **VXLAN:** VNI mappings (10100, 10200, 5000)
- **BGP:**
  - ASN 65001 (Leaf1/2) or 65002 (Leaf3/4)
  - EVPN overlay peering
  - IPv4 underlay peering
  - MLAG peer iBGP
- **Interfaces:**
  - Ethernet1-2: MLAG peer link
  - Ethernet3-6: Spine uplinks (P2P /31)
  - Ethernet7: Server port-channel
  - Loopback0: EVPN overlay peering
  - Loopback1: VTEP source

### Day2Ops Spine Configuration Features

The Day2Ops spine configlets include:

- **Routing:** BGP ASN 65000 (all spines)
- **EVPN:** Route reflector for overlay
- **Interfaces:**
  - Ethernet3-6: Leaf downlinks (P2P /31)
  - Loopback0: EVPN overlay peering
- **BGP:**
  - IPv4 underlay peers to all leafs
  - EVPN overlay peers to all leafs
  - Next-hop-unchanged for route reflection

### ATD-INFRA Configuration Features

Infrastructure setup for lab/production:

- **VRF MGMT:** Management VRF isolation
- **TerminAttr:** CVP streaming agent
- **AAA:** RADIUS integration with local fallback
- **Aliases:** Helpful CLI shortcuts
- **Management API:** HTTP commands enabled
- **DNS:** Domain configuration
- **NTP:** Time synchronization
- **Users:** Admin and automation accounts

## Network Topology Reference

These configlets were designed for a specific topology:

```
                    ┌─────────┐  ┌─────────┐  ┌─────────┐  ┌─────────┐
                    │ Spine1  │  │ Spine2  │  │ Spine3  │  │ Spine4  │
                    │ 65000   │  │ 65000   │  │ 65000   │  │ 65000   │
                    └────┬────┘  └────┬────┘  └────┬────┘  └────┬────┘
                         │            │            │            │
            ┌────────────┼────────────┼────────────┼────────────┼────────────┐
            │            │            │            │            │            │
       ┌────▼────┐  ┌────▼────┐  ┌────▼────┐  ┌────▼────┐  ┌────▼────┐  ┌────▼────┐
       │ Leaf1   │  │ Leaf2   │  │ Leaf3   │  │ Leaf4   │  │BorderL1 │  │BorderL2 │
       │ 65001   │  │ 65001   │  │ 65002   │  │ 65002   │  │ 65500   │  │ 65500   │
       └────┬────┘  └────┬────┘  └────┬────┘  └────┬────┘  └─────────┘  └─────────┘
            └─MLAG──────┘            └──MLAG────┘
                 │                        │
              Servers                  Servers
```

**IP Addressing:**
- Loopback0 (EVPN): 172.16.0.x/32
- Loopback1 (VTEP): 172.16.1.x/32
- P2P Links: 172.16.200.x/31
- Host Networks: 10.111.x.0/24

## Tips for Using These Configlets

1. **Use as Reference:** These configlets are excellent learning resources for Arista best practices
2. **Extract Patterns:** Identify common patterns and convert to Jinja2 templates
3. **Customize:** Adapt IP addressing, ASNs, and VNI ranges for your environment
4. **Version Control:** Store these as reference configurations in Git
5. **Test First:** Always test configurations in lab before production deployment

## Additional Resources

- View all configlets: `python cli/orchestrator_cli.py configlet list`
- Import more CVP exports: `python import_cvp_configlets.py --help`
- Official Arista Documentation: https://www.arista.com/en/support/product-documentation

---

These CVP configlets provide production-ready examples of Arista EOS configurations for modern data center fabrics with EVPN/VXLAN.
