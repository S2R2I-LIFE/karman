#!/usr/bin/env python3
"""
Inventory Management System
Manages device inventory with support for both CVP-managed and custom-managed devices
"""

import yaml
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Dict, Optional
from enum import Enum
from pathlib import Path


class DeviceType(Enum):
    CVP_MANAGED = "cvp"
    EAPI_MANAGED = "eapi"
    SSH_MANAGED = "ssh"
    GNMI_MANAGED = "gnmi"


class DeviceRole(Enum):
    SPINE = "spine"
    LEAF = "leaf"
    BORDER = "border"
    CORE = "core"
    ACCESS = "access"


@dataclass
class Device:
    hostname: str
    ip_address: str
    model: str
    serial_number: str
    eos_version: str
    management_type: DeviceType
    role: DeviceRole
    site: str
    container: str
    configlets: List[str] = field(default_factory=list)
    tags: Dict[str, str] = field(default_factory=dict)
    cvp_managed: bool = False
    gnmi_port: int = 6030
    polling_enabled: bool = True
    last_backup_at: Optional[str] = None
    last_synced_at: Optional[str] = None
    agent_installed: bool = False
    agent_last_checkin: Optional[str] = None

    def to_dict(self):
        return {
            'hostname': self.hostname,
            'ip_address': self.ip_address,
            'model': self.model,
            'serial_number': self.serial_number,
            'eos_version': self.eos_version,
            'management_type': self.management_type.value,
            'role': self.role.value,
            'site': self.site,
            'container': self.container,
            'configlets': self.configlets,
            'tags': self.tags,
            'cvp_managed': self.cvp_managed,
            'gnmi_port': self.gnmi_port,
            'polling_enabled': self.polling_enabled,
        }


class InventoryManager:
    def __init__(self, db_path='custom-cvp.db'):
        self.db_path = db_path
        self._init_db()

    def _init_db(self):
        """Initialize SQLite database"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS devices (
                hostname TEXT PRIMARY KEY,
                ip_address TEXT NOT NULL,
                model TEXT,
                serial_number TEXT,
                eos_version TEXT,
                management_type TEXT,
                role TEXT,
                site TEXT,
                container TEXT,
                cvp_managed BOOLEAN,
                last_seen TIMESTAMP,
                compliance_status TEXT,
                config_hash TEXT,
                gnmi_port INTEGER DEFAULT 6030
            )
        ''')

        # Migration: add gnmi_port to existing databases
        try:
            cursor.execute('ALTER TABLE devices ADD COLUMN gnmi_port INTEGER DEFAULT 6030')
            conn.commit()
        except sqlite3.OperationalError:
            pass  # Column already exists

        # Migration: add polling_enabled to existing databases
        try:
            cursor.execute('ALTER TABLE devices ADD COLUMN polling_enabled BOOLEAN DEFAULT 1')
            conn.commit()
        except sqlite3.OperationalError:
            pass  # Column already exists

        # Migration: add last_backup_at / last_synced_at / agent columns
        for col in ('last_backup_at TIMESTAMP', 'last_synced_at TIMESTAMP',
                    'agent_installed INTEGER DEFAULT 0',
                    'agent_last_checkin TIMESTAMP'):
            try:
                cursor.execute(f'ALTER TABLE devices ADD COLUMN {col}')
                conn.commit()
            except sqlite3.OperationalError:
                pass

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS device_configlets (
                device_hostname TEXT,
                configlet_name TEXT,
                priority INTEGER,
                FOREIGN KEY (device_hostname) REFERENCES devices(hostname)
            )
        ''')

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS device_tags (
                device_hostname TEXT,
                tag_key TEXT,
                tag_value TEXT,
                FOREIGN KEY (device_hostname) REFERENCES devices(hostname)
            )
        ''')

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS device_groups (
                group_id INTEGER PRIMARY KEY AUTOINCREMENT,
                group_name TEXT UNIQUE NOT NULL,
                created_at TEXT DEFAULT (datetime('now'))
            )
        ''')

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS device_group_members (
                group_id INTEGER NOT NULL,
                device_hostname TEXT NOT NULL,
                PRIMARY KEY (group_id, device_hostname),
                FOREIGN KEY (group_id) REFERENCES device_groups(group_id) ON DELETE CASCADE
            )
        ''')

        conn.commit()
        conn.close()

    def add_device(self, device: Device):
        """Add device to inventory"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute('''
            INSERT OR REPLACE INTO devices
            (hostname, ip_address, model, serial_number, eos_version,
             management_type, role, site, container, cvp_managed, gnmi_port, polling_enabled)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            device.hostname,
            device.ip_address,
            device.model,
            device.serial_number,
            device.eos_version,
            device.management_type.value,
            device.role.value,
            device.site,
            device.container,
            device.cvp_managed,
            device.gnmi_port,
            device.polling_enabled,
        ))

        # Add configlets
        cursor.execute('DELETE FROM device_configlets WHERE device_hostname = ?',
                      (device.hostname,))
        for idx, configlet in enumerate(device.configlets):
            cursor.execute('''
                INSERT INTO device_configlets (device_hostname, configlet_name, priority)
                VALUES (?, ?, ?)
            ''', (device.hostname, configlet, idx))

        # Add tags
        cursor.execute('DELETE FROM device_tags WHERE device_hostname = ?',
                      (device.hostname,))
        for key, value in device.tags.items():
            cursor.execute('''
                INSERT INTO device_tags (device_hostname, tag_key, tag_value)
                VALUES (?, ?, ?)
            ''', (device.hostname, key, value))

        conn.commit()
        conn.close()

    def get_device(self, hostname: str) -> Optional[Device]:
        """Get device by hostname"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute('''
            SELECT hostname, ip_address, model, serial_number, eos_version,
                   management_type, role, site, container, cvp_managed, gnmi_port, polling_enabled,
                   last_backup_at, last_synced_at, agent_installed, agent_last_checkin
            FROM devices WHERE hostname = ?
        ''', (hostname,))
        row = cursor.fetchone()

        if not row:
            return None

        # Get configlets
        cursor.execute('''
            SELECT configlet_name FROM device_configlets
            WHERE device_hostname = ? ORDER BY priority
        ''', (hostname,))
        configlets = [r[0] for r in cursor.fetchall()]

        # Get tags
        cursor.execute('''
            SELECT tag_key, tag_value FROM device_tags
            WHERE device_hostname = ?
        ''', (hostname,))
        tags = {r[0]: r[1] for r in cursor.fetchall()}

        conn.close()

        return Device(
            hostname=row[0],
            ip_address=row[1],
            model=row[2],
            serial_number=row[3],
            eos_version=row[4],
            management_type=DeviceType(row[5]),
            role=DeviceRole(row[6]),
            site=row[7],
            container=row[8],
            cvp_managed=bool(row[9]),
            gnmi_port=int(row[10]) if row[10] is not None else 6030,
            polling_enabled=bool(row[11]) if row[11] is not None else True,
            last_backup_at=row[12],
            last_synced_at=row[13],
            agent_installed=bool(row[14]) if row[14] is not None else False,
            agent_last_checkin=row[15],
            configlets=configlets,
            tags=tags
        )

    def get_devices_by_filter(self, **filters) -> List[Device]:
        """Get devices by various filters"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        query = 'SELECT hostname FROM devices WHERE 1=1'
        params = []

        for key, value in filters.items():
            if key in ['site', 'role', 'container', 'management_type', 'cvp_managed']:
                query += f' AND {key} = ?'
                params.append(value)

        cursor.execute(query, params)
        hostnames = [r[0] for r in cursor.fetchall()]
        conn.close()

        return [self.get_device(h) for h in hostnames]

    def list_all_devices(self) -> List[str]:
        """List all device hostnames"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute('SELECT hostname FROM devices ORDER BY hostname')
        hostnames = [r[0] for r in cursor.fetchall()]
        conn.close()
        return hostnames

    def delete_device(self, hostname: str) -> bool:
        """
        Delete a device from inventory

        Args:
            hostname: Device hostname to delete

        Returns:
            True if device was deleted, False if not found
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        try:
            # Check if device exists
            cursor.execute('SELECT hostname FROM devices WHERE hostname = ?', (hostname,))
            if not cursor.fetchone():
                conn.close()
                return False

            # Delete device configlets associations
            cursor.execute('DELETE FROM device_configlets WHERE device_hostname = ?', (hostname,))

            # Delete device tags
            cursor.execute('DELETE FROM device_tags WHERE device_hostname = ?', (hostname,))

            # Delete the device
            cursor.execute('DELETE FROM devices WHERE hostname = ?', (hostname,))

            conn.commit()
            return True

        except Exception as e:
            conn.rollback()
            raise
        finally:
            conn.close()

    def update_device(self, hostname: str, device: Device) -> bool:
        """
        Update an existing device in inventory

        Args:
            hostname: Current hostname of the device
            device: Device object with updated information

        Returns:
            True if device was updated, False if not found
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        try:
            # Check if device exists
            cursor.execute('SELECT hostname FROM devices WHERE hostname = ?', (hostname,))
            if not cursor.fetchone():
                conn.close()
                return False

            # If hostname is changing, we need to handle it specially
            if hostname != device.hostname:
                # Check if new hostname already exists
                cursor.execute('SELECT hostname FROM devices WHERE hostname = ?', (device.hostname,))
                if cursor.fetchone():
                    conn.close()
                    raise ValueError(f"Device with hostname {device.hostname} already exists")

                # Update references in other tables
                cursor.execute('UPDATE device_configlets SET device_hostname = ? WHERE device_hostname = ?',
                             (device.hostname, hostname))
                cursor.execute('UPDATE device_tags SET device_hostname = ? WHERE device_hostname = ?',
                             (device.hostname, hostname))

            # Update device
            cursor.execute('''
                UPDATE devices SET
                    hostname = ?,
                    ip_address = ?,
                    model = ?,
                    serial_number = ?,
                    eos_version = ?,
                    management_type = ?,
                    role = ?,
                    site = ?,
                    container = ?,
                    cvp_managed = ?,
                    gnmi_port = ?,
                    polling_enabled = ?
                WHERE hostname = ?
            ''', (
                device.hostname,
                device.ip_address,
                device.model,
                device.serial_number,
                device.eos_version,
                device.management_type.value,
                device.role.value,
                device.site,
                device.container,
                device.cvp_managed,
                device.gnmi_port,
                device.polling_enabled,
                hostname  # Original hostname for WHERE clause
            ))

            conn.commit()
            return True

        except Exception as e:
            conn.rollback()
            raise
        finally:
            conn.close()

    def update_agent_checkin(self, hostname: str, installed: bool = True):
        """Record a device-agent check-in."""
        conn = sqlite3.connect(self.db_path)
        conn.execute(
            'UPDATE devices SET agent_installed = ?, agent_last_checkin = ? WHERE hostname = ?',
            (1 if installed else 0,
             datetime.utcnow().isoformat(timespec='seconds'),
             hostname)
        )
        conn.commit()
        conn.close()

    def import_from_yaml(self, yaml_file: str):
        """Import inventory from YAML file"""
        with open(yaml_file, 'r') as f:
            data = yaml.safe_load(f)

        for device_data in data.get('devices', []):
            device = Device(
                hostname=device_data['hostname'],
                ip_address=device_data['ip_address'],
                model=device_data.get('model', 'Unknown'),
                serial_number=device_data.get('serial_number', ''),
                eos_version=device_data.get('eos_version', ''),
                management_type=DeviceType(device_data.get('management_type', 'eapi')),
                role=DeviceRole(device_data['role']),
                site=device_data['site'],
                container=device_data.get('container', 'Undefined'),
                cvp_managed=device_data.get('cvp_managed', False),
                configlets=device_data.get('configlets', []),
                tags=device_data.get('tags', {})
            )
            self.add_device(device)

    def export_to_yaml(self, output_file: str):
        """Export inventory to YAML"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute('SELECT hostname FROM devices')
        hostnames = [r[0] for r in cursor.fetchall()]
        conn.close()

        devices = [self.get_device(h).to_dict() for h in hostnames]

        with open(output_file, 'w') as f:
            yaml.dump({'devices': devices}, f, default_flow_style=False)
