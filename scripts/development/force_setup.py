#!/usr/bin/env python3
"""
Force setup - Closes all database connections and runs setup
"""

import sqlite3
import sys
import time
from pathlib import Path

# Force close any existing connections by opening in exclusive mode temporarily
db_path = Path(__file__).parent / 'custom-cvp.db'

print("Attempting to acquire exclusive database lock...")
try:
    # This will wait up to 60 seconds for any locks to be released
    conn = sqlite3.connect(str(db_path), timeout=60.0)
    conn.execute('PRAGMA locking_mode=EXCLUSIVE')
    conn.execute('BEGIN EXCLUSIVE')
    print("✓ Exclusive lock acquired")
    conn.rollback()
    conn.close()
    print("✓ Lock released")
    time.sleep(1)
except Exception as e:
    print(f"✗ Could not acquire lock: {e}")
    print("\nPlease manually kill any Python processes:")
    print("  killall python3")
    sys.exit(1)

# Now run the setup
print("\nRunning setup...")

from setup_cli_browser import main
success = main()
sys.exit(0 if success else 1)
