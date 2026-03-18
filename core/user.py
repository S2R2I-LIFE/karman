"""
User Management Module
Handles user authentication, access requests, and account security
"""

import sqlite3
import json
import re
from datetime import datetime, timedelta
from dataclasses import dataclass
from typing import Optional, List, Dict, Any
from werkzeug.security import generate_password_hash, check_password_hash


@dataclass
class User:
    """User data class"""
    user_id: int
    username: str
    email: str
    full_name: str
    is_admin: bool
    is_active: bool
    created_at: str
    approved_at: Optional[str] = None
    approved_by: Optional[str] = None
    last_login: Optional[str] = None
    failed_login_attempts: int = 0
    account_locked_until: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return {
            'user_id': self.user_id,
            'username': self.username,
            'email': self.email,
            'full_name': self.full_name,
            'is_admin': bool(self.is_admin),
            'is_active': bool(self.is_active),
            'created_at': self.created_at,
            'approved_at': self.approved_at,
            'approved_by': self.approved_by,
            'last_login': self.last_login,
            'failed_login_attempts': self.failed_login_attempts,
            'account_locked_until': self.account_locked_until
        }


@dataclass
class AccessRequest:
    """Access request data class"""
    request_id: int
    username: str
    email: str
    full_name: str
    reason: str
    requested_at: str
    status: str
    reviewed_at: Optional[str] = None
    reviewed_by: Optional[str] = None
    rejection_reason: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return {
            'request_id': self.request_id,
            'username': self.username,
            'email': self.email,
            'full_name': self.full_name,
            'reason': self.reason,
            'requested_at': self.requested_at,
            'status': self.status,
            'reviewed_at': self.reviewed_at,
            'reviewed_by': self.reviewed_by,
            'rejection_reason': self.rejection_reason
        }


class UserManager:
    """User management and authentication"""

    def __init__(self, db_path='custom-cvp.db'):
        self.db_path = db_path
        self.max_login_attempts = 5
        self.lockout_duration_minutes = 30
        self.password_min_length = 8
        self._ensure_audit_table()

    def _ensure_audit_table(self):
        """Create auth_audit_log if it doesn't exist (idempotent)"""
        conn = sqlite3.connect(self.db_path)
        conn.execute('''
            CREATE TABLE IF NOT EXISTS auth_audit_log (
                log_id    INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                event_type TEXT NOT NULL,
                username  TEXT,
                ip_address TEXT,
                details   TEXT,
                success   INTEGER DEFAULT 1
            )
        ''')
        conn.commit()
        conn.close()

    # ==================== Validation Methods ====================

    def validate_username(self, username: str) -> tuple[bool, str]:
        """Validate username format"""
        if not username or len(username) < 3:
            return False, "Username must be at least 3 characters"
        if len(username) > 50:
            return False, "Username must be less than 50 characters"
        if not re.match(r'^[a-zA-Z0-9_]+$', username):
            return False, "Username can only contain letters, numbers, and underscores"
        return True, ""

    def validate_email(self, email: str) -> tuple[bool, str]:
        """Validate email format"""
        if not email or '@' not in email:
            return False, "Invalid email format"
        if len(email) > 255:
            return False, "Email too long"
        # Basic email validation
        pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
        if not re.match(pattern, email):
            return False, "Invalid email format"
        return True, ""

    def validate_password(self, password: str) -> tuple[bool, str]:
        """Validate password strength"""
        if not password or len(password) < self.password_min_length:
            return False, f"Password must be at least {self.password_min_length} characters"
        if len(password) > 128:
            return False, "Password too long (max 128 characters)"

        # Check for complexity
        has_upper = any(c.isupper() for c in password)
        has_lower = any(c.islower() for c in password)
        has_digit = any(c.isdigit() for c in password)

        if not (has_upper and has_lower and has_digit):
            return False, "Password must contain uppercase, lowercase, and numbers"

        return True, ""

    # ==================== First User Check ====================

    def is_first_user(self) -> bool:
        """Check if this is the first user (becomes admin)"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute('SELECT COUNT(*) FROM users')
        count = cursor.fetchone()[0]

        conn.close()
        return count == 0

    # ==================== User CRUD Operations ====================

    def create_user_direct(self, username: str, email: str, full_name: str,
                          password: str, is_admin: bool = False) -> Optional[int]:
        """
        Create user directly (bypassing access request system)
        Used for first user or admin-created users
        """
        # Validate inputs
        valid, error = self.validate_username(username)
        if not valid:
            raise ValueError(error)

        valid, error = self.validate_email(email)
        if not valid:
            raise ValueError(error)

        valid, error = self.validate_password(password)
        if not valid:
            raise ValueError(error)

        # Hash password
        password_hash = generate_password_hash(password)

        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        try:
            now = datetime.now().isoformat()

            cursor.execute('''
                INSERT INTO users (username, email, full_name, password_hash,
                                 is_admin, is_active, created_at, approved_at)
                VALUES (?, ?, ?, ?, ?, 1, ?, ?)
            ''', (username, email, full_name, password_hash, int(is_admin), now, now))

            user_id = cursor.lastrowid
            conn.commit()

            # Log event
            self.log_auth_event('user_created', username, None,
                              {'is_admin': is_admin, 'created_directly': True})

            return user_id

        except sqlite3.IntegrityError as e:
            if 'username' in str(e):
                raise ValueError(f"Username '{username}' already exists")
            elif 'email' in str(e):
                raise ValueError(f"Email '{email}' already exists")
            else:
                raise ValueError("User already exists")
        finally:
            conn.close()

    def get_user_by_username(self, username: str) -> Optional[User]:
        """Get user by username"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute('''
            SELECT user_id, username, email, full_name, is_admin, is_active,
                   created_at, approved_at, approved_by, last_login,
                   failed_login_attempts, account_locked_until
            FROM users
            WHERE username = ?
        ''', (username,))

        row = cursor.fetchone()
        conn.close()

        if not row:
            return None

        return User(
            user_id=row[0],
            username=row[1],
            email=row[2],
            full_name=row[3],
            is_admin=bool(row[4]),
            is_active=bool(row[5]),
            created_at=row[6],
            approved_at=row[7],
            approved_by=row[8],
            last_login=row[9],
            failed_login_attempts=row[10],
            account_locked_until=row[11]
        )

    def get_user_by_id(self, user_id: int) -> Optional[User]:
        """Get user by ID"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute('''
            SELECT user_id, username, email, full_name, is_admin, is_active,
                   created_at, approved_at, approved_by, last_login,
                   failed_login_attempts, account_locked_until
            FROM users
            WHERE user_id = ?
        ''', (user_id,))

        row = cursor.fetchone()
        conn.close()

        if not row:
            return None

        return User(
            user_id=row[0],
            username=row[1],
            email=row[2],
            full_name=row[3],
            is_admin=bool(row[4]),
            is_active=bool(row[5]),
            created_at=row[6],
            approved_at=row[7],
            approved_by=row[8],
            last_login=row[9],
            failed_login_attempts=row[10],
            account_locked_until=row[11]
        )

    def list_all_users(self) -> List[User]:
        """List all users"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute('''
            SELECT user_id, username, email, full_name, is_admin, is_active,
                   created_at, approved_at, approved_by, last_login,
                   failed_login_attempts, account_locked_until
            FROM users
            ORDER BY created_at DESC
        ''')

        users = []
        for row in cursor.fetchall():
            users.append(User(
                user_id=row[0],
                username=row[1],
                email=row[2],
                full_name=row[3],
                is_admin=bool(row[4]),
                is_active=bool(row[5]),
                created_at=row[6],
                approved_at=row[7],
                approved_by=row[8],
                last_login=row[9],
                failed_login_attempts=row[10],
                account_locked_until=row[11]
            ))

        conn.close()
        return users

    # ==================== Access Request Management ====================

    def create_access_request(self, username: str, email: str, full_name: str,
                             password: str, reason: str) -> int:
        """Create new access request"""
        # Validate inputs
        valid, error = self.validate_username(username)
        if not valid:
            raise ValueError(error)

        valid, error = self.validate_email(email)
        if not valid:
            raise ValueError(error)

        valid, error = self.validate_password(password)
        if not valid:
            raise ValueError(error)

        # Hash password now
        password_hash = generate_password_hash(password)

        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        try:
            now = datetime.now().isoformat()

            cursor.execute('''
                INSERT INTO access_requests (username, email, full_name, password_hash,
                                            reason, requested_at, status)
                VALUES (?, ?, ?, ?, ?, ?, 'pending')
            ''', (username, email, full_name, password_hash, reason, now))

            request_id = cursor.lastrowid
            conn.commit()

            # Log event
            self.log_auth_event('access_requested', username, None,
                              {'email': email, 'request_id': request_id})

            return request_id

        except sqlite3.IntegrityError as e:
            if 'username' in str(e):
                raise ValueError(f"Username '{username}' is already taken or has a pending request")
            elif 'email' in str(e):
                raise ValueError(f"Email '{email}' is already registered or has a pending request")
            else:
                raise ValueError("Request already exists")
        finally:
            conn.close()

    def get_access_request(self, request_id: int) -> Optional[AccessRequest]:
        """Get access request by ID"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute('''
            SELECT request_id, username, email, full_name, reason, requested_at,
                   status, reviewed_at, reviewed_by, rejection_reason
            FROM access_requests
            WHERE request_id = ?
        ''', (request_id,))

        row = cursor.fetchone()
        conn.close()

        if not row:
            return None

        return AccessRequest(
            request_id=row[0],
            username=row[1],
            email=row[2],
            full_name=row[3],
            reason=row[4],
            requested_at=row[5],
            status=row[6],
            reviewed_at=row[7],
            reviewed_by=row[8],
            rejection_reason=row[9]
        )

    def list_pending_requests(self) -> List[AccessRequest]:
        """List all pending access requests"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute('''
            SELECT request_id, username, email, full_name, reason, requested_at,
                   status, reviewed_at, reviewed_by, rejection_reason
            FROM access_requests
            WHERE status = 'pending'
            ORDER BY requested_at ASC
        ''')

        requests = []
        for row in cursor.fetchall():
            requests.append(AccessRequest(
                request_id=row[0],
                username=row[1],
                email=row[2],
                full_name=row[3],
                reason=row[4],
                requested_at=row[5],
                status=row[6],
                reviewed_at=row[7],
                reviewed_by=row[8],
                rejection_reason=row[9]
            ))

        conn.close()
        return requests

    def approve_request(self, request_id: int, approved_by: str) -> Optional[int]:
        """Approve access request and create user"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        try:
            # Get request
            cursor.execute('''
                SELECT username, email, full_name, password_hash, status
                FROM access_requests
                WHERE request_id = ?
            ''', (request_id,))

            row = cursor.fetchone()
            if not row:
                raise ValueError(f"Access request {request_id} not found")

            username, email, full_name, password_hash, status = row

            if status != 'pending':
                raise ValueError(f"Request is already {status}")

            # Create user
            now = datetime.now().isoformat()
            cursor.execute('''
                INSERT INTO users (username, email, full_name, password_hash,
                                 is_admin, is_active, created_at, approved_at, approved_by)
                VALUES (?, ?, ?, ?, 0, 1, ?, ?, ?)
            ''', (username, email, full_name, password_hash, now, now, approved_by))

            user_id = cursor.lastrowid

            # Update request status
            cursor.execute('''
                UPDATE access_requests
                SET status = 'approved', reviewed_at = ?, reviewed_by = ?
                WHERE request_id = ?
            ''', (now, approved_by, request_id))

            conn.commit()

            # Log event
            self.log_auth_event('access_approved', username, None,
                              {'approved_by': approved_by, 'request_id': request_id})

            return user_id

        except sqlite3.IntegrityError as e:
            conn.rollback()
            raise ValueError(f"Failed to create user: {str(e)}")
        finally:
            conn.close()

    def reject_request(self, request_id: int, rejected_by: str, reason: str) -> bool:
        """Reject access request"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        try:
            # Check if request exists and is pending
            cursor.execute('''
                SELECT username, status
                FROM access_requests
                WHERE request_id = ?
            ''', (request_id,))

            row = cursor.fetchone()
            if not row:
                raise ValueError(f"Access request {request_id} not found")

            username, status = row

            if status != 'pending':
                raise ValueError(f"Request is already {status}")

            # Update request
            now = datetime.now().isoformat()
            cursor.execute('''
                UPDATE access_requests
                SET status = 'rejected', reviewed_at = ?, reviewed_by = ?, rejection_reason = ?
                WHERE request_id = ?
            ''', (now, rejected_by, reason, request_id))

            conn.commit()

            # Log event
            self.log_auth_event('access_rejected', username, None,
                              {'rejected_by': rejected_by, 'request_id': request_id, 'reason': reason})

            return True

        except Exception as e:
            conn.rollback()
            raise
        finally:
            conn.close()

    # ==================== Authentication ====================

    def verify_credentials(self, username: str, password: str) -> Optional[Dict[str, Any]]:
        """
        Verify login credentials
        Returns user dict if valid, None if invalid
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute('''
            SELECT user_id, username, email, full_name, password_hash,
                   is_admin, is_active, failed_login_attempts, account_locked_until
            FROM users
            WHERE username = ?
        ''', (username,))

        row = cursor.fetchone()
        conn.close()

        if not row:
            return None

        user_id, username, email, full_name, password_hash, is_admin, is_active, \
            failed_attempts, locked_until = row

        # Check if account is locked
        if locked_until:
            lock_time = datetime.fromisoformat(locked_until)
            if datetime.now() < lock_time:
                return None  # Still locked

        # Verify password
        if not check_password_hash(password_hash, password):
            return None

        # Check if active
        if not is_active:
            return None

        return {
            'user_id': user_id,
            'username': username,
            'email': email,
            'full_name': full_name,
            'is_admin': bool(is_admin),
            'is_active': bool(is_active)
        }

    def increment_failed_login(self, username: str):
        """Increment failed login attempts and lock if threshold reached"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute('''
            UPDATE users
            SET failed_login_attempts = failed_login_attempts + 1
            WHERE username = ?
        ''', (username,))

        # Check if we should lock the account
        cursor.execute('''
            SELECT failed_login_attempts FROM users WHERE username = ?
        ''', (username,))

        row = cursor.fetchone()
        if row and row[0] >= self.max_login_attempts:
            # Lock account
            lockout_until = datetime.now() + timedelta(minutes=self.lockout_duration_minutes)
            cursor.execute('''
                UPDATE users
                SET account_locked_until = ?
                WHERE username = ?
            ''', (lockout_until.isoformat(), username))

            self.log_auth_event('account_locked', username, None,
                              {'attempts': row[0], 'lockout_minutes': self.lockout_duration_minutes})

        conn.commit()
        conn.close()

    def reset_failed_attempts(self, username: str):
        """Reset failed login attempts after successful login"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute('''
            UPDATE users
            SET failed_login_attempts = 0, account_locked_until = NULL
            WHERE username = ?
        ''', (username,))

        conn.commit()
        conn.close()

    def is_account_locked(self, username: str) -> bool:
        """Check if account is currently locked"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute('''
            SELECT account_locked_until FROM users WHERE username = ?
        ''', (username,))

        row = cursor.fetchone()
        conn.close()

        if not row or not row[0]:
            return False

        lock_time = datetime.fromisoformat(row[0])
        return datetime.now() < lock_time

    def update_last_login(self, user_id: int):
        """Update last login timestamp"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        now = datetime.now().isoformat()
        cursor.execute('''
            UPDATE users
            SET last_login = ?
            WHERE user_id = ?
        ''', (now, user_id))

        conn.commit()
        conn.close()

    # ==================== Audit Logging ====================

    def log_auth_event(self, event_type: str, username: str, ip_address: Optional[str],
                      details: Dict[str, Any], success: bool = True):
        """Log authentication event to audit log"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        now = datetime.now().isoformat()
        details_json = json.dumps(details)

        cursor.execute('''
            INSERT INTO auth_audit_log (timestamp, event_type, username, ip_address, details, success)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (now, event_type, username, ip_address, details_json, int(success)))

        conn.commit()
        conn.close()

    def get_audit_log(self, username: Optional[str] = None, limit: int = 100) -> List[Dict[str, Any]]:
        """Get audit log entries"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        if username:
            cursor.execute('''
                SELECT log_id, timestamp, event_type, username, ip_address, details, success
                FROM auth_audit_log
                WHERE username = ?
                ORDER BY timestamp DESC
                LIMIT ?
            ''', (username, limit))
        else:
            cursor.execute('''
                SELECT log_id, timestamp, event_type, username, ip_address, details, success
                FROM auth_audit_log
                ORDER BY timestamp DESC
                LIMIT ?
            ''', (limit,))

        logs = []
        for row in cursor.fetchall():
            logs.append({
                'log_id': row[0],
                'timestamp': row[1],
                'event_type': row[2],
                'username': row[3],
                'ip_address': row[4],
                'details': json.loads(row[5]) if row[5] else {},
                'success': bool(row[6])
            })

        conn.close()
        return logs
