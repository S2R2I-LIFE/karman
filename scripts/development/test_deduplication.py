#!/usr/bin/env python3
"""
Test that deduplication is working
"""

from web.app import app

app.config['TESTING'] = True

with app.test_client() as client:
    # Login first
    client.post('/login', data={'username': 'admin', 'password': 'admin'})

    print("=" * 70)
    print("Testing Command Deduplication")
    print("=" * 70)

    # Test System commands (known to have many duplicates)
    print("\n1. System commands (limit 20):")
    response = client.get('/api/cli/technology/System?limit=20')
    data = response.get_json()

    commands = data.get('commands', [])
    print(f"   Returned: {len(commands)} commands")

    # Check for duplicates
    seen = set()
    duplicates = []
    for cmd in commands:
        key = f"{cmd['command_text']}|{cmd['mode_name']}"
        if key in seen:
            duplicates.append(cmd['command_text'][:50])
        seen.add(key)

    if duplicates:
        print(f"   ❌ Found {len(duplicates)} duplicates:")
        for dup in duplicates:
            print(f"      - {dup}...")
    else:
        print("   ✓ No duplicates found!")

    # Show first 5 commands
    print("\n   First 5 commands:")
    for i, cmd in enumerate(commands[:5], 1):
        print(f"   {i}. {cmd['command_text'][:60]}... ({cmd['mode_name']})")

    # Test BGP commands
    print("\n2. BGP commands (limit 30):")
    response = client.get('/api/cli/technology/BGP?limit=30')
    data = response.get_json()

    commands = data.get('commands', [])
    print(f"   Returned: {len(commands)} commands")

    seen = set()
    duplicates = []
    for cmd in commands:
        key = f"{cmd['command_text']}|{cmd['mode_name']}"
        if key in seen:
            duplicates.append((cmd['command_text'][:50], cmd['mode_name']))
        seen.add(key)

    if duplicates:
        print(f"   ❌ Found {len(duplicates)} duplicates:")
        for dup_cmd, mode in duplicates:
            print(f"      - {dup_cmd}... in {mode}")
    else:
        print("   ✓ No duplicates found!")

    print("\n" + "=" * 70)
    print("✓ Deduplication test complete")
    print("=" * 70)
