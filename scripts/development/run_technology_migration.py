#!/usr/bin/env python3
"""
Run technology tags migration
"""

import sqlite3
import sys

def run_migration(db_path='custom-cvp.db', sql_file='migrations/add_technology_tags.sql'):
    """Execute the technology tags migration"""
    try:
        # Read the SQL file
        with open(sql_file, 'r') as f:
            sql_script = f.read()

        # Connect to database
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        # Execute the migration
        print("Running technology tags migration...")
        cursor.executescript(sql_script)
        conn.commit()

        # Verify columns were added
        cursor.execute("PRAGMA table_info(cli_commands)")
        columns = cursor.fetchall()

        has_tech_tags = any(col[1] == 'technology_tags' for col in columns)
        has_action_tags = any(col[1] == 'action_tags' for col in columns)

        print("\nMigration completed successfully!")
        print(f"✓ technology_tags column: {'Added' if has_tech_tags else 'Failed'}")
        print(f"✓ action_tags column: {'Added' if has_action_tags else 'Failed'}")

        conn.close()

        return has_tech_tags and has_action_tags

    except Exception as e:
        print(f"Error running migration: {e}")
        sys.exit(1)

if __name__ == '__main__':
    success = run_migration()
    if not success:
        print("\nMigration verification failed!")
        sys.exit(1)
    else:
        print("\nReady to tag commands with technology categories!")
