#!/usr/bin/env python3
"""
Database migration runner
Applies SQL migrations to the database
"""

import sqlite3
import sys
from pathlib import Path

def run_migration(db_path, migration_file):
    """Run a SQL migration file"""
    print(f"Running migration: {migration_file}")

    # Read migration SQL
    with open(migration_file, 'r') as f:
        sql = f.read()

    # Connect and execute
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    try:
        # Enable foreign keys
        cursor.execute('PRAGMA foreign_keys = ON')

        # Execute migration (split by semicolon for multiple statements)
        cursor.executescript(sql)

        conn.commit()

        # Get status
        cursor.execute("SELECT COUNT(*) FROM cli_command_docs")
        doc_count = cursor.fetchone()[0]

        cursor.execute("SELECT COUNT(*) FROM cli_parameter_docs")
        param_count = cursor.fetchone()[0]

        cursor.execute("SELECT COUNT(*) FROM cli_workflows")
        workflow_count = cursor.fetchone()[0]

        print(f"✓ Migration completed successfully!")
        print(f"  - Command documentation entries: {doc_count}")
        print(f"  - Parameter documentation entries: {param_count}")
        print(f"  - Workflow entries: {workflow_count}")

        # Verify new tables exist
        cursor.execute("""
            SELECT name FROM sqlite_master
            WHERE type='table' AND name LIKE 'cli_%'
            ORDER BY name
        """)
        tables = [row[0] for row in cursor.fetchall()]
        print(f"\n✓ Available tables: {len(tables)}")
        for table in tables:
            if table not in ['cli_modes', 'cli_commands', 'cli_command_tokens',
                            'cli_command_cache', 'cli_explanations']:
                print(f"  [NEW] {table}")
            else:
                print(f"  [EXISTING] {table}")

    except Exception as e:
        conn.rollback()
        print(f"✗ Migration failed: {e}")
        sys.exit(1)
    finally:
        conn.close()

if __name__ == '__main__':
    db_path = 'custom-cvp.db'
    migration_file = 'migrations/add_documentation_tables.sql'

    if not Path(db_path).exists():
        print(f"Error: Database not found at {db_path}")
        sys.exit(1)

    if not Path(migration_file).exists():
        print(f"Error: Migration file not found at {migration_file}")
        sys.exit(1)

    run_migration(db_path, migration_file)
