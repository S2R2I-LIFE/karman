#!/usr/bin/env python3
"""
Diagnostic script to check why modes show no commands
Run this with web server stopped to avoid database locks
"""

import sqlite3

def check_mode(mode_name='RouterBgpBaseMode'):
    conn = sqlite3.connect('custom-cvp.db')
    cursor = conn.cursor()
    
    print(f"\n{'='*60}")
    print(f"Diagnostic Report for: {mode_name}")
    print(f"{'='*60}\n")
    
    # 1. Check if mode exists
    cursor.execute('SELECT mode_id, mode_category FROM cli_modes WHERE mode_name = ?', (mode_name,))
    mode_row = cursor.fetchone()
    
    if not mode_row:
        print(f"✗ Mode '{mode_name}' NOT FOUND in database!")
        conn.close()
        return
    
    mode_id, category = mode_row
    print(f"✓ Mode found: ID={mode_id}, Category={category}")
    
    # 2. Check commands count
    cursor.execute('SELECT COUNT(*) FROM cli_commands WHERE mode_id = ?', (mode_id,))
    cmd_count = cursor.fetchone()[0]
    print(f"✓ Total commands: {cmd_count}")
    
    if cmd_count == 0:
        print(f"✗ NO COMMANDS FOUND for this mode!")
        conn.close()
        return
    
    # 3. Check first few commands
    cursor.execute('''
        SELECT command_id, command_text
        FROM cli_commands
        WHERE mode_id = ?
        LIMIT 5
    ''', (mode_id,))
    
    print(f"\nSample commands:")
    for cmd_id, cmd_text in cursor.fetchall():
        print(f"  [{cmd_id}] {cmd_text[:70]}...")
    
    # 4. Check tokens at position 0
    cursor.execute('''
        SELECT DISTINCT t.token_type, t.token_value, COUNT(*) as cnt
        FROM cli_command_tokens t
        JOIN cli_commands c ON t.command_id = c.command_id
        WHERE c.mode_id = ? AND t.position = 0
        GROUP BY t.token_type, t.token_value
        ORDER BY cnt DESC
        LIMIT 10
    ''', (mode_id,))
    
    tokens_at_pos_0 = cursor.fetchall()
    print(f"\nTokens at position 0 (first tokens): {len(tokens_at_pos_0)} unique")
    for token_type, token_value, count in tokens_at_pos_0:
        print(f"  {token_type:12} '{token_value[:40]}' ({count} commands)")
    
    #5. Check total tokens
    cursor.execute('''
        SELECT COUNT(*)
        FROM cli_command_tokens t
        JOIN cli_commands c ON t.command_id = c.command_id
        WHERE c.mode_id = ?
    ''', (mode_id,))
    total_tokens = cursor.fetchone()[0]
    print(f"\nTotal tokens for this mode: {total_tokens}")
    
    # 6. Test progressive disclosure query (same as in navigator)
    cursor.execute('''
        SELECT DISTINCT t.token_type, t.token_value, t.is_optional
        FROM cli_command_tokens t
        JOIN cli_commands c ON t.command_id = c.command_id
        WHERE c.mode_id = ? AND t.position = 0
    ''', (mode_id,))
    
    progressive_tokens = cursor.fetchall()
    print(f"\nProgressive disclosure would return: {len(progressive_tokens)} tokens")
    
    if len(progressive_tokens) == 0:
        print("✗ PROBLEM: Progressive disclosure query returns 0 tokens!")
        print("   This explains why the UI shows nothing.")
    else:
        print("✓ Progressive disclosure should work correctly")
    
    conn.close()
    print(f"\n{'='*60}\n")


if __name__ == '__main__':
    # Test several modes
    import sys
    
    modes_to_test = [
        'RouterBgpBaseMode',
        'ConfigSessionMode',
        'IntfConfigMode',
        'EnableMode'
    ]
    
    for mode in modes_to_test:
        check_mode(mode)
        
    print("\nTo fix issues:")
    print("1. If tokens at position 0 = 0, the parser may have failed")
    print("2. Re-run: python3 setup_cli_browser.py")
