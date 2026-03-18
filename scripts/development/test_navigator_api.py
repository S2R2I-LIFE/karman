#!/usr/bin/env python3
"""
Test the CLI navigator API to see what token format it returns
"""

from core.cli_navigator import CLINavigator
import json

navigator = CLINavigator('custom-cvp.db')

# Test getting first tokens for ConfigSessionMode
print("=" * 70)
print("TEST: Get first tokens for ConfigSessionMode")
print("=" * 70)

tokens = navigator.get_next_tokens('ConfigSessionMode', [])
print(f"\nFound {len(tokens)} first tokens")
print("\nFirst 5 tokens:")

for token in tokens[:5]:
    print(f"\nToken:")
    print(f"  token_type: {token.token_type}")
    print(f"  token_value: {token.token_value}")
    print(f"  is_optional: {token.is_optional}")
    print(f"  choices: {token.choices}")
    print(f"  description: {token.description}")

    # Show what to_dict() returns (this is what the API sends)
    print(f"  to_dict(): {token.to_dict()}")

print("\n" + "=" * 70)
print("TEST: Get tokens after 'interface'")
print("=" * 70)

tokens = navigator.get_next_tokens('ConfigSessionMode', ['interface'])
print(f"\nFound {len(tokens)} next tokens")
print("\nFirst 5 tokens:")

for token in tokens[:5]:
    print(f"\nToken:")
    print(f"  token_type: {token.token_type}")
    print(f"  token_value: {token.token_value}")
    print(f"  to_dict(): {token.to_dict()}")

print("\n" + "=" * 70)
print("JSON format (what API returns):")
print("=" * 70)

# Simulate what the API returns
tokens = navigator.get_next_tokens('ConfigSessionMode', [])
api_response = {
    'mode': 'ConfigSessionMode',
    'current_tokens': [],
    'next_tokens': [token.to_dict() for token in tokens[:3]],
    'count': len(tokens)
}

print(json.dumps(api_response, indent=2))
