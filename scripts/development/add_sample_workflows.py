#!/usr/bin/env python3
"""
Add sample troubleshooting workflows to demonstrate the enhanced CLI browser
"""

import sqlite3
import json

def add_bgp_neighbor_workflow(conn):
    """Add BGP neighbor troubleshooting workflow"""
    cursor = conn.cursor()

    # Create workflow
    cursor.execute("""
        INSERT INTO cli_workflows (
            title, problem_description, category, subcategory,
            severity, prerequisites, estimated_time, skill_level
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        "BGP Neighbor Not Establishing",
        "BGP neighbor relationship is stuck in Active or Idle state and not progressing to Established",
        "BGP",
        "Connectivity",
        "critical",
        json.dumps([
            "Access to router CLI",
            "BGP configured with neighbor statements",
            "Basic understanding of BGP FSM states"
        ]),
        "10-15 minutes",
        "intermediate"
    ))

    workflow_id = cursor.lastrowid

    # Add workflow steps
    steps = [
        {
            "step_number": 1,
            "step_title": "Check BGP summary status",
            "mode_name": "EnableMode",
            "command_text": "show bgp summary",
            "explanation": "First, verify the current state of all BGP neighbors to identify which neighbor(s) are not established",
            "expected_result": "Neighbor state should be 'Estab'. If showing 'Active', 'Connect', or 'Idle', there's an issue",
            "interpretation_guide": json.dumps({
                "Estab": "Neighbor is working correctly",
                "Active": "TCP connection failing - check IP reachability",
                "Idle": "BGP not trying to connect - check configuration",
                "Connect": "Initial TCP handshake - may be transient"
            })
        },
        {
            "step_number": 2,
            "step_title": "Check detailed neighbor information",
            "mode_name": "EnableMode",
            "command_text": "show bgp neighbors <neighbor_ip>",
            "explanation": "Get detailed information about the specific neighbor including last reset reason and error messages",
            "expected_result": "Look for 'BGP state' and 'Last reset' fields for clues",
            "interpretation_guide": json.dumps({
                "key_fields": [
                    "BGP state: Current FSM state",
                    "Last reset: Why the session last went down",
                    "Remote AS: Must match configuration",
                    "Hold time: Session keepalive timer"
                ]
            })
        },
        {
            "step_number": 3,
            "step_title": "Verify IP connectivity",
            "mode_name": "EnableMode",
            "command_text": "ping <neighbor_ip>",
            "explanation": "Verify basic IP connectivity to the BGP neighbor. BGP uses TCP port 179",
            "expected_result": "Ping should succeed. If it fails, there's a Layer 3 connectivity issue",
            "interpretation_guide": json.dumps({
                "success": "IP connectivity is good, issue is likely BGP-specific",
                "failure": "Fix IP routing before troubleshooting BGP further"
            })
        },
        {
            "step_number": 4,
            "step_title": "Check BGP configuration",
            "mode_name": "EnableMode",
            "command_text": "show running-config | section bgp",
            "explanation": "Verify BGP configuration including AS number, neighbor statements, and address families",
            "expected_result": "Confirm neighbor IP, remote-as, and address-family activation",
            "interpretation_guide": json.dumps({
                "common_issues": [
                    "Mismatched AS numbers",
                    "Missing 'neighbor activate' in address-family",
                    "Incorrect neighbor IP address",
                    "Missing or incorrect update-source"
                ]
            })
        },
        {
            "step_number": 5,
            "step_title": "Check for ACLs blocking BGP",
            "mode_name": "EnableMode",
            "command_text": "show ip access-lists",
            "explanation": "Verify no ACLs are blocking TCP port 179 to/from the neighbor",
            "expected_result": "No ACLs should block TCP 179 between the routers",
            "interpretation_guide": json.dumps({
                "note": "BGP uses TCP port 179. Check both inbound and outbound ACLs"
            })
        },
        {
            "step_number": 6,
            "step_title": "Check interface status",
            "mode_name": "EnableMode",
            "command_text": "show ip interface brief",
            "explanation": "Verify the interface used to reach the BGP neighbor is up/up",
            "expected_result": "Interface should show 'up/up' status",
            "interpretation_guide": json.dumps({
                "down/down": "Physical layer issue",
                "up/down": "Layer 2 protocol issue",
                "up/up": "Interface is healthy"
            })
        }
    ]

    for step in steps:
        cursor.execute("""
            INSERT INTO cli_workflow_steps (
                workflow_id, step_number, step_title, mode_name,
                command_text, explanation, expected_result, interpretation_guide
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            workflow_id,
            step["step_number"],
            step["step_title"],
            step["mode_name"],
            step["command_text"],
            step["explanation"],
            step["expected_result"],
            step["interpretation_guide"]
        ))

    print(f"✓ Added BGP neighbor troubleshooting workflow with {len(steps)} steps")

def add_interface_down_workflow(conn):
    """Add interface troubleshooting workflow"""
    cursor = conn.cursor()

    cursor.execute("""
        INSERT INTO cli_workflows (
            title, problem_description, category, subcategory,
            severity, prerequisites, estimated_time, skill_level
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        "Interface Down - Troubleshooting",
        "Physical or logical interface showing down/down or up/down status",
        "Interface",
        "Connectivity",
        "critical",
        json.dumps([
            "Physical access to device (for cable checks)",
            "Basic understanding of interface states"
        ]),
        "5-10 minutes",
        "beginner"
    ))

    workflow_id = cursor.lastrowid

    steps = [
        {
            "step_number": 1,
            "step_title": "Check interface status",
            "mode_name": "EnableMode",
            "command_text": "show interfaces status",
            "explanation": "Identify which interfaces are down and their current status",
            "expected_result": "Interfaces should show 'connected'. Look for 'notconnect', 'disabled', or 'err-disabled'",
            "interpretation_guide": json.dumps({
                "connected": "Interface is up and working",
                "notconnect": "No cable or link detected",
                "disabled": "Interface administratively shut down",
                "err-disabled": "Port security or similar feature disabled the port"
            })
        },
        {
            "step_number": 2,
            "step_title": "Check detailed interface information",
            "mode_name": "EnableMode",
            "command_text": "show interfaces <interface_name>",
            "explanation": "Get detailed information including errors, drops, and layer 1/2 status",
            "expected_result": "Check for input/output errors, CRC errors, and duplex mismatches",
            "interpretation_guide": json.dumps({
                "line_protocol_down": "Layer 2 issue (encapsulation, keepalives)",
                "administratively_down": "Interface is shut down in configuration",
                "high_errors": "Physical layer problems - cable or transceiver issue"
            })
        },
        {
            "step_number": 3,
            "step_title": "Check interface configuration",
            "mode_name": "EnableMode",
            "command_text": "show running-config interface <interface_name>",
            "explanation": "Verify interface is not administratively shut down",
            "expected_result": "Should not see 'shutdown' command. Check speed/duplex settings",
            "interpretation_guide": json.dumps({
                "shutdown_present": "Remove 'shutdown' with 'no shutdown' command",
                "speed_duplex": "Ensure settings match connected device or set to auto"
            })
        },
        {
            "step_number": 4,
            "step_title": "Check transceiver status",
            "mode_name": "EnableMode",
            "command_text": "show interfaces <interface_name> transceiver",
            "explanation": "Verify optical transceiver is properly seated and functioning",
            "expected_result": "Should show valid serial number and reasonable power levels",
            "interpretation_guide": json.dumps({
                "not_present": "Transceiver not detected - reseat or replace",
                "low_power": "Weak signal - check fiber patch cable",
                "high_temp": "Overheating transceiver - check airflow"
            })
        }
    ]

    for step in steps:
        cursor.execute("""
            INSERT INTO cli_workflow_steps (
                workflow_id, step_number, step_title, mode_name,
                command_text, explanation, expected_result, interpretation_guide
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            workflow_id,
            step["step_number"],
            step["step_title"],
            step["mode_name"],
            step["command_text"],
            step["explanation"],
            step["expected_result"],
            step["interpretation_guide"]
        ))

    print(f"✓ Added interface troubleshooting workflow with {len(steps)} steps")

def add_ospf_neighbor_workflow(conn):
    """Add OSPF neighbor troubleshooting workflow"""
    cursor = conn.cursor()

    cursor.execute("""
        INSERT INTO cli_workflows (
            title, problem_description, category, subcategory,
            severity, prerequisites, estimated_time, skill_level
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        "OSPF Neighbor Not Forming",
        "OSPF neighbor adjacency stuck in INIT or 2WAY state",
        "OSPF",
        "Connectivity",
        "warning",
        json.dumps([
            "OSPF configured on interfaces",
            "Understanding of OSPF neighbor states"
        ]),
        "10-15 minutes",
        "intermediate"
    ))

    workflow_id = cursor.lastrowid

    steps = [
        {
            "step_number": 1,
            "step_title": "Check OSPF neighbors",
            "mode_name": "EnableMode",
            "command_text": "show ip ospf neighbor",
            "explanation": "Verify current OSPF neighbor states",
            "expected_result": "Neighbors should show 'FULL' state. INIT or 2WAY indicates an issue",
            "interpretation_guide": json.dumps({
                "FULL": "Adjacency is healthy",
                "2WAY": "Hello packets exchanged but no DR/BDR election or mismatched parameters",
                "INIT": "Only receiving hellos, not seeing own router ID in neighbor's hello",
                "DOWN": "No hello packets received"
            })
        },
        {
            "step_number": 2,
            "step_title": "Check OSPF interface configuration",
            "mode_name": "EnableMode",
            "command_text": "show ip ospf interface",
            "explanation": "Verify OSPF parameters on interfaces - area, network type, timers",
            "expected_result": "Network type, area, and timers should match on both routers",
            "interpretation_guide": json.dumps({
                "network_type": "Must match (broadcast, point-to-point, etc.)",
                "area": "Must match between neighbors",
                "hello_timer": "Must match between neighbors",
                "dead_timer": "Must match between neighbors"
            })
        },
        {
            "step_number": 3,
            "step_title": "Verify IP connectivity",
            "mode_name": "EnableMode",
            "command_text": "ping <neighbor_ip>",
            "explanation": "Confirm Layer 3 connectivity to OSPF neighbor",
            "expected_result": "Ping should succeed",
            "interpretation_guide": json.dumps({
                "success": "IP connectivity good",
                "failure": "Check IP addressing and routing to neighbor"
            })
        },
        {
            "step_number": 4,
            "step_title": "Check for subnet mask mismatch",
            "mode_name": "EnableMode",
            "command_text": "show ip interface <interface>",
            "explanation": "Verify subnet masks match on both ends of link",
            "expected_result": "Subnet mask should match neighbor's mask",
            "interpretation_guide": json.dumps({
                "note": "Mismatched subnets cause OSPF neighbors to not form"
            })
        }
    ]

    for step in steps:
        cursor.execute("""
            INSERT INTO cli_workflow_steps (
                workflow_id, step_number, step_title, mode_name,
                command_text, explanation, expected_result, interpretation_guide
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            workflow_id,
            step["step_number"],
            step["step_title"],
            step["mode_name"],
            step["command_text"],
            step["explanation"],
            step["expected_result"],
            step["interpretation_guide"]
        ))

    print(f"✓ Added OSPF troubleshooting workflow with {len(steps)} steps")

def main():
    """Add sample workflows to database"""
    conn = sqlite3.connect('custom-cvp.db')

    try:
        print("Adding sample troubleshooting workflows...")
        print()

        add_bgp_neighbor_workflow(conn)
        add_interface_down_workflow(conn)
        add_ospf_neighbor_workflow(conn)

        conn.commit()

        # Show statistics
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM cli_workflows")
        workflow_count = cursor.fetchone()[0]

        cursor.execute("SELECT COUNT(*) FROM cli_workflow_steps")
        step_count = cursor.fetchone()[0]

        print()
        print("=" * 60)
        print(f"✓ Successfully added workflows")
        print(f"  Total workflows: {workflow_count}")
        print(f"  Total workflow steps: {step_count}")
        print("=" * 60)

    except Exception as e:
        print(f"Error: {e}")
        conn.rollback()
    finally:
        conn.close()

if __name__ == '__main__':
    main()
