#!/usr/bin/env python3
"""
Initialize default admin user from environment variables
Run this during container startup to ensure admin access
"""

import os
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent))

from core.user import UserManager


def init_default_user():
    """Create default admin user if no users exist"""
    db_path = os.environ.get('DATABASE_PATH', '/app/data/custom-cvp.db')
    default_username = os.environ.get('DEFAULT_USERNAME', 'admin')
    default_password = os.environ.get('DEFAULT_PASSWORD', 'admin')

    print(f"[INIT] Checking for existing users in {db_path}")

    user_mgr = UserManager(db_path)

    # Check if this is the first user
    if user_mgr.is_first_user():
        print(f"[INIT] No users found, creating default admin user: {default_username}")
        try:
            user_id = user_mgr.create_user_direct(
                username=default_username,
                email=f"{default_username}@custom-cvp.local",
                full_name="Default Administrator",
                password=default_password,
                is_admin=True
            )
            print(f"[INIT] ✓ Default admin user created successfully (ID: {user_id})")
            print(f"[INIT]   Username: {default_username}")
            print(f"[INIT]   Password: {default_password}")
            print(f"[INIT]   WARNING: Change the default password after first login!")
            return True
        except Exception as e:
            print(f"[INIT] ✗ Failed to create default user: {str(e)}")
            return False
    else:
        print(f"[INIT] Users already exist, skipping default user creation")
        return True


if __name__ == '__main__':
    success = init_default_user()
    sys.exit(0 if success else 1)
