"""
Notification Management Module
Handles in-app notifications for users
"""

import sqlite3
from datetime import datetime, timedelta
from dataclasses import dataclass
from typing import Optional, List, Dict, Any


@dataclass
class Notification:
    """Notification data class"""
    notification_id: int
    user_id: Optional[int]
    notification_type: str
    title: str
    message: str
    related_id: Optional[int]
    is_read: bool
    created_at: str
    read_at: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return {
            'notification_id': self.notification_id,
            'user_id': self.user_id,
            'notification_type': self.notification_type,
            'title': self.title,
            'message': self.message,
            'related_id': self.related_id,
            'is_read': bool(self.is_read),
            'created_at': self.created_at,
            'read_at': self.read_at
        }


class NotificationManager:
    """Manage in-app notifications"""

    def __init__(self, db_path='custom-cvp.db'):
        self.db_path = db_path

    def create_notification(self, user_id: Optional[int], notification_type: str,
                          title: str, message: str, related_id: Optional[int] = None) -> int:
        """
        Create a new notification

        Args:
            user_id: Target user ID (None for system-wide notifications)
            notification_type: Type of notification (access_request, request_approved, etc.)
            title: Notification title
            message: Notification message
            related_id: Related entity ID (request_id, user_id, etc.)

        Returns:
            notification_id
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        now = datetime.now().isoformat()

        cursor.execute('''
            INSERT INTO notification_queue (user_id, notification_type, title, message,
                                          related_id, is_read, created_at)
            VALUES (?, ?, ?, ?, ?, 0, ?)
        ''', (user_id, notification_type, title, message, related_id, now))

        notification_id = cursor.lastrowid
        conn.commit()
        conn.close()

        return notification_id

    def get_notification(self, notification_id: int) -> Optional[Notification]:
        """Get notification by ID"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute('''
            SELECT notification_id, user_id, notification_type, title, message,
                   related_id, is_read, created_at, read_at
            FROM notification_queue
            WHERE notification_id = ?
        ''', (notification_id,))

        row = cursor.fetchone()
        conn.close()

        if not row:
            return None

        return Notification(
            notification_id=row[0],
            user_id=row[1],
            notification_type=row[2],
            title=row[3],
            message=row[4],
            related_id=row[5],
            is_read=bool(row[6]),
            created_at=row[7],
            read_at=row[8]
        )

    def get_user_notifications(self, user_id: int, unread_only: bool = False,
                              limit: int = 50) -> List[Notification]:
        """
        Get notifications for a user

        Args:
            user_id: User ID
            unread_only: Only return unread notifications
            limit: Maximum number of notifications to return

        Returns:
            List of Notification objects
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        if unread_only:
            cursor.execute('''
                SELECT notification_id, user_id, notification_type, title, message,
                       related_id, is_read, created_at, read_at
                FROM notification_queue
                WHERE user_id = ? AND is_read = 0
                ORDER BY created_at DESC
                LIMIT ?
            ''', (user_id, limit))
        else:
            cursor.execute('''
                SELECT notification_id, user_id, notification_type, title, message,
                       related_id, is_read, created_at, read_at
                FROM notification_queue
                WHERE user_id = ?
                ORDER BY created_at DESC
                LIMIT ?
            ''', (user_id, limit))

        notifications = []
        for row in cursor.fetchall():
            notifications.append(Notification(
                notification_id=row[0],
                user_id=row[1],
                notification_type=row[2],
                title=row[3],
                message=row[4],
                related_id=row[5],
                is_read=bool(row[6]),
                created_at=row[7],
                read_at=row[8]
            ))

        conn.close()
        return notifications

    def get_admin_notifications(self, limit: int = 50) -> List[Notification]:
        """
        Get system-wide admin notifications (user_id is NULL)

        Args:
            limit: Maximum number of notifications to return

        Returns:
            List of Notification objects
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute('''
            SELECT notification_id, user_id, notification_type, title, message,
                   related_id, is_read, created_at, read_at
            FROM notification_queue
            WHERE user_id IS NULL
            ORDER BY created_at DESC
            LIMIT ?
        ''', (limit,))

        notifications = []
        for row in cursor.fetchall():
            notifications.append(Notification(
                notification_id=row[0],
                user_id=row[1],
                notification_type=row[2],
                title=row[3],
                message=row[4],
                related_id=row[5],
                is_read=bool(row[6]),
                created_at=row[7],
                read_at=row[8]
            ))

        conn.close()
        return notifications

    def get_unread_count(self, user_id: int) -> int:
        """Get count of unread notifications for a user"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute('''
            SELECT COUNT(*)
            FROM notification_queue
            WHERE user_id = ? AND is_read = 0
        ''', (user_id,))

        count = cursor.fetchone()[0]
        conn.close()

        return count

    def get_pending_requests_count(self) -> int:
        """Get count of pending access requests (for admin badge)"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute('''
            SELECT COUNT(*)
            FROM access_requests
            WHERE status = 'pending'
        ''')

        count = cursor.fetchone()[0]
        conn.close()

        return count

    def mark_as_read(self, notification_id: int) -> bool:
        """Mark notification as read"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        now = datetime.now().isoformat()

        cursor.execute('''
            UPDATE notification_queue
            SET is_read = 1, read_at = ?
            WHERE notification_id = ?
        ''', (now, notification_id))

        affected = cursor.rowcount
        conn.commit()
        conn.close()

        return affected > 0

    def mark_all_as_read(self, user_id: int) -> int:
        """Mark all notifications as read for a user"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        now = datetime.now().isoformat()

        cursor.execute('''
            UPDATE notification_queue
            SET is_read = 1, read_at = ?
            WHERE user_id = ? AND is_read = 0
        ''', (now, user_id))

        affected = cursor.rowcount
        conn.commit()
        conn.close()

        return affected

    def delete_notification(self, notification_id: int) -> bool:
        """Delete a notification"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute('''
            DELETE FROM notification_queue
            WHERE notification_id = ?
        ''', (notification_id,))

        affected = cursor.rowcount
        conn.commit()
        conn.close()

        return affected > 0

    def delete_old_notifications(self, days: int = 30) -> int:
        """Delete notifications older than specified days"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cutoff_date = (datetime.now() - timedelta(days=days)).isoformat()

        cursor.execute('''
            DELETE FROM notification_queue
            WHERE created_at < ? AND is_read = 1
        ''', (cutoff_date,))

        affected = cursor.rowcount
        conn.commit()
        conn.close()

        return affected

    # ==================== Helper Methods for Common Notifications ====================

    def notify_new_access_request(self, admin_user_id: int, username: str, request_id: int):
        """Create notification for admin about new access request"""
        return self.create_notification(
            user_id=admin_user_id,
            notification_type='access_request',
            title='New Access Request',
            message=f'User {username} has requested access to the system.',
            related_id=request_id
        )

    def notify_request_approved(self, user_id: int, approved_by: str):
        """Create notification for user about approved request"""
        return self.create_notification(
            user_id=user_id,
            notification_type='request_approved',
            title='Access Approved',
            message=f'Your access request has been approved by {approved_by}. You can now log in.',
            related_id=None
        )

    def notify_request_rejected(self, username: str, rejected_by: str, reason: str):
        """
        Create system notification about rejected request
        Note: User doesn't have an account yet, so can't receive user-specific notification
        This is logged for audit purposes
        """
        # For now, we'll just skip creating a notification since user has no account
        # In a real system, you might send an email instead
        pass
