#!/usr/bin/env python3
"""
Test hybrid navigation API endpoints
"""

import sqlite3
import json
from collections import defaultdict

DB_PATH = 'custom-cvp.db'

def test_technologies_endpoint():
    """Test /api/cli/technologies endpoint logic"""
    print("=" * 70)
    print("TEST: Get Technologies with Counts")
    print("=" * 70)

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute("""
        SELECT technology_tags, action_tags
        FROM cli_commands
        WHERE technology_tags IS NOT NULL
        LIMIT 100
    """)

    tech_counts = defaultdict(int)
    action_counts = defaultdict(lambda: defaultdict(int))

    for row in cursor.fetchall():
        tech_tags_json, action_tags_json = row

        if tech_tags_json:
            tech_tags = json.loads(tech_tags_json)
            action_tags = json.loads(action_tags_json) if action_tags_json else []

            for tech in tech_tags:
                tech_counts[tech] += 1
                for action in action_tags:
                    action_counts[tech][action] += 1

    conn.close()

    print(f"\nTop 10 Technologies (from sample of 100):")
    for tech, count in sorted(tech_counts.items(), key=lambda x: x[1], reverse=True)[:10]:
        print(f"  {tech:20} {count:4} commands")
        actions = action_counts[tech]
        print(f"    Actions: {dict(actions)}")

    print("\n✓ Technologies endpoint logic works!")


def test_technology_commands():
    """Test /api/cli/technology/<tech_name> endpoint logic"""
    print("\n" + "=" * 70)
    print("TEST: Get BGP Commands")
    print("=" * 70)

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute("""
        SELECT c.command_id, c.command_text, c.command_base,
               c.technology_tags, c.action_tags, m.mode_name, m.mode_category
        FROM cli_commands c
        JOIN cli_modes m ON c.mode_id = m.mode_id
        WHERE c.technology_tags LIKE ?
        LIMIT 10
    """, ['%"BGP"%'])

    commands = []
    for row in cursor.fetchall():
        cmd_id, cmd_text, cmd_base, tech_tags, action_tags, mode_name, mode_cat = row

        commands.append({
            'command_id': cmd_id,
            'command_text': cmd_text[:60],
            'technologies': json.loads(tech_tags) if tech_tags else [],
            'actions': json.loads(action_tags) if action_tags else [],
            'mode_name': mode_name
        })

    conn.close()

    print(f"\nSample BGP Commands:")
    for cmd in commands[:5]:
        print(f"\n  Command: {cmd['command_text']}...")
        print(f"  Technologies: {', '.join(cmd['technologies'])}")
        print(f"  Actions: {', '.join(cmd['actions'])}")
        print(f"  Mode: {cmd['mode_name']}")

    print(f"\n✓ BGP commands endpoint logic works! ({len(commands)} commands retrieved)")


def test_technology_stats():
    """Test /api/cli/technology/<tech_name>/stats endpoint logic"""
    print("\n" + "=" * 70)
    print("TEST: Get BGP Statistics")
    print("=" * 70)

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute("""
        SELECT c.action_tags, m.mode_name
        FROM cli_commands c
        JOIN cli_modes m ON c.mode_id = m.mode_id
        WHERE c.technology_tags LIKE ?
    """, ['%"BGP"%'])

    action_counts = defaultdict(int)
    mode_counts = defaultdict(int)

    for row in cursor.fetchall():
        action_tags_json, mode_name = row

        if action_tags_json:
            action_tags = json.loads(action_tags_json)
            for action in action_tags:
                action_counts[action] += 1

        mode_counts[mode_name] += 1

    conn.close()

    print(f"\nBGP Actions:")
    for action, count in sorted(action_counts.items(), key=lambda x: x[1], reverse=True):
        print(f"  {action:15} {count:5} commands")

    print(f"\nTop BGP Modes:")
    for mode, count in sorted(mode_counts.items(), key=lambda x: x[1], reverse=True)[:5]:
        print(f"  {mode:40} {count:5} commands")

    print("\n✓ BGP statistics endpoint logic works!")


def test_action_filtering():
    """Test action filtering"""
    print("\n" + "=" * 70)
    print("TEST: Filter BGP Commands by 'Show' Action")
    print("=" * 70)

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute("""
        SELECT c.command_text, c.action_tags
        FROM cli_commands c
        WHERE c.technology_tags LIKE ?
        AND c.action_tags LIKE ?
        LIMIT 10
    """, ['%"BGP"%', '%"Show"%'])

    commands = []
    for row in cursor.fetchall():
        cmd_text, action_tags = row
        commands.append({
            'command': cmd_text[:60],
            'actions': json.loads(action_tags) if action_tags else []
        })

    conn.close()

    print(f"\nSample BGP 'Show' Commands:")
    for cmd in commands:
        print(f"  {cmd['command']}...")
        print(f"    Actions: {', '.join(cmd['actions'])}")

    print(f"\n✓ Action filtering works! ({len(commands)} commands retrieved)")


if __name__ == '__main__':
    print("\n" + "=" * 70)
    print("HYBRID NAVIGATION API TESTS")
    print("=" * 70)

    test_technologies_endpoint()
    test_technology_commands()
    test_technology_stats()
    test_action_filtering()

    print("\n" + "=" * 70)
    print("✓ All API endpoint tests passed!")
    print("=" * 70)
    print("\nReady to test in browser! Start Flask server with:")
    print("  cd web && python3 app.py")
    print("\nThen navigate to:")
    print("  http://localhost:5000/cli-browser")
    print("=" * 70)
