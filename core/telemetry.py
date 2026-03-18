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

            # Version info
            if is_eapi:
                try:
                    result = connector.execute_commands(['show version'])
                    # eAPI returns JSON data directly in result
                    if result and len(result) > 0:
                        data = result[0].get('result', result[0]) if isinstance(result[0], dict) else {}
                        telemetry['version_info'] = {
                            'version': data.get('version', ''),
                            'model': data.get('modelName', ''),
                            'uptime': str(data.get('uptime', '')),
                            'serial': data.get('serialNumber', '')
                        }
                except Exception as e:
                    print(f"Error getting version info via eAPI: {e}")
                    telemetry['version_info'] = {}
            else:
                try:
                    output = connector.execute_command('show version')
                    telemetry['version_info'] = DeviceTelemetry.parse_version(output)
                except Exception as e:
                    print(f"Error getting version info via SSH: {e}")
                    telemetry['version_info'] = {}

            # Interface status
            if is_eapi:
                try:
                    result = connector.execute_commands(['show interfaces status'])
                    # eAPI returns structured interface data
                    if result and len(result) > 0:
                        data = result[0].get('result', result[0]) if isinstance(result[0], dict) else {}
                        interfaces = data.get('interfaceStatuses', {})
                        stats = {'total': 0, 'up': 0, 'down': 0, 'admin_down': 0}
                        for intf_name, intf_data in interfaces.items():
                            stats['total'] += 1
                            link_status = intf_data.get('linkStatus', '').lower()
                            line_protocol = intf_data.get('lineProtocolStatus', '').lower()
                            if link_status == 'connected' or line_protocol == 'up':
                                stats['up'] += 1
                            elif link_status == 'disabled':
                                stats['admin_down'] += 1
                            else:
                                stats['down'] += 1
                        telemetry['interfaces'] = stats
                    else:
                        telemetry['interfaces'] = {'total': 0, 'up': 0, 'down': 0, 'admin_down': 0}
                except Exception as e:
                    print(f"Error getting interface status via eAPI: {e}")
                    telemetry['interfaces'] = {'total': 0, 'up': 0, 'down': 0, 'admin_down': 0}
            else:
                try:
                    output = connector.execute_command('show interfaces status')
                    telemetry['interfaces'] = DeviceTelemetry.parse_interfaces_status(output)
                except Exception as e:
                    print(f"Error getting interface status via SSH: {e}")
                    telemetry['interfaces'] = {'total': 0, 'up': 0, 'down': 0, 'admin_down': 0}

            # System resources
            try:
                if is_eapi:
                    result = connector.execute_commands(['show processes top once'])
                    # eAPI may return text output for 'show processes top'
                    if result and len(result) > 0:
                        data = result[0].get('result', result[0]) if isinstance(result[0], dict) else {}
                        # Try to get text output if available, otherwise use structured data
                        if 'output' in data:
                            output = data['output']
                            telemetry['system'] = DeviceTelemetry.parse_cpu_memory(output)
                        else:
                            # Fallback if no CPU/memory data available
                            telemetry['system'] = {'cpu_percent': 0, 'memory_percent': 0}
                    else:
                        telemetry['system'] = {'cpu_percent': 0, 'memory_percent': 0}
                else:
                    output = connector.execute_command('show processes top once')
                    telemetry['system'] = DeviceTelemetry.parse_cpu_memory(output)
            except Exception as e:
                print(f"Error getting system resources: {e}")
                telemetry['system'] = {'cpu_percent': 0, 'memory_percent': 0}

            # Temperature sensors
            try:
                if is_eapi:
                    result = connector.execute_commands(['show system environment temperature'])
                    if result and len(result) > 0:
                        data = result[0].get('result', result[0]) if isinstance(result[0], dict) else {}
                        # eAPI temperature is structured, convert to similar format
                        sensors = []
                        if 'tempSensors' in data:
                            for sensor_data in data.get('tempSensors', []):
                                sensors.append({
                                    'name': sensor_data.get('name', 'Unknown'),
                                    'temperature': sensor_data.get('currentTemperature', 0),
                                    'warning_threshold': sensor_data.get('overheatThreshold', 75),
                                    'critical_threshold': sensor_data.get('criticalThreshold', 95),
                                    'status': 'ok' if sensor_data.get('inAlertState', False) == False else 'warning'
                                })
                        telemetry['temperature'] = {'sensors': sensors, 'count': len(sensors)}
                    else:
                        telemetry['temperature'] = {'sensors': [], 'count': 0}
                else:
                    output = connector.execute_command('show system environment temperature')
                    telemetry['temperature'] = DeviceTelemetry.parse_temperature(output)
            except Exception as e:
                print(f"Error getting temperature: {e}")
                telemetry['temperature'] = {'sensors': [], 'count': 0}

            # Interface counters (errors/traffic)
            try:
                if is_eapi:
                    result = connector.execute_commands(['show interfaces counters'])
                    if result and len(result) > 0:
                        data = result[0].get('result', result[0]) if isinstance(result[0], dict) else {}
                        # eAPI returns structured counter data
                        interfaces = {}
                        if 'interfaces' in data:
                            for intf_name, intf_data in data.get('interfaces', {}).items():
                                counters = intf_data.get('interfaceCounters', {})
                                interfaces[intf_name] = {
                                    'in_octets': counters.get('inOctets', 0),
                                    'in_pkts': counters.get('inUcastPkts', 0),
                                    'in_errors': counters.get('inErrors', 0),
                                    'out_octets': counters.get('outOctets', 0),
                                    'out_pkts': counters.get('outUcastPkts', 0),
                                    'out_errors': counters.get('outErrors', 0)
                                }
                        telemetry['interface_counters'] = interfaces
                    else:
                        telemetry['interface_counters'] = {}
                else:
                    output = connector.execute_command('show interfaces counters')
                    telemetry['interface_counters'] = DeviceTelemetry.parse_interface_counters(output)
            except Exception as e:
                print(f"Error getting interface counters: {e}")
                telemetry['interface_counters'] = {}

            # Interface bandwidth rates
            try:
                if is_eapi:
                    result = connector.execute_commands(['show interfaces counters rates'])
                    if result and len(result) > 0:
                        data = result[0].get('result', result[0]) if isinstance(result[0], dict) else {}
                        # eAPI returns structured rate data
                        interfaces = {}
                        if 'interfaces' in data:
                            for intf_name, intf_data in data.get('interfaces', {}).items():
                                interfaces[intf_name] = {
                                    'in_bps': intf_data.get('inBitsPerSecond', 0),
                                    'out_bps': intf_data.get('outBitsPerSecond', 0)
                                }
                        telemetry['interface_rates'] = interfaces
                    else:
                        telemetry['interface_rates'] = {}
                else:
                    output = connector.execute_command('show interfaces counters rates')
                    telemetry['interface_rates'] = DeviceTelemetry.parse_interface_rates(output)
            except Exception as e:
                print(f"Error getting interface rates: {e}")
                telemetry['interface_rates'] = {}

            telemetry['reachable'] = True

        except Exception as e:
            print(f"Telemetry collection error: {e}")
            telemetry['error'] = str(e)

        return telemetry
