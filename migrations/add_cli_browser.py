#!/usr/bin/env python3
"""
Database Migration: Add CLI Browser Tables
Creates 5 new tables for CLI command browser functionality
"""

import sqlite3
import sys
from pathlib import Path
from datetime import datetime


def create_cli_browser_tables(db_path='custom-cvp.db'):
    """Create CLI browser tables in the database"""
    
    print(f"[MIGRATION] Connecting to database: {db_path}")
    conn = sqlite3.connect(db_path, timeout=30.0)  # 30 second timeout
    cursor = conn.cursor()
    
    try:
        # Table 1: CLI Modes
        print("[MIGRATION] Creating cli_modes table...")
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS cli_modes (
                mode_id INTEGER PRIMARY KEY AUTOINCREMENT,
                mode_name TEXT UNIQUE NOT NULL,
                mode_category TEXT,
                parent_mode_id INTEGER,
                description TEXT,
                FOREIGN KEY (parent_mode_id) REFERENCES cli_modes(mode_id)
            )
        ''')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_cli_modes_name ON cli_modes(mode_name)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_cli_modes_category ON cli_modes(mode_category)')
        
        # Table 2: CLI Commands
        print("[MIGRATION] Creating cli_commands table...")
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS cli_commands (
                command_id INTEGER PRIMARY KEY AUTOINCREMENT,
                mode_id INTEGER NOT NULL,
                command_text TEXT NOT NULL,
                command_base TEXT NOT NULL,
                has_no_prefix BOOLEAN DEFAULT 0,
                has_default_prefix BOOLEAN DEFAULT 0,
                line_number INTEGER,
                syntax_hash TEXT,
                FOREIGN KEY (mode_id) REFERENCES cli_modes(mode_id)
            )
        ''')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_cli_commands_mode ON cli_commands(mode_id)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_cli_commands_base ON cli_commands(command_base)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_cli_commands_hash ON cli_commands(syntax_hash)')
        
        # Table 3: CLI Command Tokens
        print("[MIGRATION] Creating cli_command_tokens table...")
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS cli_command_tokens (
                token_id INTEGER PRIMARY KEY AUTOINCREMENT,
                command_id INTEGER NOT NULL,
                position INTEGER NOT NULL,
                token_type TEXT NOT NULL,
                token_value TEXT,
                is_optional BOOLEAN DEFAULT 0,
                parent_token_id INTEGER,
                FOREIGN KEY (command_id) REFERENCES cli_commands(command_id),
                FOREIGN KEY (parent_token_id) REFERENCES cli_command_tokens(token_id)
            )
        ''')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_cli_tokens_command ON cli_command_tokens(command_id)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_cli_tokens_parent ON cli_command_tokens(parent_token_id)')
        
        # Table 4: CLI Command Cache
        print("[MIGRATION] Creating cli_command_cache table...")
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS cli_command_cache (
                cache_id INTEGER PRIMARY KEY AUTOINCREMENT,
                command_prefix TEXT UNIQUE NOT NULL,
                matching_commands TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_cli_cache_prefix ON cli_command_cache(command_prefix)')
        
        # Table 5: CLI Explanations
        print("[MIGRATION] Creating cli_explanations table...")
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS cli_explanations (
                explanation_id INTEGER PRIMARY KEY AUTOINCREMENT,
                command_id INTEGER,
                command_text TEXT NOT NULL,
                explanation TEXT NOT NULL,
                source TEXT NOT NULL,
                model_name TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                created_by TEXT,
                rating INTEGER,
                FOREIGN KEY (command_id) REFERENCES cli_commands(command_id)
            )
        ''')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_cli_explanations_command ON cli_explanations(command_id)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_cli_explanations_text ON cli_explanations(command_text)')
        
        conn.commit()
        print("[MIGRATION] ✓ All tables created successfully")
        return True
        
    except Exception as e:
        print(f"[MIGRATION] ✗ Error creating tables: {e}")
        conn.rollback()
        return False
    finally:
        conn.close()


def verify_migration(db_path='custom-cvp.db'):
    """Verify that all tables were created correctly"""
    
    print("\n[VERIFICATION] Checking created tables...")
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    expected_tables = [
        'cli_modes',
        'cli_commands',
        'cli_command_tokens',
        'cli_command_cache',
        'cli_explanations'
    ]
    
    cursor.execute("""
        SELECT name FROM sqlite_master 
        WHERE type='table' AND name LIKE 'cli_%'
        ORDER BY name
    """)
    
    existing_tables = [row[0] for row in cursor.fetchall()]
    
    all_created = True
    for table in expected_tables:
        if table in existing_tables:
            # Get column count
            cursor.execute(f"PRAGMA table_info({table})")
            columns = cursor.fetchall()
            print(f"[VERIFICATION] ✓ {table} ({len(columns)} columns)")
        else:
            print(f"[VERIFICATION] ✗ {table} NOT FOUND")
            all_created = False
    
    # Get index count
    cursor.execute("""
        SELECT COUNT(*) FROM sqlite_master 
        WHERE type='index' AND name LIKE 'idx_cli_%'
    """)
    index_count = cursor.fetchone()[0]
    print(f"[VERIFICATION] ✓ {index_count} indexes created")
    
    conn.close()
    
    if all_created:
        print("[VERIFICATION] ✓ Migration completed successfully")
    else:
        print("[VERIFICATION] ✗ Migration incomplete")
    
    return all_created


def rollback_migration(db_path='custom-cvp.db'):
    """Rollback: Drop all CLI browser tables"""
    
    print("[ROLLBACK] Dropping CLI browser tables...")
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    tables = [
        'cli_explanations',
        'cli_command_cache',
        'cli_command_tokens',
        'cli_commands',
        'cli_modes'
    ]
    
    for table in tables:
        try:
            cursor.execute(f'DROP TABLE IF EXISTS {table}')
            print(f"[ROLLBACK] ✓ Dropped {table}")
        except Exception as e:
            print(f"[ROLLBACK] Error dropping {table}: {e}")
    
    conn.commit()
    conn.close()
    print("[ROLLBACK] ✓ Rollback complete")


def backup_database(db_path='custom-cvp.db'):
    """Create a backup of the database before migration"""
    
    if not Path(db_path).exists():
        print(f"[BACKUP] Database {db_path} does not exist yet")
        return None
    
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    backup_path = f"{db_path}.backup_{timestamp}"
    
    try:
        import shutil
        shutil.copy2(db_path, backup_path)
        print(f"[BACKUP] ✓ Database backed up to: {backup_path}")
        return backup_path
    except Exception as e:
        print(f"[BACKUP] ✗ Error creating backup: {e}")
        return None


if __name__ == '__main__':
    import sys
    
    # Determine database path
    if len(sys.argv) > 2:
        db_path = sys.argv[2]
    else:
        # Default path relative to script location
        script_dir = Path(__file__).parent.parent
        db_path = script_dir / 'custom-cvp.db'
    
    # Parse command
    command = sys.argv[1] if len(sys.argv) > 1 else 'migrate'
    
    if command == 'migrate':
        print("=" * 60)
        print("CLI Browser Database Migration")
        print("=" * 60)
        
        # Backup first
        backup_path = backup_database(db_path)
        
        # Run migration
        success = create_cli_browser_tables(db_path)
        
        if success:
            verify_migration(db_path)
            print("\n" + "=" * 60)
            print("Migration completed successfully!")
            print("=" * 60)
        else:
            print("\n" + "=" * 60)
            print("Migration failed! Restore from backup if needed:")
            if backup_path:
                print(f"  cp {backup_path} {db_path}")
            print("=" * 60)
            sys.exit(1)
        
    elif command == 'verify':
        verify_migration(db_path)
        
    elif command == 'rollback':
        confirm = input("Are you sure you want to rollback? (yes/no): ")
        if confirm.lower() == 'yes':
            rollback_migration(db_path)
        else:
            print("Rollback cancelled")
    
    else:
        print("Usage: python3 add_cli_browser.py [migrate|verify|rollback] [db_path]")
        print("  migrate  - Create CLI browser tables")
        print("  verify   - Verify tables exist")
        print("  rollback - Drop all CLI browser tables")
        sys.exit(1)
