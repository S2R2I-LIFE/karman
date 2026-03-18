#!/usr/bin/env python3
"""
Add missing commands from showcli.txt to database
Adds only specific commands that were confirmed missing
"""

import sys
import sqlite3
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

from core.cli_parser import CLIParser

def add_missing_commands():
    """Add the 4 confirmed missing commands"""

    # The 4 commands missing from database (line numbers from showcli.txt)
    missing_line_numbers = [6860, 8976, 9695, 11577]

    db_path = 'custom-cvp.db'
    showcli_path = 'showcli.txt'

    print("=" * 70)
    print("Adding Missing Commands to Database")
    print("=" * 70)

    # Read showcli.txt
    with open(showcli_path, 'r', encoding='utf-8') as f:
        lines = f.readlines()

    print(f"✓ Read showcli.txt ({len(lines)} lines)")

    # Initialize parser
    parser = CLIParser(db_path)

    # Parse only the missing lines
    commands_to_add = []
    for line_num in missing_line_numbers:
        line = lines[line_num - 1]  # Convert to 0-indexed
        parsed = parser.parse_line(line, line_num)

        if parsed:
            commands_to_add.append(parsed)
            print(f"✓ Parsed line {line_num}: {parsed.command_text[:60]}...")
        else:
            print(f"✗ Failed to parse line {line_num}: {line.strip()}")

    if not commands_to_add:
        print("\n✗ No commands to add")
        return False

    # Connect to database
    print(f"\n[DB] Connecting to {db_path}...")
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    try:
        added_count = 0

        for cmd in commands_to_add:
            # Get or create mode
            cursor.execute('SELECT mode_id FROM cli_modes WHERE mode_name = ?', (cmd.mode,))
            result = cursor.fetchone()

            if result:
                mode_id = result[0]
            else:
                # Create mode if it doesn't exist
                category = parser._categorize_mode(cmd.mode)
                cursor.execute('''
                    INSERT INTO cli_modes (mode_name, mode_category, description)
                    VALUES (?, ?, ?)
                ''', (cmd.mode, category, f"Auto-detected {category} mode"))
                mode_id = cursor.lastrowid
                print(f"[DB] Created new mode: {cmd.mode}")

            # Check if command already exists (safety check)
            cursor.execute('''
                SELECT command_id FROM cli_commands
                WHERE mode_id = ? AND command_text = ?
            ''', (mode_id, cmd.command_text))

            if cursor.fetchone():
                print(f"[DB] Command already exists, skipping: {cmd.command_text[:60]}...")
                continue

            # Insert command
            cursor.execute('''
                INSERT INTO cli_commands
                (mode_id, command_text, command_base, has_no_prefix,
                 has_default_prefix, line_number, syntax_hash)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            ''', (mode_id, cmd.command_text, cmd.command_base,
                  cmd.has_no_prefix, cmd.has_default_prefix,
                  cmd.line_number, cmd.syntax_hash))

            command_id = cursor.lastrowid

            # Insert tokens
            for token in cmd.tokens:
                cursor.execute('''
                    INSERT INTO cli_command_tokens
                    (command_id, position, token_type, token_value,
                     is_optional, parent_token_id)
                    VALUES (?, ?, ?, ?, ?, ?)
                ''', (command_id, token.position, token.token_type,
                      token.token_value, token.is_optional, token.parent_id))

            added_count += 1
            print(f"[DB] ✓ Added: {cmd.command_text[:60]}...")

        conn.commit()

        print("\n" + "=" * 70)
        print(f"✓ Successfully added {added_count} commands")
        print("=" * 70)

        # Verify
        cursor.execute('SELECT COUNT(*) FROM cli_commands')
        total = cursor.fetchone()[0]
        print(f"Total commands in database: {total:,}")

        return True

    except Exception as e:
        print(f"\n✗ Error: {e}")
        import traceback
        traceback.print_exc()
        conn.rollback()
        return False

    finally:
        conn.close()


if __name__ == '__main__':
    success = add_missing_commands()
    sys.exit(0 if success else 1)
