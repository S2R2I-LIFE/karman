#!/usr/bin/env python3
"""
Test API endpoints directly without authentication
"""

from web.app import app
import json

app.config['TESTING'] = True

with app.test_client() as client:
    print("=" * 70)
    print("Testing API Endpoints Directly")
    print("=" * 70)

    # Login first
    print("\n1. Logging in...")
    response = client.post('/login', data={
        'username': 'admin',
        'password': 'admin'
    }, follow_redirects=False)
    print(f"   Login response: {response.status_code}")

    # Test technologies endpoint
    print("\n2. GET /api/cli/technologies")
    response = client.get('/api/cli/technologies')
    print(f"   Status: {response.status_code}")
    print(f"   Content-Type: {response.content_type}")

    if response.status_code == 200:
        data = response.get_json()
        print(f"   Technologies found: {data.get('total', 0)}")
        if data.get('technologies'):
            print(f"   First technology: {data['technologies'][0]['name']} ({data['technologies'][0]['count']} commands)")
    else:
        print(f"   Error: {response.data[:200]}")

    # Test technology commands endpoint
    print("\n3. GET /api/cli/technology/BGP")
    response = client.get('/api/cli/technology/BGP?limit=5')
    print(f"   Status: {response.status_code}")
    print(f"   Content-Type: {response.content_type}")

    if response.status_code == 200:
        data = response.get_json()
        print(f"   Commands found: {len(data.get('commands', []))}")
        if data.get('commands'):
            print(f"   First command: {data['commands'][0]['command_text'][:60]}...")
    else:
        print(f"   Error: {response.data[:200]}")

    # Test technology stats endpoint
    print("\n4. GET /api/cli/technology/BGP/stats")
    response = client.get('/api/cli/technology/BGP/stats')
    print(f"   Status: {response.status_code}")
    print(f"   Content-Type: {response.content_type}")

    if response.status_code == 200:
        data = response.get_json()
        print(f"   Actions: {list(data.get('actions', {}).keys())}")
    else:
        print(f"   Error: {response.data[:200]}")

    # Test next tokens endpoint
    print("\n5. POST /api/cli/next-tokens")
    response = client.post('/api/cli/next-tokens',
                          json={'mode': 'ConfigSessionMode', 'tokens': []},
                          content_type='application/json')
    print(f"   Status: {response.status_code}")
    print(f"   Content-Type: {response.content_type}")

    if response.status_code == 200:
        data = response.get_json()
        print(f"   Next tokens found: {data.get('count', 0)}")
    else:
        print(f"   Error: {response.data[:200]}")

    print("\n" + "=" * 70)
    print("✓ All API endpoints tested")
    print("=" * 70)
