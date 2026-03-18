#!/usr/bin/env python3
"""
Configlet Management System
Manages configuration snippets with versioning and history tracking
"""

import sqlite3
import hashlib
from datetime import datetime
from typing import List, Optional, Dict
from pathlib import Path


class Configlet:
    def __init__(self, name: str, config: str, description: str = "",
                 configlet_type: str = "static", template_vars: Dict = None):
        self.name = name
        self.config = config
        self.description = description
        self.configlet_type = configlet_type  # static, template, builder
        self.template_vars = template_vars or {}
        self.hash = self._calculate_hash()
        self.created_at = datetime.now()
        self.updated_at = datetime.now()

    def _calculate_hash(self):
        """Calculate SHA256 hash of config"""
        return hashlib.sha256(self.config.encode()).hexdigest()

    def update_config(self, new_config: str):
        """Update configlet content"""
        self.config = new_config
        self.hash = self._calculate_hash()
        self.updated_at = datetime.now()


class ConfigletManager:
    def __init__(self, db_path='custom-cvp.db', configlet_dir='configlets'):
        self.db_path = db_path
        self.configlet_dir = Path(configlet_dir)
        self.configlet_dir.mkdir(exist_ok=True)
        self._init_db()

    def _init_db(self):
        """Initialize configlet tables"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS configlets (
                name TEXT PRIMARY KEY,
                description TEXT,
                configlet_type TEXT,
                config_hash TEXT,
                created_at TIMESTAMP,
                updated_at TIMESTAMP,
                version INTEGER DEFAULT 1
            )
        ''')

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS configlet_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                configlet_name TEXT,
                version INTEGER,
                config_hash TEXT,
                changed_at TIMESTAMP,
                changed_by TEXT,
                change_reason TEXT
            )
        ''')

        conn.commit()
        conn.close()

    def create_configlet(self, configlet: Configlet, author: str = "system"):
        """Create new configlet"""
        # Save to filesystem
        configlet_file = self.configlet_dir / f"{configlet.name}.cfg"
        with open(configlet_file, 'w') as f:
            f.write(configlet.config)

        # Save to database
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute('''
            INSERT OR REPLACE INTO configlets
            (name, description, configlet_type, config_hash, created_at, updated_at, version)
            VALUES (?, ?, ?, ?, ?, ?, 1)
        ''', (
            configlet.name,
            configlet.description,
            configlet.configlet_type,
            configlet.hash,
            configlet.created_at,
            configlet.updated_at
        ))

        # Add to history
        cursor.execute('''
            INSERT INTO configlet_history
            (configlet_name, version, config_hash, changed_at, changed_by, change_reason)
            VALUES (?, 1, ?, ?, ?, 'Initial creation')
        ''', (configlet.name, configlet.hash, datetime.now(), author))

        conn.commit()
        conn.close()

    def update_configlet(self, name: str, new_config: str,
                        author: str = "system", reason: str = ""):
        """Update existing configlet"""
        configlet = self.get_configlet(name)
        if not configlet:
            raise ValueError(f"Configlet {name} not found")

        old_hash = configlet.hash
        configlet.update_config(new_config)

        # Update filesystem
        configlet_file = self.configlet_dir / f"{name}.cfg"
        with open(configlet_file, 'w') as f:
            f.write(new_config)

        # Update database
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        # Get current version
        cursor.execute('SELECT version FROM configlets WHERE name = ?', (name,))
        current_version = cursor.fetchone()[0]
        new_version = current_version + 1

        cursor.execute('''
            UPDATE configlets
            SET config_hash = ?, updated_at = ?, version = ?
            WHERE name = ?
        ''', (configlet.hash, configlet.updated_at, new_version, name))

        # Add to history
        cursor.execute('''
            INSERT INTO configlet_history
            (configlet_name, version, config_hash, changed_at, changed_by, change_reason)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (name, new_version, configlet.hash, datetime.now(), author, reason))

        conn.commit()
        conn.close()

        return old_hash, configlet.hash  # Return for change tracking

    def get_configlet(self, name: str) -> Optional[Configlet]:
        """Get configlet by name"""
        configlet_file = self.configlet_dir / f"{name}.cfg"
        if not configlet_file.exists():
            return None

        with open(configlet_file, 'r') as f:
            config = f.read()

        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute('SELECT description, configlet_type FROM configlets WHERE name = ?',
                      (name,))
        row = cursor.fetchone()
        conn.close()

        if row:
            return Configlet(name, config, row[0], row[1])
        return None

    def list_configlets(self) -> List[str]:
        """List all configlet names"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute('SELECT name FROM configlets ORDER BY name')
        names = [r[0] for r in cursor.fetchall()]
        conn.close()
        return names

    def get_configlet_history(self, name: str) -> List[Dict]:
        """Get change history for configlet"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute('''
            SELECT version, config_hash, changed_at, changed_by, change_reason
            FROM configlet_history
            WHERE configlet_name = ?
            ORDER BY version DESC
        ''', (name,))

        history = []
        for row in cursor.fetchall():
            history.append({
                'version': row[0],
                'hash': row[1],
                'changed_at': row[2],
                'changed_by': row[3],
                'reason': row[4]
            })

        conn.close()
        return history

    def delete_configlet(self, name: str):
        """Delete a configlet"""
        configlet_file = self.configlet_dir / f"{name}.cfg"
        if configlet_file.exists():
            configlet_file.unlink()

        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute('DELETE FROM configlets WHERE name = ?', (name,))
        cursor.execute('DELETE FROM configlet_history WHERE configlet_name = ?', (name,))
        conn.commit()
        conn.close()
