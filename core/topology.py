#!/usr/bin/env python3
"""Network topology discovery via LLDP"""

import re
from typing import Dict, List, Optional, Set, Tuple


class TopologyDiscovery:
    """Discover network topology using LLDP"""

    @staticmethod
    def parse_lldp_neighbors(output: str, is_eapi: bool = False) -> List[Dict]:
        """
        Parse LLDP neighbors from command output

        Returns list of neighbors with:
        - local_interface: Local interface name
        - neighbor_device: Remote device hostname
        - neighbor_interface: Remote interface name
        - neighbor_description: Remote device description
        """
        neighbors = []

        if is_eapi:
            # eAPI returns structured data
            # Output is already parsed JSON from 'show lldp neighbors detail'
            if isinstance(output, dict):
                lldp_neighbors = output.get('lldpNeighbors', {})
                for local_port, neighbor_list in lldp_neighbors.items():
                    # Skip management interfaces — LLDP on Mgmt produces noise
                    if local_port.lower().startswith('management'):
                        continue
                    for neighbor in neighbor_list.get('lldpNeighborInfo', []):
                        # Arista eAPI wraps interfaceId in extra quotes, e.g. '"Ethernet1"'
                        raw_intf = neighbor.get('neighborInterfaceInfo', {}).get('interfaceId', 'Unknown')
                        neighbor_intf = raw_intf.strip('"')
                        neighbors.append({
                            'local_interface': local_port,
                            'neighbor_device': neighbor.get('systemName', 'Unknown'),
                            'neighbor_interface': neighbor_intf,
                            'neighbor_description': neighbor.get('systemDescription', ''),
                            'neighbor_mgmt_ip': neighbor.get('managementAddresses', [{}])[0].get('address', '') if neighbor.get('managementAddresses') else ''
                        })
        else:
            # SSH/CLI text output parsing
            # Parse 'show lldp neighbors detail' output
            current_neighbor = {}

            for line in output.split('\n'):
                line = line.strip()

                # Interface line: "Interface Ethernet1 detected 1 LLDP neighbors:"
                if line.startswith('Interface') and 'detected' in line:
                    if current_neighbor and 'neighbor_device' in current_neighbor:
                        neighbors.append(current_neighbor)
                        current_neighbor = {}
                    match = re.search(r'Interface\s+(\S+)\s+detected', line)
                    if match:
                        intf_name = match.group(1).strip()
                        # Skip management interfaces
                        if intf_name.lower().startswith('management'):
                            current_neighbor = {}
                        else:
                            current_neighbor = {'local_interface': intf_name}

                # System Name: "ceos2"
                elif '- System Name:' in line:
                    match = re.search(r'System Name:\s*"([^"]+)"', line)
                    if match:
                        current_neighbor['neighbor_device'] = match.group(1).strip()

                # Port ID: "Ethernet1"
                elif '- Port ID type:' in line:
                    # Skip this line, wait for actual Port ID
                    pass
                elif 'Port ID' in line and ':' in line and '- Port ID type' not in line:
                    match = re.search(r'Port ID\s*:\s*"([^"]+)"', line)
                    if match:
                        current_neighbor['neighbor_interface'] = match.group(1).strip()

                # System Description
                elif '- System Description:' in line:
                    match = re.search(r'System Description:\s*"([^"]+)"', line)
                    if match:
                        current_neighbor['neighbor_description'] = match.group(1).strip()

                # Management Address: 172.100.100.3
                elif 'Management Address        :' in line or 'Management Address:' in line:
                    # Skip subtype line
                    if 'Subtype' not in line:
                        match = re.search(r'Management Address\s*:\s*(\S+)', line)
                        if match:
                            addr = match.group(1).strip()
                            # Skip if it's a subtype descriptor
                            if not addr.startswith('IPv') and addr not in current_neighbor.get('neighbor_mgmt_ip', ''):
                                current_neighbor['neighbor_mgmt_ip'] = addr

            # Add last neighbor
            if current_neighbor and 'neighbor_device' in current_neighbor:
                neighbors.append(current_neighbor)

        return neighbors

    @staticmethod
    def _parse_lldp_oc_gnmi(result: Dict) -> List[Dict]:
        """
        Parse an OpenConfig gNMI GetResponse for LLDP neighbors.

        Two response shapes are handled:
          Shape A — one notification per neighbor leaf (path-per-leaf / ASCII):
            prefix = "lldp/interfaces/interface[name=Ethernet1]/neighbors/neighbor[id=<id>]"
            update  = [{"path": "state/system-name", "val": "switch2"}, ...]

          Shape B — bulk JSON_IETF val containing the whole lldp object:
            prefix = "" / "lldp"
            update  = [{"path": "...", "val": { "openconfig-lldp:lldp": { ... } }}]
        """
        neighbors: List[Dict] = []

        # ── Shape A: path-per-leaf, one notification per neighbor leaf ──────
        neigh_map: Dict[tuple, Dict] = {}
        for notification in result.get('notification', []):
            prefix = notification.get('prefix', '')
            intf_m = re.search(r'interface\[name=([^\]]+)\]', prefix)
            neigh_m = re.search(r'neighbor\[id=([^\]]+)\]', prefix)
            if not (intf_m and neigh_m):
                continue
            key = (intf_m.group(1), neigh_m.group(1))
            entry = neigh_map.setdefault(key, {'local_interface': intf_m.group(1)})

            for update in notification.get('update', []):
                path = update.get('path', '')
                val  = update.get('val')
                if path.endswith('system-name'):
                    entry['neighbor_device'] = str(val)
                elif path.endswith('port-id'):
                    entry['neighbor_interface'] = str(val)
                elif path.endswith('system-description'):
                    entry['neighbor_description'] = str(val)
                elif 'management-address' in path and 'neighbor_mgmt_ip' not in entry:
                    entry['neighbor_mgmt_ip'] = str(val)

        for entry in neigh_map.values():
            if 'neighbor_device' in entry:
                neighbors.append(entry)

        if neighbors:
            return neighbors

        # ── Shape B: bulk JSON_IETF dict ─────────────────────────────────────
        for notification in result.get('notification', []):
            for update in notification.get('update', []):
                val = update.get('val')
                if not isinstance(val, dict):
                    continue
                lldp_root = (
                    val.get('openconfig-lldp:lldp') or
                    val.get('lldp') or
                    {}
                )
                intfs = (
                    lldp_root.get('interfaces', {}).get('interface') or
                    lldp_root.get('openconfig-lldp:interfaces', {})
                           .get('openconfig-lldp:interface') or
                    []
                )
                for intf in intfs:
                    local_intf = intf.get('name', '')
                    for neigh in (
                        intf.get('neighbors', {}).get('neighbor') or
                        intf.get('openconfig-lldp:neighbors', {})
                            .get('openconfig-lldp:neighbor') or
                        []
                    ):
                        state = neigh.get('state', {})
                        if state.get('system-name'):
                            neighbors.append({
                                'local_interface':    local_intf,
                                'neighbor_device':    state.get('system-name', ''),
                                'neighbor_interface': state.get('port-id', ''),
                                'neighbor_description': state.get('system-description', ''),
                                'neighbor_mgmt_ip':   '',
                            })

        return neighbors

    @staticmethod
    def _get_lldp_via_gnmi(connector) -> List[Dict]:
        """
        Fetch LLDP neighbors via a connected GNMIConnector.

        Tries OpenConfig LLDP first (works with full CVP licence).
        Falls back gracefully to an empty list when the device does not
        populate OpenConfig paths (e.g. vEOS-lab without a CVP subscription).
        """
        # OpenConfig LLDP
        try:
            result = connector.get('openconfig:lldp')
            if result and result.get('notification'):
                parsed = TopologyDiscovery._parse_lldp_oc_gnmi(result)
                if parsed:
                    return parsed
        except Exception:
            pass

        # Nothing available — return empty; the device still appears as a node
        return []

    @staticmethod
    def discover_topology(devices_info: List[Dict]) -> Dict:
        """
        Discover full network topology from multiple devices

        Args:
            devices_info: List of dicts with 'hostname', 'connector', 'is_eapi'

        Returns:
            Dict with 'nodes', 'links', and 'device_status'
        """
        all_links = []
        seen_links = set()  # Track bidirectional links
        nodes = {}
        device_status = []  # Per-device LLDP discovery status

        for device_info in devices_info:
            hostname = device_info['hostname']
            connector = device_info['connector']
            is_eapi = device_info.get('is_eapi', False)

            # Add node
            nodes[hostname] = {
                'id': hostname,
                'label': hostname,
                'role': device_info.get('role', 'unknown'),
                'model': device_info.get('model', 'unknown'),
                'ip': device_info.get('ip', ''),
                'management_type': device_info.get('management_type', ''),
            }

            lldp_source = 'none'
            lldp_error = None

            try:
                # Get LLDP neighbors
                is_gnmi = device_info.get('is_gnmi', False)

                if is_gnmi:
                    # gNMI: connect, fetch, disconnect within this block
                    if not connector.connect():
                        print(f"gNMI connect failed for {hostname}, skipping LLDP")
                        neighbors = []
                        lldp_error = 'gNMI connect failed'
                    else:
                        neighbors = TopologyDiscovery._get_lldp_via_gnmi(connector)
                        connector.disconnect()
                        if neighbors:
                            lldp_source = 'gnmi'

                    # If gNMI returned no LLDP data, fall back to SSH
                    if not neighbors:
                        fallback = device_info.get('lldp_fallback')
                        if fallback:
                            try:
                                if fallback.connect():
                                    output = fallback.execute_command('show lldp neighbors detail')
                                    neighbors = TopologyDiscovery.parse_lldp_neighbors(output, False)
                                    fallback.disconnect()
                                    lldp_source = 'ssh_fallback' if neighbors else 'ssh_fallback_empty'
                                else:
                                    lldp_error = (lldp_error or '') + '; SSH fallback connect failed'
                            except Exception as fb_e:
                                lldp_error = (lldp_error or '') + f'; SSH fallback error: {fb_e}'
                                print(f"SSH LLDP fallback failed for {hostname}: {fb_e}")
                        else:
                            lldp_error = (lldp_error or '') + '; no fallback configured'
                elif is_eapi:
                    result = connector.execute_commands(['show lldp neighbors detail'])
                    lldp_data = result[0]['result'] if result else {}
                    neighbors = TopologyDiscovery.parse_lldp_neighbors(lldp_data, True)
                    lldp_source = 'eapi' if neighbors else 'eapi_empty'
                else:
                    lldp_output = connector.execute_command('show lldp neighbors detail')
                    neighbors = TopologyDiscovery.parse_lldp_neighbors(lldp_output, False)
                    lldp_source = 'ssh' if neighbors else 'ssh_empty'

                device_status.append({
                    'hostname': hostname,
                    'lldp_source': lldp_source,
                    'neighbor_count': len(neighbors),
                    'error': lldp_error,
                })

                # Create links
                for neighbor in neighbors:
                    neighbor_device = neighbor.get('neighbor_device', '').strip()
                    local_intf = neighbor.get('local_interface', '').strip()
                    remote_intf = neighbor.get('neighbor_interface', '').strip()

                    if not neighbor_device or not local_intf or not remote_intf:
                        continue

                    # Resolve neighbor to canonical DB hostname (case-insensitive).
                    # LLDP system-name may differ in case or domain suffix from the
                    # DB hostname, which would cause seen_links to miss duplicates.
                    canonical_neighbor = next(
                        (n for n in nodes if n.lower() == neighbor_device.lower()),
                        neighbor_device
                    )

                    # Add neighbor as node if not already present
                    if canonical_neighbor not in nodes:
                        nodes[canonical_neighbor] = {
                            'id': canonical_neighbor,
                            'label': canonical_neighbor,
                            'role': 'unknown',
                            'model': 'unknown',
                            'ip': neighbor.get('neighbor_mgmt_ip', '')
                        }

                    # Create unique link identifier (bidirectional, case-normalised)
                    link_key = tuple(sorted([
                        f"{hostname.lower()}:{local_intf.lower()}",
                        f"{canonical_neighbor.lower()}:{remote_intf.lower()}"
                    ]))

                    if link_key not in seen_links:
                        seen_links.add(link_key)
                        all_links.append({
                            'from': hostname,
                            'to': canonical_neighbor,
                            'from_interface': local_intf,
                            'to_interface': remote_intf,
                            'id': f"{hostname}_{local_intf}_{canonical_neighbor}_{remote_intf}"
                        })

            except Exception as e:
                print(f"Error discovering topology from {hostname}: {e}")
                device_status.append({
                    'hostname': hostname,
                    'lldp_source': 'error',
                    'neighbor_count': 0,
                    'error': str(e),
                })
                continue

        # Final dedup pass — catches any residual duplicates where the same
        # physical link was added from both ends with slightly different names
        seen_final: Set[tuple] = set()
        deduped_links = []
        for link in all_links:
            key = tuple(sorted([
                f"{link['from'].lower()}:{link['from_interface'].lower()}",
                f"{link['to'].lower()}:{link['to_interface'].lower()}"
            ]))
            if key not in seen_final:
                seen_final.add(key)
                deduped_links.append(link)

        return {
            'nodes': list(nodes.values()),
            'links': deduped_links,
            'device_status': device_status,
        }

    @staticmethod
    def get_topology_stats(topology: Dict) -> Dict:
        """Get statistics about the topology"""
        nodes = topology.get('nodes', [])
        links = topology.get('links', [])

        # Count nodes by role
        role_counts = {}
        for node in nodes:
            role = node.get('role', 'unknown')
            role_counts[role] = role_counts.get(role, 0) + 1

        return {
            'total_nodes': len(nodes),
            'total_links': len(links),
            'roles': role_counts
        }
