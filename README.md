# Kármán - Arista Device Orchestration Platform

A comprehensive in-house solution for managing Arista network devices, designed to complement CloudVision Portal (CVP) for networks where budget constraints limit full CVP deployment.

## Overview

This platform addresses the challenge of managing large-scale Arista deployments (1000+ devices) where only a subset (40 devices) have full CVP support. It provides:

- **Unified Management**: Single interface for both CVP-managed and non-CVP-managed devices
- **Configuration Management**: Template-based configlet generation using Jinja2
- **CVP Integration**: Import and use existing CVP configlets (25 production-ready configs included)
- **Change Control**: Task-based workflow with approval and rollback capabilities
- **Inventory Management**: Device inventory with tagging and filtering
- **Multi-Protocol Support**: eAPI, SSH, CVP API, and gNMI connectivity
- **Version Control**: Configuration history and change tracking
- **Validation**: Pre-deployment validation of configurations

## Architecture

```
custom-cvp/
├── core/                      # Core functionality
│   ├── inventory.py           # Device inventory management
│   ├── configlet.py           # Configlet management with versioning
│   └── task.py                # Task/change control management
├── connectors/                # Device connectivity
│   ├── eapi_connector.py      # Arista eAPI (pyeapi)
│   ├── cvp_connector.py       # CVP API integration
│   ├── netmiko_connector.py   # SSH fallback
│   └── gnmi_connector.py      # gNMI/gRPC support
├── templates/                 # Jinja2 configuration templates
│   ├── base/                  # Base system configs
│   ├── layer2/                # L2 features (VLANs, MLAG, etc.)
│   ├── layer3/                # L3 features (BGP, OSPF, etc.)
│   └── overlays/              # Overlay configs (VXLAN, EVPN)
├── variables/                 # Device and global variables
│   ├── device-vars/           # Per-device YAML files
│   └── global-vars/           # Shared variables
├── cli/                       # Command-line interface
│   └── orchestrator_cli.py    # Main CLI tool
├── builder.py                 # Configuration builder
├── validator.py               # Configuration validator
└── config/                    # Platform configuration
    ├── devices.yaml           # Device inventory
    └── settings.yaml          # Platform settings
```

## Installation

### Prerequisites

- Python 3.8 or higher
- Access to Arista devices (eAPI enabled or SSH)
- Optional: CVP access for CVP-managed devices

### Setup

1. Clone or extract the platform:
```bash
cd custom-cvp
```

2. Install dependencies:
```bash
pip install -r requirements.txt
```

3. Initialize the database:
```bash
python cli/orchestrator_cli.py inventory list
```

## Quick Start

### 1. Import Device Inventory

```bash
python cli/orchestrator_cli.py inventory import config/devices.yaml
```

### 1b. Explore Imported CVP Configlets (Optional)

The platform includes 25 production-ready configlets imported from Arista CVP:

```bash
# List all imported configlets
python cli/orchestrator_cli.py configlet list

# View a specific configlet
python cli/orchestrator_cli.py configlet show Day2Ops-Leaf1-start

# See CVP_CONFIGLETS.md for detailed documentation
```

### 2. Create a Device Variable File

Create a YAML file in `variables/device-vars/`:

```yaml
hostname: leaf1-dc1
domain_name: datacenter.local

dns_servers:
  - ip: 8.8.8.8
    vrf: management

vlans:
  - id: 10
    name: VLAN10

interfaces:
  - name: Ethernet3
    description: "Server Port"
    mode: access
    vlan: 10
```

### 3. Build Configuration

```bash
python builder.py \
  --device leaf1.yaml \
  --templates base/system.j2 layer2/vlans.j2 base/interfaces.j2 \
  --output leaf1.cfg
```

### 4. Validate Configuration

```bash
python validator.py --config output/generated-configs/leaf1.cfg
```

### 5. Deploy to Device

Using eAPI connector:
```python
from connectors.eapi_connector import EAPIConnector

conn = EAPIConnector('192.168.1.11', 'admin', 'password')
conn.connect()
conn.apply_config(['interface Ethernet3', 'description Updated'])
conn.save_config()
```

## CLI Usage

### Inventory Management

```bash
# List all devices
python cli/orchestrator_cli.py inventory list

# Add a device
python cli/orchestrator_cli.py inventory add \
  --hostname leaf3 \
  --ip 192.168.1.13 \
  --role leaf \
  --site datacenter1 \
  --mgmt-type eapi

# Import from YAML
python cli/orchestrator_cli.py inventory import config/devices.yaml

# Export to YAML
python cli/orchestrator_cli.py inventory export backup.yaml
```

### Configlet Management

```bash
# List configlets
python cli/orchestrator_cli.py configlet list

# Create configlet
python cli/orchestrator_cli.py configlet create \
  --name BASE_CONFIG \
  --file /path/to/config.txt \
  --description "Base configuration"

# Show configlet
python cli/orchestrator_cli.py configlet show BASE_CONFIG

# View history
python cli/orchestrator_cli.py configlet history BASE_CONFIG
```

### Build Configurations

```bash
# Single device
python cli/orchestrator_cli.py build \
  --device leaf1.yaml \
  --templates base/system.j2 layer2/mlag.j2

# Bulk build
python cli/orchestrator_cli.py build \
  --bulk device-list.yaml \
  --templates base/system.j2 layer2/vlans.j2
```

### Task Management

```bash
# List tasks
python cli/orchestrator_cli.py task list

# Show task details
python cli/orchestrator_cli.py task show 1

# Create task
python cli/orchestrator_cli.py task create \
  --type config_change \
  --devices "leaf1,leaf2" \
  --description "Update VLANs"
```

## Template Development

### Template Structure

Templates use Jinja2 syntax with EOS-specific formatting:

```jinja
!
! VLAN Configuration
!
{% for vlan in vlans %}
vlan {{ vlan.id }}
   name {{ vlan.name }}
!
{% endfor %}
```

### Variable Hierarchy

1. **Global Variables** (`variables/global-vars/global-vars.yaml`): Shared across all devices
2. **Device Variables** (`variables/device-vars/<device>.yaml`): Device-specific settings
3. **Template Defaults**: Fallback values in templates

### Creating New Templates

1. Create template file in appropriate directory:
```bash
touch templates/layer3/static-routes.j2
```

2. Add Jinja2 template content:
```jinja
{% if static_routes %}
{% for route in static_routes %}
ip route {{ route.destination }} {{ route.next_hop }}
{% endfor %}
{% endif %}
```

3. Use in builds:
```bash
python builder.py --device leaf1.yaml --templates layer3/static-routes.j2
```

## Device Connectivity

### eAPI (Recommended)

Enable eAPI on Arista devices:
```
management api http-commands
   protocol https
   no shutdown
   vrf management
```

Python usage:
```python
from connectors.eapi_connector import EAPIConnector

conn = EAPIConnector('192.168.1.11', 'admin', 'password')
conn.connect()
result = conn.execute_commands(['show version'])
```

### CVP Integration

For CVP-managed devices:
```python
from connectors.cvp_connector import CVPConnector

cvp = CVPConnector('cvp.example.com', 'admin', 'password')
cvp.connect()
devices = cvp.get_devices()
```

### SSH Fallback

When eAPI is unavailable:
```python
from connectors.netmiko_connector import NetmikoConnector

conn = NetmikoConnector('192.168.1.11', 'admin', 'password')
conn.connect()
output = conn.get_running_config()
```

## Configuration Validation

### Variable Validation

Define schema in `schemas/device-schema.json`:
```json
{
  "type": "object",
  "required": ["hostname"],
  "properties": {
    "hostname": {
      "type": "string",
      "pattern": "^[a-zA-Z0-9-]+$"
    }
  }
}
```

Validate:
```bash
python validator.py --vars variables/device-vars/leaf1.yaml
```

### Syntax Validation

```bash
python validator.py --config output/generated-configs/leaf1.cfg
```

## Best Practices

### 1. Configuration Sessions

Always use configuration sessions for complex changes:
```python
conn.apply_config(commands, session='CHANGE-12345')
# Review changes
# Commit or abort
```

### 2. Checkpoints

Create checkpoints before major changes:
```python
conn.create_checkpoint('pre-upgrade-backup')
```

### 3. Version Control

Store templates and variables in Git:
```bash
git add templates/ variables/
git commit -m "Add MLAG configuration template"
```

### 4. Testing

Test configurations in lab environment before production deployment.

### 5. Change Control

Use the task system for all production changes:
```python
task_id = tasks.create_task(
    TaskType.CONFIG_CHANGE,
    ['leaf1', 'leaf2'],
    "Update BGP configuration",
    config_changes
)
```

## Hybrid CVP Environment

### Managing Mixed Deployment

For 40 CVP-managed devices and 960 custom-managed devices:

1. **Inventory Tracking**: Tag devices with `cvp_managed: true/false`
2. **Unified Templates**: Same templates for both groups
3. **Selective Deployment**:
   - CVP devices: Push via CVP API
   - Custom devices: Direct eAPI/SSH

Example workflow:
```python
devices = inventory.get_devices_by_filter(cvp_managed=False)
for device in devices:
    # Deploy via eAPI
    conn = EAPIConnector(device.ip_address, user, pass)
    conn.apply_config(config_lines)

cvp_devices = inventory.get_devices_by_filter(cvp_managed=True)
for device in cvp_devices:
    # Deploy via CVP
    cvp.apply_configlet_to_device(device.hostname, configlet_name)
```

## Troubleshooting

### Common Issues

1. **Database locked**: Close other CLI instances
2. **eAPI connection fails**: Verify eAPI is enabled and credentials are correct
3. **Template errors**: Check variable names match between YAML and templates
4. **Permission denied**: Ensure user has appropriate privileges on devices

### Debug Mode

Enable verbose logging:
```python
import logging
logging.basicConfig(level=logging.DEBUG)
```

## Advanced Features

### Bulk Operations

Create device list file:
```yaml
devices:
  - variable_file: leaf1.yaml
    output_file: leaf1.cfg
  - variable_file: leaf2.yaml
    output_file: leaf2.cfg
```

Execute:
```bash
python builder.py --bulk device-list.yaml --templates base/system.j2
```

### Custom Filters

Add custom Jinja2 filters in `builder.py`:
```python
def ip_increment(ip_address, offset):
    # Custom logic
    return new_ip

env.filters['ip_increment'] = ip_increment
```

### API Integration

Extend with REST API using Flask or FastAPI (see `web/` directory for future implementation).

## Contributing

To extend the platform:

1. Add new connectors in `connectors/`
2. Create new templates in `templates/`
3. Extend core modules in `core/`
4. Add CLI commands in `cli/orchestrator_cli.py`

## Support

For issues related to:
- Arista EOS: Refer to Arista documentation
- Python dependencies: Check requirements.txt versions
- Platform bugs: Review code and logs

## License

Internal use - customize as needed for your organization.

## Roadmap

Future enhancements:
- [ ] Web-based UI
- [ ] Real-time telemetry integration
- [ ] Automated compliance checking
- [ ] Integration with network monitoring tools
- [ ] Multi-site synchronization
- [ ] Role-based access control (RBAC)
- [ ] Workflow automation engine

---

Built for network engineers managing large-scale Arista deployments with budget constraints.
