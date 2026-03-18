#!/usr/bin/env python3
"""
Database migration to add user authentication tables
Creates: users, access_requests, notification_queue, email_log, auth_audit_log, user_sessions
"""

import sqlite3
import sys
import shutil
from pathlib import Path
from datetime import datetime


def backup_database(db_path):
    """Create a backup of the database before migration"""
    if not Path(db_path).exists():
        print(f"Database {db_path} does not exist, skipping backup")
        return None

    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    backup_path = f"{db_path}.backup_{timestamp}"

    print(f"Creating backup: {backup_path}")
    shutil.copy2(db_path, backup_path)
    print(f"Backup created successfully")

    return backup_path


def create_user_auth_tables(db_path='custom-cvp.db'):
    """Create all user authentication tables"""
    print(f"Starting migration on {db_path}")

    conn = sqlite3.connect(db_path, timeout=30.0)
    cursor = conn.cursor()

    try:
        # Check if tables already exist
        cursor.execute("""
            SELECT name FROM sqlite_master
            WHERE type='table' AND name='users'
        """)

        if cursor.fetchone():
            print("Migration already applied (users table exists), skipping...")
            conn.close()
            return True

        print("Creating users table...")
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                email TEXT UNIQUE NOT NULL,
                full_name TEXT NOT NULL,
                password_hash TEXT NOT NULL,
                is_admin INTEGER DEFAULT 0,
                is_active INTEGER DEFAULT 0,
                created_at TEXT NOT NULL,
                approved_at TEXT,
                approved_by TEXT,
                last_login TEXT,
                failed_login_attempts INTEGER DEFAULT 0,
                account_locked_until TEXT,
                CONSTRAINT username_length CHECK (length(username) >= 3),
                CONSTRAINT email_format CHECK (email LIKE '%@%')
            )
        ''')

        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_users_username ON users(username)
        ''')

        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_users_email ON users(email)
        ''')

        print("Creating access_requests table...")
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS access_requests (
                request_id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                email TEXT UNIQUE NOT NULL,
                full_name TEXT NOT NULL,
                password_hash TEXT NOT NULL,
                reason TEXT NOT NULL,
                requested_at TEXT NOT NULL,
                status TEXT DEFAULT 'pending',
                reviewed_at TEXT,
                reviewed_by TEXT,
                rejection_reason TEXT,
                CONSTRAINT status_values CHECK (status IN ('pending', 'approved', 'rejected'))
            )
        ''')

        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_access_requests_status ON access_requests(status)
        ''')

        print("Creating notification_queue table...")
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS notification_queue (
                notification_id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                notification_type TEXT NOT NULL,
                title TEXT NOT NULL,
                message TEXT NOT NULL,
                related_id INTEGER,
                is_read INTEGER DEFAULT 0,
                created_at TEXT NOT NULL,
                read_at TEXT,
                FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE
            )
        ''')

        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_notifications_user_id ON notification_queue(user_id)
        ''')

        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_notifications_is_read ON notification_queue(is_read)
        ''')

        print("Creating email_log table...")
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS email_log (
                log_id INTEGER PRIMARY KEY AUTOINCREMENT,
                recipient_email TEXT NOT NULL,
                subject TEXT NOT NULL,
                email_type TEXT NOT NULL,
                sent_at TEXT NOT NULL,
                success INTEGER DEFAULT 1,
                error_message TEXT,
                related_request_id INTEGER,
                FOREIGN KEY (related_request_id) REFERENCES access_requests(request_id)
            )
        ''')

        print("Creating auth_audit_log table...")
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS auth_audit_log (
                log_id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                event_type TEXT NOT NULL,
                username TEXT NOT NULL,
                ip_address TEXT,
                details TEXT,
                success INTEGER DEFAULT 1
            )
        ''')

        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_audit_log_username ON auth_audit_log(username)
        ''')

        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_audit_log_timestamp ON auth_audit_log(timestamp)
        ''')

        print("Creating user_sessions table...")
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS user_sessions (
                session_id TEXT PRIMARY KEY,
                user_id INTEGER NOT NULL,
                ip_address TEXT,
                user_agent TEXT,
                created_at TEXT NOT NULL,
                last_activity TEXT NOT NULL,
                expires_at TEXT NOT NULL,
                FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE
            )
        ''')

        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_sessions_user_id ON user_sessions(user_id)
        ''')

        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_sessions_expires_at ON user_sessions(expires_at)
        ''')

        conn.commit()
        print("✓ Migration completed successfully")
        print("\nCreated tables:")
        print("  - users (with indexes on username, email)")
        print("  - access_requests (with index on status)")
        print("  - notification_queue (with indexes on user_id, is_read)")
        print("  - email_log")
        print("  - auth_audit_log (with indexes on username, timestamp)")
        print("  - user_sessions (with indexes on user_id, expires_at)")

        return True

    except Exception as e:
        print(f"✗ Migration failed: {str(e)}")
        conn.rollback()
        return False

    finally:
        conn.close()


def verify_migration(db_path='custom-cvp.db'):
    """Verify that all tables were created correctly"""
    print("\nVerifying migration...")

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    expected_tables = [
        'users',
        'access_requests',
        'notification_queue',
        'email_log',
        'auth_audit_log',
        'user_sessions'
    ]

    cursor.execute("""
        SELECT name FROM sqlite_master
        WHERE type='table'
        ORDER BY name
    """)

    existing_tables = [row[0] for row in cursor.fetchall()]

    all_present = True
    for table in expected_tables:
        if table in existing_tables:
            print(f"  ✓ {table}")
        else:
            print(f"  ✗ {table} - MISSING")
            all_present = False

    conn.close()

    if all_present:
        print("\n✓ All tables verified successfully")
    else:
        print("\n✗ Some tables are missing")

    return all_present


def rollback_migration(db_path, backup_path):
    """Rollback migration by restoring from backup"""
    if not backup_path or not Path(backup_path).exists():
        print(f"Cannot rollback: backup file {backup_path} not found")
        return False

    print(f"Rolling back migration...")
    print(f"Restoring from backup: {backup_path}")

    shutil.copy2(backup_path, db_path)
    print(f"✓ Database restored successfully")

    return True


def main():
    """Main migration function"""
    if len(sys.argv) > 1:
        db_path = sys.argv[1]
    else:
        # Default to database in parent directory
        db_path = str(Path(__file__).parent.parent / 'custom-cvp.db')

    print("=" * 60)
    print("User Authentication Migration")
    print("=" * 60)
    print(f"Database: {db_path}")
    print()

    # Check if migration command specified
    command = sys.argv[2] if len(sys.argv) > 2 else 'migrate'

    if command == 'verify':
        verify_migration(db_path)
        return

    if command == 'rollback':
        if len(sys.argv) < 4:
            print("Usage: python add_user_auth.py <db_path> rollback <backup_path>")
            sys.exit(1)
        backup_path = sys.argv[3]
        success = rollback_migration(db_path, backup_path)
        sys.exit(0 if success else 1)

    # Default: migrate
    # Create backup
    backup_path = backup_database(db_path)

    # Run migration
    success = create_user_auth_tables(db_path)

    if success:
        # Verify
        verify_success = verify_migration(db_path)

        if verify_success:
            print("\n" + "=" * 60)
            print("✓ Migration completed and verified successfully!")
            print("=" * 60)
            if backup_path:
                print(f"\nBackup saved to: {backup_path}")
            sys.exit(0)
        else:
            print("\n" + "=" * 60)
            print("✗ Migration verification failed!")
            print("=" * 60)
            sys.exit(1)
    else:
        print("\n" + "=" * 60)
        print("✗ Migration failed!")
        print("=" * 60)
        if backup_path:
            print(f"\nTo rollback: python {sys.argv[0]} {db_path} rollback {backup_path}")
        sys.exit(1)


if __name__ == '__main__':
    main()
