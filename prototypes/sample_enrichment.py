#!/usr/bin/env python3
"""
Sample script showing how to enrich CLI commands with educational content
This demonstrates the data structure we'd need for a truly useful CLI browser
"""

import json

# Sample enriched command data structure
SAMPLE_ENRICHED_COMMANDS = [
    {
        "command_id": 1,
        "mode": "RouterBgpBaseMode",
        "command_text": "[no|default] address-family ipv4 unicast",
        "command_base": "address-family",

        # ENRICHMENT DATA:
        "documentation": {
            "short_description": "Enter BGP IPv4 unicast address family configuration mode",

            "long_description": """
                The address-family command enters BGP address family configuration mode,
                allowing you to configure routing policies, neighbors, and network
                advertisements specific to the IPv4 unicast address family. This separates
                IPv4 configuration from other address families like IPv6 or EVPN.
            """,

            "when_to_use": [
                "Configuring basic IPv4 BGP routing",
                "Activating neighbors in the IPv4 address family",
                "Applying route-maps or prefix-lists to IPv4 routes",
                "Configuring network statements for IPv4 prefixes",
                "Setting up route redistribution for IPv4"
            ],

            "privilege_level": 15,
            "requires_config_mode": True,
            "tags": ["BGP", "Routing", "IPv4", "Configuration", "Address Family"]
        },

        "parameters": [
            {
                "name": "no",
                "description": "Remove the address family configuration",
                "optional": True,
                "type": "prefix"
            },
            {
                "name": "default",
                "description": "Reset address family to default configuration",
                "optional": True,
                "type": "prefix"
            },
            {
                "name": "ipv4 unicast",
                "description": "IPv4 unicast address family",
                "type": "keyword",
                "alternatives": ["ipv6 unicast", "evpn", "vpnv4", "vpnv6"]
            }
        ],

        "examples": [
            {
                "scenario": "Basic IPv4 BGP configuration",
                "difficulty": "beginner",
                "workflow": [
                    {
                        "step": 1,
                        "command": "enable",
                        "mode": "UnprivMode → EnableMode",
                        "explanation": "Enter privileged exec mode"
                    },
                    {
                        "step": 2,
                        "command": "configure terminal",
                        "mode": "EnableMode → ConfigSessionMode",
                        "explanation": "Enter global configuration mode"
                    },
                    {
                        "step": 3,
                        "command": "router bgp 65000",
                        "mode": "ConfigSessionMode → RouterBgpBaseMode",
                        "explanation": "Enter BGP configuration mode for AS 65000"
                    },
                    {
                        "step": 4,
                        "command": "address-family ipv4 unicast",
                        "mode": "RouterBgpBaseMode → RouterBgpBaseAfIpUniMode",
                        "explanation": "Enter IPv4 unicast address family mode"
                    },
                    {
                        "step": 5,
                        "command": "network 10.0.0.0/8",
                        "explanation": "Advertise 10.0.0.0/8 network in BGP"
                    },
                    {
                        "step": 6,
                        "command": "neighbor 192.168.1.1 activate",
                        "explanation": "Activate neighbor in IPv4 address family"
                    }
                ],
                "expected_output": """
Router(config)# router bgp 65000
Router(config-router)# address-family ipv4 unicast
Router(config-router-af)# network 10.0.0.0/8
Router(config-router-af)# neighbor 192.168.1.1 activate
                """,
                "verification_commands": [
                    "show bgp ipv4 unicast summary",
                    "show running-config | section bgp"
                ]
            },
            {
                "scenario": "EVPN data center fabric",
                "difficulty": "advanced",
                "workflow": [
                    {
                        "step": 1,
                        "command": "router bgp 65100",
                        "explanation": "Enter BGP for spine AS"
                    },
                    {
                        "step": 2,
                        "command": "address-family evpn",
                        "explanation": "Configure EVPN address family for VXLAN"
                    },
                    {
                        "step": 3,
                        "command": "neighbor OVERLAY peer group",
                        "explanation": "Create peer group for EVPN neighbors"
                    }
                ]
            }
        ],

        "related_commands": [
            {
                "command": "router bgp",
                "relationship": "parent",
                "description": "Must enter BGP mode before address-family"
            },
            {
                "command": "neighbor activate",
                "relationship": "commonly_used_with",
                "description": "Activate neighbors within this address family"
            },
            {
                "command": "network",
                "relationship": "commonly_used_with",
                "description": "Advertise networks in this address family"
            },
            {
                "command": "show bgp ipv4 unicast summary",
                "relationship": "verification",
                "description": "Verify IPv4 unicast BGP status"
            }
        ],

        "warnings": [
            {
                "severity": "warning",
                "type": "session_disruption",
                "message": "Changes to address family may require clearing BGP sessions",
                "mitigation": "Use 'clear bgp ipv4 unicast soft' to avoid hard reset"
            },
            {
                "severity": "info",
                "type": "requirement",
                "message": "Neighbors must be explicitly activated in each address family",
                "mitigation": "Remember to use 'neighbor X.X.X.X activate' command"
            }
        ],

        "troubleshooting": {
            "common_issues": [
                {
                    "symptom": "Neighbor not receiving routes",
                    "likely_cause": "Neighbor not activated in address family",
                    "solution": "Use 'neighbor X.X.X.X activate' command",
                    "verification": "show bgp ipv4 unicast neighbors X.X.X.X"
                },
                {
                    "symptom": "Routes not being advertised",
                    "likely_cause": "Network statement missing or route-map filtering",
                    "solution": "Check network statements and route-map configuration",
                    "verification": "show bgp ipv4 unicast | include Network"
                }
            ]
        }
    },

    {
        "command_id": 2,
        "mode": "EnableMode",
        "command_text": "show bgp summary",
        "command_base": "show",

        "documentation": {
            "short_description": "Display summary of all BGP neighbor sessions",

            "long_description": """
                Shows a concise summary of all BGP neighbor relationships including
                neighbor IP, AS number, message counts, uptime, and current state.
                This is typically the first command used when troubleshooting BGP.
            """,

            "when_to_use": [
                "Quick health check of all BGP neighbors",
                "Identify which neighbors are down or flapping",
                "Verify BGP configuration after changes",
                "Troubleshooting BGP connectivity issues",
                "Monitoring BGP neighbor stability"
            ],

            "privilege_level": 1,
            "requires_config_mode": False,
            "tags": ["BGP", "Show", "Troubleshooting", "Monitoring"]
        },

        "output_example": """
BGP summary information for VRF default
Router identifier 10.0.0.1, local AS number 65000
Neighbor Status Codes: m - Under maintenance
  Neighbor         V  AS           MsgRcvd   MsgSent  InQ OutQ  Up/Down State   PfxRcd PfxAcc
  192.168.1.1      4  65001            234       231    0    0 01:23:45 Estab   150    150
  192.168.1.2      4  65001            456       452    0    0 02:15:20 Estab   150    150
  192.168.2.1      4  65002            0         0      0    0 00:00:00 Active  0      0
        """,

        "output_interpretation": {
            "columns": [
                {
                    "name": "Neighbor",
                    "description": "IP address of BGP neighbor"
                },
                {
                    "name": "V",
                    "description": "BGP version (4 = BGP4)"
                },
                {
                    "name": "AS",
                    "description": "Neighbor's AS number"
                },
                {
                    "name": "MsgRcvd/MsgSent",
                    "description": "BGP message counters"
                },
                {
                    "name": "State",
                    "description": "BGP FSM state (Estab = established, Active = trying to connect)",
                    "healthy_values": ["Estab"],
                    "warning_values": ["Active", "Connect"],
                    "error_values": ["Idle"]
                },
                {
                    "name": "PfxRcd",
                    "description": "Number of prefixes received from neighbor",
                    "note": "0 may indicate filtering or no routes advertised"
                }
            ]
        },

        "related_commands": [
            {
                "command": "show bgp neighbors",
                "relationship": "detailed_version",
                "description": "More detailed neighbor information"
            },
            {
                "command": "show bgp ipv4 unicast",
                "relationship": "show_routes",
                "description": "Display actual BGP routes received"
            }
        ],

        "troubleshooting_decision_tree": {
            "if_neighbor_state_active": [
                "Check IP connectivity: ping neighbor_ip",
                "Verify BGP configuration: show running-config | section bgp",
                "Check neighbor details: show bgp neighbors <IP>",
                "Look for ACLs blocking TCP 179"
            ],
            "if_neighbor_state_idle": [
                "Check if neighbor is configured",
                "Verify AS number matches neighbor configuration",
                "Check for 'shutdown' under neighbor config"
            ],
            "if_pfxrcd_is_zero": [
                "Verify neighbor is sending routes",
                "Check for route-map filtering: show route-map",
                "Verify address-family activation"
            ]
        }
    }
]


def display_enriched_command(cmd_data):
    """Pretty print enriched command data"""
    print("=" * 80)
    print(f"Command: {cmd_data['command_text']}")
    print(f"Mode: {cmd_data['mode']}")
    print("=" * 80)

    doc = cmd_data['documentation']
    print(f"\n📖 {doc['short_description']}")
    print(f"\n{doc['long_description'].strip()}")

    print("\n💡 When to use:")
    for use_case in doc['when_to_use']:
        print(f"  • {use_case}")

    if 'parameters' in cmd_data:
        print("\n📋 Parameters:")
        for param in cmd_data['parameters']:
            opt = " (optional)" if param.get('optional') else ""
            print(f"  • {param['name']}{opt}: {param['description']}")

    if 'examples' in cmd_data:
        print("\n📝 Example Scenarios:")
        for ex in cmd_data['examples']:
            print(f"\n  Scenario: {ex['scenario']} [{ex['difficulty']}]")
            print(f"  Workflow:")
            for step in ex['workflow'][:3]:  # Show first 3 steps
                print(f"    {step['step']}. {step['command']}")
                print(f"       → {step['explanation']}")

    if 'output_example' in cmd_data:
        print("\n💻 Example Output:")
        print(cmd_data['output_example'])

    if 'related_commands' in cmd_data:
        print("\n🔗 Related Commands:")
        for rel in cmd_data['related_commands']:
            print(f"  • {rel['command']} - {rel['description']}")

    if 'warnings' in cmd_data:
        print("\n⚠️  Important Notes:")
        for warn in cmd_data['warnings']:
            severity_icon = "🔴" if warn['severity'] == 'critical' else "⚡"
            print(f"  {severity_icon} {warn['message']}")

    print("\n" + "=" * 80)


if __name__ == '__main__':
    print("\n" + "=" * 80)
    print("CLI BROWSER ENRICHMENT - SAMPLE DATA DEMONSTRATION")
    print("=" * 80)
    print("\nThis shows how enriched command data provides educational value\n")

    # Display enriched commands
    for cmd in SAMPLE_ENRICHED_COMMANDS:
        display_enriched_command(cmd)
        print("\n")

    # Show JSON structure
    print("\n" + "=" * 80)
    print("SAMPLE JSON STRUCTURE")
    print("=" * 80)
    print("\nThis is the data structure we'd store in the enhanced database:\n")
    print(json.dumps(SAMPLE_ENRICHED_COMMANDS[0], indent=2))

    print("\n" + "=" * 80)
    print("NEXT STEPS")
    print("=" * 80)
    print("""
1. Extend database schema with new tables (see ENHANCEMENT_PROPOSAL.md)
2. Create AI enrichment pipeline to generate initial documentation
3. Build web UI for human review and enhancement
4. Implement workflow-based navigation
5. Add interactive troubleshooting wizard

This transforms the CLI browser from a command list into an
educational platform that actually helps engineers solve problems.
    """)
