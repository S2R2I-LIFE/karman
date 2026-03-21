"""
AgentManager — Karman-Link server-side state

Manages API keys, agent sessions, and the command queue that bridges
the Karman UI to the karman-link agent running on an engineer's laptop.
"""

import hashlib
import json
import secrets
import sqlite3
import time
import uuid
from typing import Dict, List, Optional


class AgentManager:
    def __init__(self, db_path: str):
        self.db_path = db_path
        self._init_tables()

    # ── Schema ────────────────────────────────────────────────────────────────

    def _init_tables(self):
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()

        c.execute('''
            CREATE TABLE IF NOT EXISTS agent_keys (
                key_id       TEXT PRIMARY KEY,
                key_hash     TEXT NOT NULL,
                label        TEXT,
                created_by   TEXT,
                created_at   REAL NOT NULL,
                expires_at   REAL,
                last_used_at REAL,
                revoked      INTEGER DEFAULT 0
            )
        ''')

        c.execute('''
            CREATE TABLE IF NOT EXISTS agent_sessions (
                session_id      TEXT PRIMARY KEY,
                key_id          TEXT,
                engineer        TEXT,
                connected_at    REAL NOT NULL,
                last_heartbeat  REAL,
                disconnected_at REAL,
                switch_ip       TEXT,
                switch_hostname TEXT,
                switch_model    TEXT,
                switch_serial   TEXT,
                switch_eos      TEXT,
                status          TEXT DEFAULT 'connected',
                FOREIGN KEY (key_id) REFERENCES agent_keys(key_id)
            )
        ''')

        c.execute('''
            CREATE TABLE IF NOT EXISTS agent_commands (
                command_id   TEXT PRIMARY KEY,
                session_id   TEXT NOT NULL,
                action       TEXT NOT NULL,
                payload      TEXT,
                created_at   REAL NOT NULL,
                claimed_at   REAL,
                result       TEXT,
                completed_at REAL,
                success      INTEGER,
                FOREIGN KEY (session_id) REFERENCES agent_sessions(session_id)
            )
        ''')

        conn.commit()
        conn.close()

    # ── API key management ────────────────────────────────────────────────────

    def generate_key(self, label: str, created_by: str,
                     expires_days: int = None) -> tuple:
        """
        Generate a new API key.
        Returns (key_id, raw_key) — the raw key is shown once and never stored.
        """
        key_id = str(uuid.uuid4())
        raw_key = secrets.token_hex(32)
        key_hash = hashlib.sha256(raw_key.encode()).hexdigest()
        expires_at = time.time() + expires_days * 86400 if expires_days else None

        conn = sqlite3.connect(self.db_path)
        conn.execute(
            'INSERT INTO agent_keys (key_id, key_hash, label, created_by, created_at, expires_at) '
            'VALUES (?, ?, ?, ?, ?, ?)',
            (key_id, key_hash, label, created_by, time.time(), expires_at)
        )
        conn.commit()
        conn.close()
        return key_id, raw_key

    def validate_key(self, raw_key: str) -> Optional[Dict]:
        """Return the key record if valid and not expired/revoked, else None."""
        key_hash = hashlib.sha256(raw_key.encode()).hexdigest()
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            'SELECT * FROM agent_keys WHERE key_hash = ? AND revoked = 0',
            (key_hash,)
        ).fetchone()
        conn.close()

        if not row:
            return None
        record = dict(row)
        if record['expires_at'] and time.time() > record['expires_at']:
            return None

        # Touch last_used
        conn = sqlite3.connect(self.db_path)
        conn.execute('UPDATE agent_keys SET last_used_at = ? WHERE key_id = ?',
                     (time.time(), record['key_id']))
        conn.commit()
        conn.close()
        return record

    def list_keys(self) -> List[Dict]:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            'SELECT key_id, label, created_by, created_at, expires_at, last_used_at, revoked '
            'FROM agent_keys ORDER BY created_at DESC'
        ).fetchall()
        conn.close()
        return [dict(r) for r in rows]

    def revoke_key(self, key_id: str):
        conn = sqlite3.connect(self.db_path)
        conn.execute('UPDATE agent_keys SET revoked = 1 WHERE key_id = ?', (key_id,))
        conn.commit()
        conn.close()

    # ── Session management ────────────────────────────────────────────────────

    def create_session(self, key_id: str, engineer: str) -> str:
        session_id = str(uuid.uuid4())
        now = time.time()
        conn = sqlite3.connect(self.db_path)
        conn.execute(
            'INSERT INTO agent_sessions '
            '(session_id, key_id, engineer, connected_at, last_heartbeat, status) '
            'VALUES (?, ?, ?, ?, ?, ?)',
            (session_id, key_id, engineer, now, now, 'connected')
        )
        conn.commit()
        conn.close()
        return session_id

    def update_session(self, session_id: str, **kwargs):
        if not kwargs:
            return
        set_clause = ', '.join(f'{k} = ?' for k in kwargs)
        conn = sqlite3.connect(self.db_path)
        conn.execute(
            f'UPDATE agent_sessions SET {set_clause} WHERE session_id = ?',
            list(kwargs.values()) + [session_id]
        )
        conn.commit()
        conn.close()

    def get_session(self, session_id: str) -> Optional[Dict]:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            'SELECT * FROM agent_sessions WHERE session_id = ?', (session_id,)
        ).fetchone()
        conn.close()
        return dict(row) if row else None

    def list_sessions(self, active_only: bool = False) -> List[Dict]:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        if active_only:
            # Sessions with a heartbeat in the last 60 seconds
            cutoff = time.time() - 60
            rows = conn.execute(
                "SELECT * FROM agent_sessions "
                "WHERE status NOT IN ('disconnected', 'error') AND last_heartbeat > ? "
                "ORDER BY connected_at DESC",
                (cutoff,)
            ).fetchall()
        else:
            rows = conn.execute(
                'SELECT * FROM agent_sessions ORDER BY connected_at DESC LIMIT 50'
            ).fetchall()
        conn.close()
        return [dict(r) for r in rows]

    # ── Command queue ─────────────────────────────────────────────────────────

    def queue_command(self, session_id: str, action: str, payload: dict) -> str:
        command_id = str(uuid.uuid4())
        conn = sqlite3.connect(self.db_path)
        conn.execute(
            'INSERT INTO agent_commands (command_id, session_id, action, payload, created_at) '
            'VALUES (?, ?, ?, ?, ?)',
            (command_id, session_id, action, json.dumps(payload), time.time())
        )
        conn.commit()
        conn.close()
        return command_id

    def claim_next_command(self, session_id: str) -> Optional[Dict]:
        """Atomically claim and return the next unclaimed command, or None."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            'SELECT * FROM agent_commands '
            'WHERE session_id = ? AND claimed_at IS NULL '
            'ORDER BY created_at LIMIT 1',
            (session_id,)
        ).fetchone()
        if row:
            conn.execute(
                'UPDATE agent_commands SET claimed_at = ? WHERE command_id = ?',
                (time.time(), row['command_id'])
            )
            conn.commit()
        conn.close()
        return dict(row) if row else None

    def complete_command(self, command_id: str, success: bool, result: dict):
        conn = sqlite3.connect(self.db_path)
        conn.execute(
            'UPDATE agent_commands SET result = ?, completed_at = ?, success = ? '
            'WHERE command_id = ?',
            (json.dumps(result), time.time(), 1 if success else 0, command_id)
        )
        conn.commit()
        conn.close()

    def get_command(self, command_id: str) -> Optional[Dict]:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            'SELECT * FROM agent_commands WHERE command_id = ?', (command_id,)
        ).fetchone()
        conn.close()
        return dict(row) if row else None

    def get_session_commands(self, session_id: str) -> List[Dict]:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            'SELECT command_id, action, payload, created_at, claimed_at, '
            'completed_at, success, result '
            'FROM agent_commands WHERE session_id = ? ORDER BY created_at',
            (session_id,)
        ).fetchall()
        conn.close()
        return [dict(r) for r in rows]

    # ── Ingest sequence ───────────────────────────────────────────────────────

    # Standard commands run against every ingested switch
    INGEST_SEQUENCE = [
        ['show version'],
        ['show interfaces status'],
        ['show lldp neighbors detail'],
        ['show running-config'],
        ['show system environment temperature'],
        ['show ip bgp summary'],
    ]

    def queue_ingest(self, session_id: str, switch_ip: str,
                     username: str = 'admin', password: str = '',
                     port: int = 80, transport: str = 'http') -> List[str]:
        """Queue the full ingest command sequence. Returns list of command IDs."""
        ids = []
        for cmds in self.INGEST_SEQUENCE:
            cid = self.queue_command(session_id, 'execute', {
                'host': switch_ip,
                'port': port,
                'transport': transport,
                'username': username,
                'password': password,
                'commands': cmds,
            })
            ids.append(cid)
        return ids

    def queue_provision_new(self, session_id: str, switch_ip: str,
                            mgmt_ip: str, prefix_len: str, gateway: str,
                            new_password: str = '',
                            vrf: str = 'default',
                            enable_eapi: bool = True,
                            enable_ssh: bool = True,
                            enable_terminattr: bool = False,
                            extra_config: str = '') -> List[str]:
        """
        Queue config-mode commands to bootstrap a factory-reset switch.
        Connects using factory defaults (admin / no password / HTTP port 80).
        Returns list of queued command IDs.
        """
        cmds = []

        # Set admin password if requested
        if new_password:
            cmds.append(f'username admin privilege 15 secret 0 {new_password}')

        # VRF instance (if non-default)
        if vrf and vrf != 'default':
            cmds.append(f'vrf instance {vrf}')

        # Management interface
        cmds.append('interface Management0')
        if vrf and vrf != 'default':
            cmds.append(f'   vrf {vrf}')
        cmds.append(f'   ip address {mgmt_ip}/{prefix_len}')

        # Default route
        if vrf and vrf != 'default':
            cmds.append(f'ip route vrf {vrf} 0.0.0.0/0 {gateway}')
        else:
            cmds.append(f'ip route 0.0.0.0/0 {gateway}')

        # eAPI
        if enable_eapi:
            cmds += ['management api http-commands', '   protocol https', '   no shutdown']
            if vrf and vrf != 'default':
                cmds.append(f'   vrf {vrf}')

        # SSH
        if enable_ssh:
            cmds += ['management ssh', '   idle-timeout 60', '   no shutdown']
            if vrf and vrf != 'default':
                cmds.append(f'   vrf {vrf}')

        # TerminAttr
        if enable_terminattr:
            vrf_label = vrf if (vrf and vrf != 'default') else 'default'
            cmds += [
                'daemon TerminAttr',
                f'   exec /usr/bin/TerminAttr -grpcaddr={vrf_label}/0.0.0.0:6030 -disableaaa',
                '   no shutdown',
            ]

        # User-supplied extra lines
        for line in (extra_config or '').strip().splitlines():
            stripped = line.strip()
            if stripped:
                cmds.append(stripped)

        ids = []
        # Push configuration (factory creds, HTTP)
        ids.append(self.queue_command(session_id, 'configure', {
            'host': switch_ip,
            'port': 80,
            'transport': 'http',
            'username': 'admin',
            'password': '',
            'commands': cmds,
        }))
        # Persist to startup-config
        ids.append(self.queue_command(session_id, 'execute', {
            'host': switch_ip,
            'port': 80,
            'transport': 'http',
            'username': 'admin',
            'password': '',
            'commands': ['write memory'],
        }))
        return ids

    def queue_adopt(self, session_id: str, switch_ip: str,
                    username: str = 'admin', password: str = '',
                    port: int = 443, transport: str = 'https',
                    vrf: str = 'default',
                    enable_eapi: bool = True,
                    enable_ssh: bool = True,
                    enable_terminattr: bool = False) -> List[str]:
        """
        Queue adoption config for a switch that is already on the network.
        Pushes only what's needed for Kármán telemetry (eAPI / SSH / TerminAttr).
        Returns list of queued command IDs.
        """
        cmds = []

        if enable_eapi:
            cmds += ['management api http-commands', '   protocol https', '   no shutdown']
            if vrf and vrf != 'default':
                cmds.append(f'   vrf {vrf}')

        if enable_ssh:
            cmds += ['management ssh', '   idle-timeout 60', '   no shutdown']
            if vrf and vrf != 'default':
                cmds.append(f'   vrf {vrf}')

        if enable_terminattr:
            vrf_label = vrf if (vrf and vrf != 'default') else 'default'
            cmds += [
                'daemon TerminAttr',
                f'   exec /usr/bin/TerminAttr -grpcaddr={vrf_label}/0.0.0.0:6030 -disableaaa',
                '   no shutdown',
            ]

        if not cmds:
            return []

        ids = []
        ids.append(self.queue_command(session_id, 'configure', {
            'host': switch_ip,
            'port': port,
            'transport': transport,
            'username': username,
            'password': password,
            'commands': cmds,
        }))
        ids.append(self.queue_command(session_id, 'execute', {
            'host': switch_ip,
            'port': port,
            'transport': transport,
            'username': username,
            'password': password,
            'commands': ['write memory'],
        }))
        return ids
