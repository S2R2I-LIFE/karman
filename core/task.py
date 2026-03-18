#!/usr/bin/env python3
"""
Task Management System (Change Control)
Manages configuration change tasks with approval workflow
"""

import sqlite3
from datetime import datetime
from enum import Enum
from typing import List, Dict, Optional
import json


class TaskStatus(Enum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class TaskType(Enum):
    CONFIG_CHANGE = "config_change"
    CONFIGLET_ASSIGN = "configlet_assign"
    CONFIGLET_REMOVE = "configlet_remove"
    SOFTWARE_UPGRADE = "software_upgrade"
    COMPLIANCE_CHECK = "compliance_check"


class Task:
    def __init__(self, task_id: int, task_type: TaskType, devices: List[str],
                 description: str, config_changes: Dict, created_by: str):
        self.task_id = task_id
        self.task_type = task_type
        self.devices = devices
        self.description = description
        self.config_changes = config_changes  # Device -> config mapping
        self.status = TaskStatus.PENDING
        self.created_at = datetime.now()
        self.created_by = created_by
        self.executed_at = None
        self.executed_by = None
        self.results = {}  # Device -> result mapping
        self.rollback_info = {}


class TaskManager:
    def __init__(self, db_path='custom-cvp.db'):
        self.db_path = db_path
        self._init_db()

    def _init_db(self):
        """Initialize task tables"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS tasks (
                task_id INTEGER PRIMARY KEY AUTOINCREMENT,
                task_type TEXT,
                description TEXT,
                status TEXT,
                created_at TIMESTAMP,
                created_by TEXT,
                executed_at TIMESTAMP,
                executed_by TEXT,
                devices TEXT,
                config_changes TEXT,
                results TEXT,
                rollback_info TEXT
            )
        ''')

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS task_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                task_id INTEGER,
                timestamp TIMESTAMP,
                device TEXT,
                log_level TEXT,
                message TEXT,
                FOREIGN KEY (task_id) REFERENCES tasks(task_id)
            )
        ''')

        conn.commit()
        conn.close()

    def create_task(self, task_type: TaskType, devices: List[str],
                   description: str, config_changes: Dict,
                   created_by: str = "system") -> int:
        """Create new task"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute('''
            INSERT INTO tasks
            (task_type, description, status, created_at, created_by,
             devices, config_changes)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (
            task_type.value,
            description,
            TaskStatus.PENDING.value,
            datetime.now(),
            created_by,
            json.dumps(devices),
            json.dumps(config_changes)
        ))

        task_id = cursor.lastrowid
        conn.commit()
        conn.close()

        return task_id

    def get_task(self, task_id: int) -> Optional[Dict]:
        """Get task by ID"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute('SELECT * FROM tasks WHERE task_id = ?', (task_id,))
        row = cursor.fetchone()
        conn.close()

        if not row:
            return None

        return {
            'task_id': row[0],
            'task_type': row[1],
            'description': row[2],
            'status': row[3],
            'created_at': row[4],
            'created_by': row[5],
            'executed_at': row[6],
            'executed_by': row[7],
            'devices': json.loads(row[8]) if row[8] else [],
            'config_changes': json.loads(row[9]) if row[9] else {},
            'results': json.loads(row[10]) if row[10] else {},
            'rollback_info': json.loads(row[11]) if row[11] else {}
        }

    def update_task_status(self, task_id: int, status: TaskStatus,
                          executed_by: str = None):
        """Update task status"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        if status in [TaskStatus.IN_PROGRESS, TaskStatus.COMPLETED]:
            cursor.execute('''
                UPDATE tasks
                SET status = ?, executed_at = ?, executed_by = ?
                WHERE task_id = ?
            ''', (status.value, datetime.now(), executed_by, task_id))
        else:
            cursor.execute('''
                UPDATE tasks SET status = ? WHERE task_id = ?
            ''', (status.value, task_id))

        conn.commit()
        conn.close()

    def add_task_log(self, task_id: int, device: str, log_level: str, message: str):
        """Add log entry for task"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute('''
            INSERT INTO task_logs (task_id, timestamp, device, log_level, message)
            VALUES (?, ?, ?, ?, ?)
        ''', (task_id, datetime.now(), device, log_level, message))

        conn.commit()
        conn.close()

    def get_task_logs(self, task_id: int) -> List[Dict]:
        """Get logs for a task"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute('''
            SELECT timestamp, device, log_level, message
            FROM task_logs
            WHERE task_id = ?
            ORDER BY timestamp
        ''', (task_id,))

        logs = []
        for row in cursor.fetchall():
            logs.append({
                'timestamp': row[0],
                'device': row[1],
                'log_level': row[2],
                'message': row[3]
            })

        conn.close()
        return logs

    def list_tasks(self, status: TaskStatus = None) -> List[Dict]:
        """List all tasks or filter by status"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        if status:
            cursor.execute('''
                SELECT task_id, task_type, description, status, created_at, created_by
                FROM tasks WHERE status = ? ORDER BY created_at DESC
            ''', (status.value,))
        else:
            cursor.execute('''
                SELECT task_id, task_type, description, status, created_at, created_by
                FROM tasks ORDER BY created_at DESC
            ''')

        tasks = []
        for row in cursor.fetchall():
            tasks.append({
                'task_id': row[0],
                'task_type': row[1],
                'description': row[2],
                'status': row[3],
                'created_at': row[4],
                'created_by': row[5]
            })

        conn.close()
        return tasks

    def update_task_results(self, task_id: int, results: Dict):
        """Update task results"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute('''
            UPDATE tasks SET results = ? WHERE task_id = ?
        ''', (json.dumps(results), task_id))

        conn.commit()
        conn.close()

    def delete_task(self, task_id: int) -> bool:
        """Delete a task and its logs"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute('DELETE FROM task_logs WHERE task_id = ?', (task_id,))
        cursor.execute('DELETE FROM tasks WHERE task_id = ?', (task_id,))
        affected = cursor.rowcount

        conn.commit()
        conn.close()

        return affected > 0
