#!/usr/bin/env python3
"""
Quick test of progressive disclosure fix
Tests that modes now return next tokens correctly
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

from core.cli_navigator import CLINavigator

def test_modes():
    """Test several modes to verify they work"""
    
    nav = CLINavigator('custom-cvp.db')
    
    test_modes = [
        'ConfigSessionMode',
        'RouterBgpBaseMode',
        'IntfConfigMode',
        'RouterOspfMode',
        'VlanMode'
    ]
    
    print("Testing Progressive Disclosure Fix")
    print("=" * 60)
    
    for mode in test_modes:
        try:
            tokens = nav.get_next_tokens(mode, [])
            print(f"\n{mode}:")
            print(f"  ✓ Found {len(tokens)} first tokens")
            
            if len(tokens) > 0:
                # Show first few
                for token in tokens[:5]:
                    print(f"    - {token.token_type}: {token.token_value}")
            else:
                print("  ✗ NO TOKENS FOUND (This is a problem!)")
                
        except Exception as e:
            print(f"\n{mode}:")
            print(f"  ✗ ERROR: {e}")
    
    print("\n" + "=" * 60)
    print("Test Complete")

if __name__ == '__main__':
    test_modes()
