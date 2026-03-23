#!/usr/bin/env python3
"""
Alert Manager — threshold-based alerting for Kármán.
Manages alert rules and firing/resolved event lifecycle.
"""

import sqlite3
import time
from dataclasses import dataclass
from typing import List, Optional, Dict, Any


@dataclass
class AlertRule:
    rule_id: int
    rule_name: str
    alert_type: str        # cpu | memory | interface_down_count | device_down | temperature_critical
    threshold: Optional[float]
    scope: str             # 'all' or specific hostname
    cooldown_minutes: int
    send_email: bool
    is_enabled: bool
    created_by: Optional[str]
    created_at: Optional[float]

    def to_dict(self) -> Dict[str, Any]:
        return {
            'rule_id': self.rule_id,
            'rule_name': self.rule_name,
            'alert_type': self.alert_type,
            'threshold': self.threshold,
            'scope': self.scope,
            'cooldown_minutes': self.cooldown_minutes,
            'send_email': bool(self.send_email),
            'is_enabled': bool(self.is_enabled),
            'created_by': self.created_by,
            'created_at': self.created_at,
        }


@dataclass
class AlertEvent:
    event_id: int
    rule_id: int
    hostname: str
    status: str            # 'firing' | 'resolved'
    value: Optional[float]
    triggered_at: float
    resolved_at: Optional[float]
    notified_at: Optional[float]

    def to_dict(self) -> Dict[str, Any]:
        return {
            'event_id': self.event_id,
            'rule_id': self.rule_id,
            'hostname': self.hostname,
            'status': self.status,
            'value': self.value,
            'triggered_at': self.triggered_at,
            'resolved_at': self.resolved_at,
            'notified_at': self.notified_at,
        }


class AlertManager:
    def __init__(self, db_path: str = 'custom-cvp.db'):
        self.db_path = db_path
        self._init_db()

    def _init_db(self):
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS alert_rules (
                rule_id          INTEGER PRIMARY KEY AUTOINCREMENT,
                rule_name        TEXT NOT NULL,
                alert_type       TEXT NOT NULL,
                threshold        REAL,
                scope            TEXT NOT NULL DEFAULT 'all',
                cooldown_minutes INTEGER NOT NULL DEFAULT 60,
                send_email       BOOLEAN NOT NULL DEFAULT 0,
                is_enabled       BOOLEAN NOT NULL DEFAULT 1,
                created_by       TEXT,
                created_at       REAL
            )
        ''')
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS alert_events (
                event_id     INTEGER PRIMARY KEY AUTOINCREMENT,
                rule_id      INTEGER NOT NULL REFERENCES alert_rules(rule_id) ON DELETE CASCADE,
                hostname     TEXT NOT NULL,
                status       TEXT NOT NULL,
                value        REAL,
                triggered_at REAL NOT NULL,
                resolved_at  REAL,
                notified_at  REAL
            )
        ''')
        conn.commit()
        conn.close()

    # ── Rule CRUD ──────────────────────────────────────────────────────────────

    def list_rules(self) -> List[AlertRule]:
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute(
            'SELECT rule_id, rule_name, alert_type, threshold, scope, '
            'cooldown_minutes, send_email, is_enabled, created_by, created_at '
            'FROM alert_rules ORDER BY rule_id'
        )
        rows = cursor.fetchall()
        conn.close()
        return [AlertRule(*row) for row in rows]

    def get_rule(self, rule_id: int) -> Optional[AlertRule]:
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute(
            'SELECT rule_id, rule_name, alert_type, threshold, scope, '
            'cooldown_minutes, send_email, is_enabled, created_by, created_at '
            'FROM alert_rules WHERE rule_id = ?', (rule_id,)
        )
        row = cursor.fetchone()
        conn.close()
        return AlertRule(*row) if row else None

    def create_rule(self, rule_name: str, alert_type: str, threshold: Optional[float],
                    scope: str = 'all', cooldown_minutes: int = 60,
                    send_email: bool = False, created_by: str = '') -> int:
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute(
            'INSERT INTO alert_rules '
            '(rule_name, alert_type, threshold, scope, cooldown_minutes, send_email, '
            'is_enabled, created_by, created_at) VALUES (?, ?, ?, ?, ?, ?, 1, ?, ?)',
            (rule_name, alert_type, threshold, scope, cooldown_minutes,
             1 if send_email else 0, created_by, time.time())
        )
        rule_id = cursor.lastrowid
        conn.commit()
        conn.close()
        return rule_id

    def update_rule(self, rule_id: int, **fields) -> bool:
        allowed = {'rule_name', 'alert_type', 'threshold', 'scope',
                   'cooldown_minutes', 'send_email', 'is_enabled'}
        updates = {k: v for k, v in fields.items() if k in allowed}
        if not updates:
            return False
        set_clause = ', '.join(f'{k} = ?' for k in updates)
        values = list(updates.values()) + [rule_id]
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute(f'UPDATE alert_rules SET {set_clause} WHERE rule_id = ?', values)
        changed = cursor.rowcount > 0
        conn.commit()
        conn.close()
        return changed

    def delete_rule(self, rule_id: int) -> bool:
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute('DELETE FROM alert_rules WHERE rule_id = ?', (rule_id,))
        changed = cursor.rowcount > 0
        conn.commit()
        conn.close()
        return changed

    def toggle_rule(self, rule_id: int) -> Optional[bool]:
        rule = self.get_rule(rule_id)
        if rule is None:
            return None
        new_state = not rule.is_enabled
        self.update_rule(rule_id, is_enabled=1 if new_state else 0)
        return new_state

    # ── Event lifecycle ────────────────────────────────────────────────────────

    def get_active_event(self, rule_id: int, hostname: str) -> Optional[AlertEvent]:
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute(
            'SELECT event_id, rule_id, hostname, status, value, triggered_at, '
            'resolved_at, notified_at FROM alert_events '
            'WHERE rule_id = ? AND hostname = ? AND status = "firing"',
            (rule_id, hostname)
        )
        row = cursor.fetchone()
        conn.close()
        return AlertEvent(*row) if row else None

    def open_event(self, rule_id: int, hostname: str, value: Optional[float]) -> int:
        now = time.time()
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute(
            'INSERT INTO alert_events '
            '(rule_id, hostname, status, value, triggered_at, notified_at) '
            'VALUES (?, ?, "firing", ?, ?, ?)',
            (rule_id, hostname, value, now, now)
        )
        event_id = cursor.lastrowid
        conn.commit()
        conn.close()
        return event_id

    def resolve_event(self, event_id: int):
        conn = sqlite3.connect(self.db_path)
        conn.execute(
            'UPDATE alert_events SET status = "resolved", resolved_at = ? '
            'WHERE event_id = ?',
            (time.time(), event_id)
        )
        conn.commit()
        conn.close()

    def update_notified_at(self, event_id: int):
        conn = sqlite3.connect(self.db_path)
        conn.execute(
            'UPDATE alert_events SET notified_at = ? WHERE event_id = ?',
            (time.time(), event_id)
        )
        conn.commit()
        conn.close()

    def get_recent_events(self, limit: int = 100) -> List[AlertEvent]:
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute(
            'SELECT event_id, rule_id, hostname, status, value, triggered_at, '
            'resolved_at, notified_at FROM alert_events '
            'ORDER BY triggered_at DESC LIMIT ?', (limit,)
        )
        rows = cursor.fetchall()
        conn.close()
        return [AlertEvent(*row) for row in rows]
