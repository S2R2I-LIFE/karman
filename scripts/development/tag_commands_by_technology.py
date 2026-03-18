#!/usr/bin/env python3
"""
Tag all CLI commands with technology and action categories
Part of Phase 1 of Hybrid Navigation implementation
"""

import sqlite3
import json
from collections import defaultdict
import re

# Technology pattern definitions
TECHNOLOGY_PATTERNS = {
    'BGP': {
        'patterns': ['bgp', 'border gateway', 'neighbor.*remote-as', 'neighbor.*activate'],
        'modes': ['RouterBgpBaseMode', 'RouterBgpVrfMode', 'RouterBgpAfMode']
    },
    'OSPF': {
        'patterns': ['ospf', 'area.*authentication', 'area.*stub'],
        'modes': ['RouterOspfMode', 'RouterOspfVrfMode', 'IntfConfigOspfMode']
    },
    'ISIS': {
        'patterns': ['isis', 'is-is', 'clns'],
        'modes': ['RouterIsisMode', 'IntfConfigIsisMode']
    },
    'Interfaces': {
        'patterns': ['interface', 'ethernet', 'port-channel', 'loopback', 'vxlan', 'management'],
        'modes': ['IntfConfigMode', 'IntfEthernetMode', 'IntfPortChannelMode', 'IntfLoopbackMode']
    },
    'VLANs': {
        'patterns': ['vlan(?!\\s*interface)', 'switchport', 'trunk', 'access-group'],
        'modes': ['VlanMode', 'IntfConfigSwitchportMode']
    },
    'ACLs': {
        'patterns': ['access-list', '\\bacl\\b', 'permit', 'deny', 'ip access-group'],
        'modes': ['AclMode', 'Ipv6AclMode', 'MacAclMode']
    },
    'QoS': {
        'patterns': ['qos', 'policy-map', 'class-map', 'service-policy', 'traffic-shape', 'priority'],
        'modes': ['QosPolicyMode', 'QosClassMode', 'QosServicePolicyMode']
    },
    'Multicast': {
        'patterns': ['igmp', 'pim', 'mroute', 'multicast', 'msdp'],
        'modes': ['RouterPimMode', 'RouterIgmpMode', 'RouterMsdpMode']
    },
    'MPLS': {
        'patterns': ['mpls', 'label', 'ldp', 'rsvp', 'traffic-engineering'],
        'modes': ['MplsMode', 'MplsLdpMode', 'MplsRsvpMode']
    },
    'VRF': {
        'patterns': ['\\bvrf\\b', 'route-target', 'rd\\s+\\d+:\\d+'],
        'modes': ['VrfMode', 'RouterBgpVrfMode', 'RouterOspfVrfMode']
    },
    'Routing': {
        'patterns': ['\\broute\\b', 'routing', 'static', 'ip route', 'ipv6 route'],
        'modes': ['ConfigSessionMode']
    },
    'ARP': {
        'patterns': ['\\barp\\b', 'neighbor-advertisement'],
        'modes': []
    },
    'NAT': {
        'patterns': ['\\bnat\\b', 'ip nat', 'translation'],
        'modes': ['NatMode']
    },
    'AAA': {
        'patterns': ['aaa', 'tacacs', 'radius', 'authentication', 'authorization', 'accounting'],
        'modes': ['AaaMode', 'TacacsMode', 'RadiusMode']
    },
    'SNMP': {
        'patterns': ['snmp', 'community', 'trap', 'mib'],
        'modes': ['SnmpMode']
    },
    'Logging': {
        'patterns': ['logging', '\\blog\\b', 'syslog'],
        'modes': ['LoggingMode']
    },
    'NTP': {
        'patterns': ['\\bntp\\b', 'clock'],
        'modes': ['NtpMode']
    },
    'STP': {
        'patterns': ['spanning-tree', '\\bstp\\b', 'bpdu'],
        'modes': ['StpMode']
    },
    'LLDP': {
        'patterns': ['lldp', 'link layer discovery'],
        'modes': ['LldpMode']
    },
    'MLAG': {
        'patterns': ['mlag', 'peer-link'],
        'modes': ['MlagMode']
    },
    'BFD': {
        'patterns': ['\\bbfd\\b', 'bidirectional forwarding'],
        'modes': ['BfdMode']
    },
    'EVPN': {
        'patterns': ['evpn', 'vxlan', 'overlay'],
        'modes': ['EvpnMode', 'VxlanMode']
    },
    'Hardware': {
        'patterns': ['platform', 'hardware', 'transceiver', 'module', 'power', 'fan', 'temperature'],
        'modes': ['PlatformMode', 'HardwareMode']
    },
    'System': {
        'patterns': ['hostname', 'banner', 'boot', 'reload', 'shutdown', 'copy', 'write'],
        'modes': ['ConfigSessionMode', 'EnableMode']
    },
    'Monitoring': {
        'patterns': ['monitor', 'debug', 'trace'],
        'modes': ['EnableMode', 'ConfigSessionMode']
    }
}

# Action pattern definitions
ACTION_PATTERNS = {
    'Show': ['show'],
    'Configure': [],  # Default for config modes
    'Remove': ['no '],
    'Reset': ['default '],
    'Clear': ['clear'],
    'Debug': ['debug', 'trace'],
    'Monitor': ['monitor']
}


def compile_patterns(patterns_dict):
    """Compile regex patterns for efficiency"""
    compiled = {}
    for category, info in patterns_dict.items():
        compiled[category] = {
            'patterns': [re.compile(p, re.IGNORECASE) for p in info['patterns']],
            'modes': set(info['modes'])
        }
    return compiled


def tag_command(command_text, command_base, mode_name, mode_category, tech_patterns):
    """
    Determine technology and action tags for a command
    Returns: (technology_tags, action_tags)
    """
    technology_tags = []
    action_tags = []

    # Determine action tags
    cmd_lower = command_base.lower()
    if cmd_lower.startswith('show'):
        action_tags.append('Show')
    elif cmd_lower.startswith('no '):
        action_tags.append('Remove')
    elif cmd_lower.startswith('default '):
        action_tags.append('Reset')
    elif cmd_lower.startswith('clear'):
        action_tags.append('Clear')
    elif cmd_lower.startswith('debug') or 'trace' in cmd_lower:
        action_tags.append('Debug')
    elif cmd_lower.startswith('monitor'):
        action_tags.append('Monitor')
    else:
        # Configuration command
        action_tags.append('Configure')

    # Determine technology tags (can have multiple)
    search_text = f"{command_text} {command_base} {mode_name}".lower()

    for tech, info in tech_patterns.items():
        # Check if mode matches
        if mode_name in info['modes']:
            technology_tags.append(tech)
            continue

        # Check if any pattern matches
        for pattern in info['patterns']:
            if pattern.search(search_text):
                technology_tags.append(tech)
                break

    # If no technology matched, try to infer from mode category
    if not technology_tags:
        if 'routing' in mode_category.lower():
            technology_tags.append('Routing')
        elif 'interface' in mode_category.lower():
            technology_tags.append('Interfaces')
        elif 'config' in mode_category.lower():
            technology_tags.append('System')

    # Remove duplicates while preserving order
    technology_tags = list(dict.fromkeys(technology_tags))
    action_tags = list(dict.fromkeys(action_tags))

    return technology_tags, action_tags


def tag_all_commands(db_path='custom-cvp.db', batch_size=1000, verbose=True):
    """
    Tag all commands in the database
    """
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # Compile patterns for efficiency
    tech_patterns = compile_patterns(TECHNOLOGY_PATTERNS)

    # Get total count
    cursor.execute("SELECT COUNT(*) FROM cli_commands")
    total_commands = cursor.fetchone()[0]

    if verbose:
        print(f"Tagging {total_commands:,} commands...")
        print("=" * 70)

    # Get all commands
    cursor.execute("""
        SELECT c.command_id, c.command_text, c.command_base, m.mode_name, m.mode_category
        FROM cli_commands c
        JOIN cli_modes m ON c.mode_id = m.mode_id
    """)

    # Statistics
    tech_counts = defaultdict(int)
    action_counts = defaultdict(int)
    processed = 0
    updates = []

    for row in cursor.fetchall():
        command_id, command_text, command_base, mode_name, mode_category = row

        # Tag the command
        tech_tags, action_tags = tag_command(
            command_text, command_base, mode_name, mode_category, tech_patterns
        )

        # Store for batch update
        updates.append((
            json.dumps(tech_tags),
            json.dumps(action_tags),
            command_id
        ))

        # Update statistics
        for tech in tech_tags:
            tech_counts[tech] += 1
        for action in action_tags:
            action_counts[action] += 1

        processed += 1

        # Batch update
        if len(updates) >= batch_size:
            cursor.executemany("""
                UPDATE cli_commands
                SET technology_tags = ?, action_tags = ?
                WHERE command_id = ?
            """, updates)
            conn.commit()

            if verbose:
                print(f"  Processed {processed:,} / {total_commands:,} ({processed*100/total_commands:.1f}%)")

            updates = []

    # Final batch
    if updates:
        cursor.executemany("""
            UPDATE cli_commands
            SET technology_tags = ?, action_tags = ?
            WHERE command_id = ?
        """, updates)
        conn.commit()

    conn.close()

    if verbose:
        print(f"\n{'='*70}")
        print(f"Tagging complete! Processed {processed:,} commands")
        print(f"\n{'='*70}")
        print("TECHNOLOGY DISTRIBUTION:")
        print(f"{'='*70}")
        for tech, count in sorted(tech_counts.items(), key=lambda x: x[1], reverse=True):
            percentage = (count / total_commands) * 100
            print(f"{tech:20} {count:6,} commands ({percentage:5.1f}%)")

        print(f"\n{'='*70}")
        print("ACTION DISTRIBUTION:")
        print(f"{'='*70}")
        for action, count in sorted(action_counts.items(), key=lambda x: x[1], reverse=True):
            percentage = (count / total_commands) * 100
            print(f"{action:20} {count:6,} commands ({percentage:5.1f}%)")

    return tech_counts, action_counts


def verify_tagging(db_path='custom-cvp.db'):
    """Verify that tagging was successful"""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # Count commands with tags
    cursor.execute("""
        SELECT
            COUNT(*) as total,
            SUM(CASE WHEN technology_tags IS NOT NULL THEN 1 ELSE 0 END) as with_tech,
            SUM(CASE WHEN action_tags IS NOT NULL THEN 1 ELSE 0 END) as with_action
        FROM cli_commands
    """)

    total, with_tech, with_action = cursor.fetchone()

    print(f"\n{'='*70}")
    print("VERIFICATION:")
    print(f"{'='*70}")
    print(f"Total commands:              {total:,}")
    print(f"With technology tags:        {with_tech:,} ({with_tech*100/total:.1f}%)")
    print(f"With action tags:            {with_action:,} ({with_action*100/total:.1f}%)")

    # Sample some tagged commands
    print(f"\n{'='*70}")
    print("SAMPLE TAGGED COMMANDS:")
    print(f"{'='*70}")

    cursor.execute("""
        SELECT command_text, technology_tags, action_tags
        FROM cli_commands
        WHERE technology_tags IS NOT NULL
        LIMIT 10
    """)

    for cmd_text, tech_tags, action_tags in cursor.fetchall():
        tech = json.loads(tech_tags) if tech_tags else []
        actions = json.loads(action_tags) if action_tags else []
        print(f"\nCommand: {cmd_text[:60]}...")
        print(f"  Technologies: {', '.join(tech)}")
        print(f"  Actions: {', '.join(actions)}")

    conn.close()


if __name__ == '__main__':
    print("=" * 70)
    print("CLI COMMAND TECHNOLOGY TAGGER")
    print("Phase 1 of Hybrid Navigation Implementation")
    print("=" * 70)
    print()

    # Tag all commands
    tech_counts, action_counts = tag_all_commands()

    # Verify the results
    verify_tagging()

    print(f"\n{'='*70}")
    print("✓ Technology tagging complete!")
    print("✓ Ready for Phase 2: API endpoint implementation")
    print(f"{'='*70}")
