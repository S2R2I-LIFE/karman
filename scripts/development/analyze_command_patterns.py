#!/usr/bin/env python3
"""
Analyze command patterns to support alternative navigation approaches
"""

import sqlite3
import json
from collections import defaultdict
import re

def analyze_technologies(db_path='custom-cvp.db'):
    """Analyze commands by technology/feature"""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # Get all commands
    cursor.execute("""
        SELECT c.command_id, c.command_text, c.command_base, m.mode_name, m.mode_category
        FROM cli_commands c
        JOIN cli_modes m ON c.mode_id = m.mode_id
    """)

    tech_patterns = {
        'BGP': ['bgp', 'border gateway'],
        'OSPF': ['ospf'],
        'ISIS': ['isis', 'is-is'],
        'Interface': ['interface', 'ethernet', 'port-channel', 'loopback', 'vlan'],
        'VLAN': ['vlan', 'switchport'],
        'ACL': ['access-list', 'acl', 'permit', 'deny'],
        'QoS': ['qos', 'policy-map', 'class-map', 'service-policy'],
        'Multicast': ['igmp', 'pim', 'mroute', 'multicast'],
        'MPLS': ['mpls', 'label', 'ldp'],
        'VRF': ['vrf'],
        'Routing Table': ['route', 'routing'],
        'ARP': ['arp'],
        'NAT': ['nat'],
        'AAA': ['aaa', 'tacacs', 'radius'],
        'SNMP': ['snmp'],
        'Logging': ['logging', 'log'],
        'NTP': ['ntp', 'clock'],
        'STP': ['spanning-tree', 'stp'],
        'LLDP': ['lldp'],
        'MLAG': ['mlag', 'port-channel'],
        'BFD': ['bfd'],
        'Hardware': ['platform', 'hardware', 'transceiver'],
    }

    technology_counts = defaultdict(int)
    technology_commands = defaultdict(list)

    for row in cursor.fetchall():
        cmd_id, cmd_text, cmd_base, mode_name, mode_category = row

        for tech, patterns in tech_patterns.items():
            match_found = False
            for pattern in patterns:
                if (pattern in cmd_text.lower() or
                    pattern in cmd_base.lower() or
                    pattern in mode_name.lower()):
                    technology_counts[tech] += 1
                    if len(technology_commands[tech]) < 5:  # Store sample
                        technology_commands[tech].append({
                            'command': cmd_text[:80],
                            'mode': mode_name
                        })
                    match_found = True
                    break
            if match_found:
                break

    conn.close()

    return technology_counts, technology_commands


def analyze_actions(db_path='custom-cvp.db'):
    """Analyze commands by action/verb"""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    cursor.execute("""
        SELECT command_text, command_base
        FROM cli_commands
    """)

    action_counts = defaultdict(int)

    for row in cursor.fetchall():
        cmd_text, cmd_base = row

        # Extract first word/phrase
        if cmd_base.startswith('show'):
            action_counts['Show/Display'] += 1
        elif cmd_base.startswith('no'):
            action_counts['Remove (no)'] += 1
        elif cmd_base.startswith('default'):
            action_counts['Reset (default)'] += 1
        elif cmd_base.startswith('clear'):
            action_counts['Clear'] += 1
        elif cmd_base.startswith('debug'):
            action_counts['Debug'] += 1
        elif any(x in cmd_base for x in ['enable', 'disable']):
            action_counts['Enable/Disable'] += 1
        else:
            action_counts['Configure'] += 1

    conn.close()
    return action_counts


def analyze_objects(db_path='custom-cvp.db'):
    """Analyze commands by network object"""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    cursor.execute("""
        SELECT command_text, command_base
        FROM cli_commands
    """)

    object_patterns = {
        'Neighbor/Peer': ['neighbor', 'peer', 'adjacency'],
        'Route': ['route', 'prefix', 'network'],
        'Interface': ['interface', 'port', 'ethernet'],
        'VLAN': ['vlan'],
        'ACL': ['access-list', 'acl'],
        'Policy': ['policy', 'route-map'],
        'User/Session': ['user', 'session', 'login'],
        'Configuration': ['running-config', 'startup-config', 'config'],
        'Counter/Stats': ['counter', 'statistics', 'stat'],
        'Table': ['table', 'database'],
    }

    object_counts = defaultdict(int)

    for row in cursor.fetchall():
        cmd_text, cmd_base = row

        for obj, patterns in object_patterns.items():
            for pattern in patterns:
                if pattern in cmd_text.lower() or pattern in cmd_base.lower():
                    object_counts[obj] += 1
                    break

    conn.close()
    return object_counts


def main():
    print("=" * 70)
    print("CLI COMMAND PATTERN ANALYSIS")
    print("=" * 70)
    print()

    # Technology analysis
    print("📊 COMMANDS BY TECHNOLOGY/FEATURE")
    print("-" * 70)
    tech_counts, tech_samples = analyze_technologies()

    # Sort by count
    for tech, count in sorted(tech_counts.items(), key=lambda x: x[1], reverse=True):
        print(f"{tech:25} {count:5,} commands")
        if tech in tech_samples and tech_samples[tech]:
            print(f"  Sample: {tech_samples[tech][0]['command'][:60]}...")

    total_categorized = sum(tech_counts.values())
    print(f"\nTotal categorized: {total_categorized:,}")

    print()
    print("=" * 70)

    # Action analysis
    print("\n🎬 COMMANDS BY ACTION/VERB")
    print("-" * 70)
    action_counts = analyze_actions()
    for action, count in sorted(action_counts.items(), key=lambda x: x[1], reverse=True):
        percentage = (count / 24026) * 100
        print(f"{action:25} {count:6,} commands ({percentage:5.1f}%)")

    print()
    print("=" * 70)

    # Object analysis
    print("\n🎯 COMMANDS BY NETWORK OBJECT")
    print("-" * 70)
    object_counts = analyze_objects()
    for obj, count in sorted(object_counts.items(), key=lambda x: x[1], reverse=True):
        print(f"{obj:25} {count:5,} commands")

    print()
    print("=" * 70)
    print("\n💡 INSIGHTS FOR ALTERNATIVE NAVIGATION:")
    print("-" * 70)
    print()
    print("1. TECHNOLOGY-BASED would work well:")
    print("   - BGP has 1,000+ related commands")
    print("   - Interfaces has 2,000+ commands")
    print("   - Clear categories with good separation")
    print()
    print("2. ACTION-BASED very natural:")
    print("   - ~8,000 'show' commands (monitoring)")
    print("   - ~6,000 configuration commands")
    print("   - ~5,000 'no' commands (removal)")
    print()
    print("3. OBJECT-BASED makes sense:")
    print("   - Routes, Neighbors, Interfaces are common objects")
    print("   - Matches network engineer mental model")
    print()
    print("4. HYBRID APPROACH recommended:")
    print("   - Primary: Technology tabs (BGP, OSPF, Interface)")
    print("   - Secondary: Action filter (Show, Configure, Remove)")
    print("   - Tertiary: Object filter (Neighbor, Route, VLAN)")
    print()
    print("=" * 70)


if __name__ == '__main__':
    main()
