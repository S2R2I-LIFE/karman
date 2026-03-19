#!/usr/bin/env python3
"""Device telemetry collection"""

import re
from typing import Dict, List

class DeviceTelemetry:
    """Collect and parse device telemetry"""

    @staticmethod
    def parse_version(output: str) -> Dict:
        """Parse show version output"""
        data = {}

        # Software version
        match = re.search(r'Software.*version:\s*([^\s]+)', output)
        if match:
            data['version'] = match.group(1)

        # Model
        match = re.search(r'Model:\s*([^\s]+)', output)
        if match:
            data['model'] = match.group(1)

        # Uptime
        match = re.search(r'Uptime:\s*(.+?)(?:\n|$)', output)
        if match:
            data['uptime'] = match.group(1).strip()

        # Serial
        match = re.search(r'Serial Number:\s*([^\s]+)', output)
        if match:
            data['serial'] = match.group(1)

        return data

    @staticmethod
    def parse_interfaces_status(output: str) -> Dict:
        """Parse interface status"""
        data = {'total': 0, 'up': 0, 'down': 0, 'admin_down': 0}

        for line in output.split('\n'):
            if 'connected' in line.lower():
                data['up'] += 1
                data['total'] += 1
            elif 'notconnect' in line.lower():
                data['down'] += 1
                data['total'] += 1
            elif 'disabled' in line.lower():
                data['admin_down'] += 1
                data['total'] += 1

        return data

    @staticmethod
    def parse_cpu_memory(output: str) -> Dict:
        """Parse CPU and memory from show processes top"""
        data = {}

        # CPU
        match = re.search(r'CPU.*?(\d+\.?\d*)%', output)
        if match:
            data['cpu_percent'] = float(match.group(1))

        # Memory
        match = re.search(r'Mem.*?(\d+)k total.*?(\d+)k used', output)
        if match:
            total = int(match.group(1))
            used = int(match.group(2))
            data['memory_percent'] = round((used / total) * 100, 1) if total > 0 else 0

        return data

    @staticmethod
    def parse_temperature(output: str) -> Dict:
        """Parse temperature sensors"""
        sensors = []

        # Parse temperature output lines
        for line in output.split('\n'):
            # Look for lines with temperature readings
            # Format: "Cpu temp sensor    68.0    75.0    95.0     ok"
            match = re.search(r'(.+?)\s+(\d+\.?\d*)\s+(\d+\.?\d*)\s+(\d+\.?\d*)\s+(ok|not ok|.*)', line, re.IGNORECASE)
            if match:
                name = match.group(1).strip()
                current = float(match.group(2))
                warning = float(match.group(3))
                critical = float(match.group(4))
                status = match.group(5).strip().lower()

                # Determine status
                if 'ok' in status or current < warning:
                    sensor_status = 'ok'
                elif current >= critical:
                    sensor_status = 'critical'
                elif current >= warning:
                    sensor_status = 'warning'
                else:
                    sensor_status = 'ok'

                sensors.append({
                    'name': name,
                    'temperature': current,
                    'warning_threshold': warning,
                    'critical_threshold': critical,
                    'status': sensor_status
                })

        return {'sensors': sensors, 'count': len(sensors)}

    @staticmethod
    def parse_interface_counters(output: str) -> Dict:
        """Parse interface counters for errors and traffic stats"""
        interfaces = {}

        for line in output.split('\n'):
            # Skip header lines
            if 'Interface' in line or 'Port' in line or '---' in line or not line.strip():
                continue

            # Parse interface counter lines
            parts = line.split()
            if len(parts) >= 5:
                interface = parts[0]
                if interface.startswith('Et') or interface.startswith('Ma'):
                    try:
                        interfaces[interface] = {
                            'in_octets': int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else 0,
                            'in_pkts': int(parts[2]) if len(parts) > 2 and parts[2].isdigit() else 0,
                            'in_errors': int(parts[3]) if len(parts) > 3 and parts[3].isdigit() else 0,
                            'out_octets': int(parts[4]) if len(parts) > 4 and parts[4].isdigit() else 0,
                            'out_pkts': int(parts[5]) if len(parts) > 5 and parts[5].isdigit() else 0,
                            'out_errors': int(parts[6]) if len(parts) > 6 and parts[6].isdigit() else 0
                        }
                    except (ValueError, IndexError):
                        continue

        return interfaces

    @staticmethod
    def parse_interface_rates(output: str) -> Dict:
        """Parse interface bandwidth rates"""
        interfaces = {}

        for line in output.split('\n'):
            # Skip headers
            if 'Interface' in line or 'Port' in line or '---' in line or not line.strip():
                continue

            # Parse rate lines
            parts = line.split()
            if len(parts) >= 3:
                interface = parts[0]
                if interface.startswith('Et') or interface.startswith('Ma'):
                    try:
                        # Handle k, M, G suffixes for rates
                        def parse_rate(rate_str):
                            rate_str = rate_str.strip()
                            multiplier = 1
                            if rate_str.endswith('G'):
                                multiplier = 1000000000
                                rate_str = rate_str[:-1]
                            elif rate_str.endswith('M'):
                                multiplier = 1000000
                                rate_str = rate_str[:-1]
                            elif rate_str.endswith('k'):
                                multiplier = 1000
                                rate_str = rate_str[:-1]
                            return float(rate_str.replace(',', '')) * multiplier if rate_str.replace('.', '').replace(',', '').isdigit() or rate_str.replace(',', '').replace('.', '', 1).isdigit() else 0

                        interfaces[interface] = {
                            'in_bps': parse_rate(parts[1]) if len(parts) > 1 else 0,
                            'out_bps': parse_rate(parts[2]) if len(parts) > 2 else 0
                        }
                    except (ValueError, IndexError):
                        continue

        return interfaces

    # ------------------------------------------------------------------ #
    # gNMI helpers                                                        #
    # ------------------------------------------------------------------ #

    @staticmethod
    def _gnmi_updates(result: Dict) -> List:
        """Return the flat list of (path, val) updates from a GetResponse."""
        updates = []
        for notification in result.get('notification', []):
            updates.extend(notification.get('update', []))
        return updates

    @staticmethod
    def _gnmi_find_val(updates: List, key_fragment: str):
        """Return the val of the first update whose path contains key_fragment."""
        for u in updates:
            if key_fragment in u.get('path', ''):
                return u.get('val')
        return None

    @staticmethod
    def _parse_gnmi_interfaces(result: Dict) -> Dict:
        """
        Parse openconfig-interfaces:interfaces GetResponse.

        Handles two common response shapes:
          1. Single update whose val is the full interfaces object (JSON_IETF).
          2. Separate scalar updates per leaf (ASCII encoding / path-per-leaf).
        """
        stats = {'total': 0, 'up': 0, 'down': 0, 'admin_down': 0}
        counters = {}

        updates = DeviceTelemetry._gnmi_updates(result)

        # Shape 1: val is the complete interfaces object
        for update in updates:
            val = update.get('val')
            if not isinstance(val, dict):
                continue

            # Arista TerminAttr wraps in 'openconfig-interfaces:interface' key
            intf_list = (
                val.get('openconfig-interfaces:interface') or
                val.get('interface') or
                []
            )
            if not intf_list:
                continue

            for intf in intf_list:
                name = intf.get('name', '')
                state = intf.get('state', {})
                oper = state.get('oper-status', '').upper()
                admin = state.get('admin-status', '').upper()

                # Skip sub-interfaces and aggregate-only entries
                if not name:
                    continue

                stats['total'] += 1
                if admin == 'DOWN':
                    stats['admin_down'] += 1
                elif oper == 'UP':
                    stats['up'] += 1
                else:
                    stats['down'] += 1

                intf_counters = state.get('counters', {})
                if intf_counters:
                    counters[name] = {
                        'in_octets':  intf_counters.get('in-octets', 0),
                        'in_pkts':    intf_counters.get('in-unicast-pkts', 0),
                        'in_errors':  intf_counters.get('in-errors', 0),
                        'out_octets': intf_counters.get('out-octets', 0),
                        'out_pkts':   intf_counters.get('out-unicast-pkts', 0),
                        'out_errors': intf_counters.get('out-errors', 0),
                    }
            return stats  # done with shape-1

        # Shape 2: path-per-leaf updates (fallback)
        intf_map: Dict[str, Dict] = {}
        for update in updates:
            path = update.get('path', '')
            val  = update.get('val')
            # e.g. "openconfig-interfaces:interfaces/interface[name=Ethernet1]/state/oper-status"
            if '/interface[name=' not in path:
                continue
            parts = path.split('/')
            # extract name from e.g. "interface[name=Ethernet1]"
            seg = next((p for p in parts if p.startswith('interface[name=')), '')
            name = seg.replace('interface[name=', '').rstrip(']')
            if not name:
                continue
            leaf = parts[-1]
            intf_map.setdefault(name, {})[leaf] = val

        for name, leaves in intf_map.items():
            stats['total'] += 1
            oper  = str(leaves.get('oper-status', '')).upper()
            admin = str(leaves.get('admin-status', '')).upper()
            if admin == 'DOWN':
                stats['admin_down'] += 1
            elif oper == 'UP':
                stats['up'] += 1
            else:
                stats['down'] += 1

        return stats

    @staticmethod
    def _parse_gnmi_system(result: Dict) -> Dict:
        """Parse openconfig-system:system GetResponse for basic system info."""
        info: Dict = {}
        updates = DeviceTelemetry._gnmi_updates(result)

        for update in updates:
            val = update.get('val')
            path = update.get('path', '')

            if isinstance(val, dict):
                # Full system object
                state = (
                    val.get('openconfig-system:state') or
                    val.get('state') or
                    {}
                )
                if state:
                    if 'software-version' in state:
                        info['version'] = state['software-version']
                    if 'hostname' in state:
                        info['hostname'] = state['hostname']
                    if 'boot-time' in state:
                        import time
                        uptime_s = int(time.time()) - int(state['boot-time']) // 1_000_000_000
                        info['uptime'] = f"{uptime_s // 3600}h {(uptime_s % 3600) // 60}m"
            else:
                # Scalar leaf
                if 'software-version' in path:
                    info['version'] = str(val)
                elif path.endswith('/hostname') or path.endswith('/config/hostname'):
                    info['hostname'] = str(val)

        return info

    @staticmethod
    def _parse_gnmi_platform(result: Dict) -> Dict:
        """Parse openconfig-platform:components for model, serial, and temperature."""
        version_info: Dict = {}
        sensors = []
        updates = DeviceTelemetry._gnmi_updates(result)

        for update in updates:
            val = update.get('val')
            if not isinstance(val, dict):
                continue

            component_list = (
                val.get('openconfig-platform:component') or
                val.get('component') or
                []
            )
            for comp in component_list:
                state = comp.get('state', {})
                comp_type = str(state.get('type', '')).upper()
                comp_name = state.get('name', comp.get('name', ''))

                # Model + serial from chassis
                if 'CHASSIS' in comp_type or comp_name.lower() in ('chassis', 'system'):
                    if 'description' in state and not version_info.get('model'):
                        version_info['model'] = state['description']
                    if 'serial-no' in state and not version_info.get('serial'):
                        version_info['serial'] = state['serial-no']
                    if 'software-version' in state and not version_info.get('version'):
                        version_info['version'] = state['software-version']

                # Temperature sensors
                temp_data = state.get('temperature', {})
                if temp_data and 'instant' in temp_data:
                    current = float(temp_data.get('instant', 0))
                    warn_t  = float(temp_data.get('alarm-threshold', 75))
                    crit_t  = warn_t + 20  # rough estimate

                    if current >= crit_t:
                        sensor_status = 'critical'
                    elif current >= warn_t or temp_data.get('alarm-status', False):
                        sensor_status = 'warning'
                    else:
                        sensor_status = 'ok'

                    sensors.append({
                        'name': comp_name,
                        'temperature': current,
                        'warning_threshold': warn_t,
                        'critical_threshold': crit_t,
                        'status': sensor_status,
                    })

        return {
            'version_info': version_info,
            'temperature': {'sensors': sensors, 'count': len(sensors)},
        }

    @staticmethod
    def _parse_eos_native_interfaces(result: Dict) -> Dict:
        """
        Parse eos_native interface status from:
          eos_native:/Sysdb/interface/status/eth/phy/slice/1/intfStatus

        Each interface has its own notification block whose prefix ends with
        the interface name, e.g.:
          prefix = "Sysdb/interface/status/eth/phy/slice/1/intfStatus/Ethernet7"
        The update paths within that block are bare leaf names:
          {"path": "operStatus", "val": "intfOperDown"}
          {"path": "linkStatus",  "val": "linkDown"}
        """
        stats = {'total': 0, 'up': 0, 'down': 0, 'admin_down': 0}

        for notification in result.get('notification', []):
            prefix = notification.get('prefix', '')
            # Last segment of the prefix is the interface name
            intf_name = prefix.rstrip('/').split('/')[-1]
            # Skip aggregate/metadata entries (e.g. _counts)
            if not intf_name or intf_name.startswith('_') or intf_name == 'intfStatus':
                continue

            oper_status = None
            for update in notification.get('update', []):
                if update.get('path') == 'operStatus':
                    oper_status = update.get('val')
                    break

            if oper_status is None:
                continue  # no operStatus in this notification block

            stats['total'] += 1
            if oper_status == 'intfOperUp':
                stats['up'] += 1
            else:
                stats['down'] += 1

        return stats

    @staticmethod
    def collect_from_gnmi(connector) -> Dict:
        """
        Collect telemetry via gNMI/TerminAttr using eos_native Sysdb paths.

        vEOS-lab TerminAttr does not populate OpenConfig paths without a full
        CloudVision subscription, so we use Arista's native eos_native origin
        which is always available regardless of licensing.
        """
        telemetry: Dict = {
            'reachable': False,
            'version_info': {},
            'interfaces': {'total': 0, 'up': 0, 'down': 0, 'admin_down': 0},
            'system': {'cpu_percent': 0, 'memory_percent': 0},
            'temperature': {'sensors': [], 'count': 0},
            'interface_counters': {},
            'interface_rates': {},
        }

        try:
            if not connector.connect():
                telemetry['error'] = 'gNMI connection failed (check port 6030 / TerminAttr)'
                return telemetry

            # --- Interfaces (eos_native Sysdb path, always populated) ---
            # NOTE: gRPC channels are lazy — connect() succeeding only means the
            # channel object was created, not that the device actually responded.
            # We only mark reachable=True once a Get RPC returns a real response,
            # distinguishing "TerminAttr answered" from "gRPC channel opened but
            # device is down or built-in gNMI has no eos_native paths".
            try:
                result = connector.get(
                    'eos_native:/Sysdb/interface/status/eth/phy/slice/1/intfStatus'
                )
                if result is not None:
                    # Got a real response — TerminAttr is up and serving eos_native paths
                    telemetry['reachable'] = True
                    telemetry['interfaces'] = DeviceTelemetry._parse_eos_native_interfaces(result)
                else:
                    # connect() succeeded (gRPC channel opened) but the Get returned
                    # nothing — TerminAttr is likely not running; built-in EOS gNMI
                    # does not serve eos_native paths
                    telemetry['error'] = 'gNMI connected but no data returned (TerminAttr not running?)'
            except Exception as e:
                print(f"gNMI interface collection error: {e}", file=__import__('sys').stderr)
                telemetry['error'] = f'gNMI query error: {e}'

            connector.disconnect()

        except Exception as e:
            print(f"gNMI telemetry error: {e}", file=__import__('sys').stderr)
            telemetry['error'] = str(e)
            try:
                connector.disconnect()
            except Exception:
                pass

        return telemetry

    # ------------------------------------------------------------------ #
    # Main dispatcher                                                      #
    # ------------------------------------------------------------------ #

    @staticmethod
    def collect_from_device(connector) -> Dict:
        """Collect all telemetry from a device"""
        # Dispatch to gNMI collector when appropriate
        if type(connector).__name__ == 'GNMIConnector':
            return DeviceTelemetry.collect_from_gnmi(connector)

        telemetry = {
            'reachable': False,
            'version_info': {},
            'interfaces': {},
            'system': {}
        }

        try:
            # Determine connector type
            is_eapi = type(connector).__name__ == 'EAPIConnector'

            if is_eapi:
                # ── eAPI: ONE batched HTTP request for all telemetry ──────────────────
                # Batching is critical: 6 sequential calls each take up to 10s on a
                # loaded vEOS node, pushing total collection time past the 35s timeout
                # and causing spurious reachable=False / "Collection timeout" entries.
                # A single node.enable([cmd1, cmd2, ...]) does one HTTPS round-trip.
                EAPI_CMDS = [
                    'show version',                        # idx 0
                    'show interfaces status',              # idx 1
                    'show processes top once',             # idx 2
                    'show system environment temperature', # idx 3
                ]
                try:
                    result = connector.execute_commands(EAPI_CMDS)
                except Exception as e:
                    print(f"eAPI batch command failed: {e}")
                    result = []

                def _r(idx):
                    """Return the result dict for command at index, or {}.

                    Some commands return text output; in that case result['result']
                    is a string. Always return a dict so .get() calls are safe.
                    """
                    if not result or idx >= len(result):
                        return {}
                    item = result[idx]
                    if not isinstance(item, dict):
                        return {}
                    r = item.get('result', {})
                    return r if isinstance(r, dict) else {}

                # Version info — if result is empty, commands failed silently (e.g.
                # HTTP timeout returned [] without raising).  Treat as unreachable.
                d = _r(0)
                if not d:
                    telemetry['error'] = 'No response from device'
                    return telemetry
                telemetry['version_info'] = {
                    'version': d.get('version', ''),
                    'model':   d.get('modelName', ''),
                    'uptime':  str(d.get('uptime', '')),
                    'serial':  d.get('serialNumber', ''),
                }

                # Interface status
                interfaces_raw = _r(1).get('interfaceStatuses', {})
                stats = {'total': 0, 'up': 0, 'down': 0, 'admin_down': 0}
                for intf_data in interfaces_raw.values():
                    stats['total'] += 1
                    link = intf_data.get('linkStatus', '').lower()
                    proto = intf_data.get('lineProtocolStatus', '').lower()
                    if link == 'connected' or proto == 'up':
                        stats['up'] += 1
                    elif link == 'disabled':
                        stats['admin_down'] += 1
                    else:
                        stats['down'] += 1
                telemetry['interfaces'] = stats

                # CPU / Memory — eAPI returns structured JSON from show processes top once
                d = _r(2)
                cpu_info = d.get('cpuInfo', {}).get('%Cpu(s)', {})
                mem_info = d.get('memInfo', {}).get('physicalMem', {})
                if cpu_info or mem_info:
                    idle = cpu_info.get('idle', 100)
                    cpu_pct = round(100 - idle, 1)
                    mem_total = mem_info.get('memTotal', 0)
                    mem_free = mem_info.get('memFree', 0)
                    mem_buf = mem_info.get('memBuffer', 0)
                    mem_pct = round((mem_total - mem_free - mem_buf) / mem_total * 100, 1) if mem_total else 0
                    telemetry['system'] = {'cpu_percent': cpu_pct, 'memory_percent': mem_pct}
                else:
                    # Fallback: try text output field (SSH path / older EOS)
                    output = d.get('output', '')
                    if output:
                        telemetry['system'] = DeviceTelemetry.parse_cpu_memory(output)
                    else:
                        telemetry['system'] = {'cpu_percent': 0, 'memory_percent': 0}

                # Temperature
                sensors = []
                for s in _r(3).get('tempSensors', []):
                    sensors.append({
                        'name':               s.get('name', 'Unknown'),
                        'temperature':        s.get('currentTemperature', 0),
                        'warning_threshold':  s.get('overheatThreshold', 75),
                        'critical_threshold': s.get('criticalThreshold', 95),
                        'status':             'ok' if not s.get('inAlertState') else 'warning',
                    })
                telemetry['temperature'] = {'sensors': sensors, 'count': len(sensors)}

                # Counters and rates are not displayed on the dashboard — the
                # Metrics tab fetches them on demand via /api/devices/<h>/live-metrics.
                telemetry['interface_counters'] = {}
                telemetry['interface_rates'] = {}

            else:
                # ── SSH: sequential text commands ────────────────────────────────────
                try:
                    output = connector.execute_command('show version')
                    telemetry['version_info'] = DeviceTelemetry.parse_version(output)
                except Exception as e:
                    print(f"Error getting version info via SSH: {e}")
                    telemetry['version_info'] = {}

                try:
                    output = connector.execute_command('show interfaces status')
                    telemetry['interfaces'] = DeviceTelemetry.parse_interfaces_status(output)
                except Exception as e:
                    print(f"Error getting interface status via SSH: {e}")
                    telemetry['interfaces'] = {'total': 0, 'up': 0, 'down': 0, 'admin_down': 0}

                try:
                    output = connector.execute_command('show processes top once')
                    telemetry['system'] = DeviceTelemetry.parse_cpu_memory(output)
                except Exception as e:
                    print(f"Error getting system resources via SSH: {e}")
                    telemetry['system'] = {'cpu_percent': 0, 'memory_percent': 0}

                try:
                    output = connector.execute_command('show system environment temperature')
                    telemetry['temperature'] = DeviceTelemetry.parse_temperature(output)
                except Exception as e:
                    print(f"Error getting temperature via SSH: {e}")
                    telemetry['temperature'] = {'sensors': [], 'count': 0}

                # Counters/rates fetched on demand by Metrics tab, not needed here.
                telemetry['interface_counters'] = {}
                telemetry['interface_rates'] = {}

            telemetry['reachable'] = True

        except Exception as e:
            print(f"Telemetry collection error: {e}")
            telemetry['error'] = str(e)

        return telemetry
