#!/usr/bin/env python3
"""
karman-link — Karman Local Agent

Bridges an unprovisioned or factory-reset Arista switch to the Karman
management platform.  Run this on any laptop that is directly cabled to
the switch's management port.

Usage:
    python karman_link.py --server https://karman.example.com --key <api_key>

    Optional flags:
      --switch-ip  192.168.0.1   Override auto-discovery (use a known IP)
      --interface  eth0          Ethernet interface connected to the switch
      --debug                    Enable verbose logging

Requirements:
    pip install -r requirements.txt
    (requests, pyeapi)
"""

import argparse
import json
import logging
import signal
import sys
import time

import requests
import urllib3

# Suppress SSL warnings — factory-reset switches have no valid certificate
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# ── Logging ────────────────────────────────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s  %(levelname)-7s  %(message)s',
    datefmt='%H:%M:%S',
)
log = logging.getLogger('karman-link')

# ── Switch discovery constants ─────────────────────────────────────────────────

# Arista factory-reset switches default to 192.168.0.1 on Management0.
# HTTP is tried first because factory images have no TLS certificate.
FACTORY_TARGETS = [
    ('192.168.0.1', 80,  'http'),
    ('192.168.0.1', 443, 'https'),
    ('192.168.1.1', 80,  'http'),
]


# ── Switch communication ───────────────────────────────────────────────────────

def _eapi_call(host: str, port: int, transport: str,
               username: str, password: str, commands: list,
               timeout: int = 30) -> tuple:
    """
    Execute eAPI enable-mode commands.
    Returns (success, results_list, error_string).
    """
    try:
        import pyeapi
        from pyeapi.client import Node

        conn = pyeapi.connect(
            transport=transport, host=host,
            username=username, password=password,
            port=port, timeout=timeout,
        )
        node = Node(conn)
        raw = node.enable(commands)

        results = []
        for item in raw:
            if not isinstance(item, dict):
                continue
            r = item.get('result', {})
            results.append({
                'command': item.get('command', ''),
                'result': r if isinstance(r, dict) else {'output': str(r)},
            })
        return True, results, None

    except Exception as exc:
        return False, [], str(exc)


def _eapi_config(host: str, port: int, transport: str,
                 username: str, password: str, commands: list,
                 timeout: int = 60) -> tuple:
    """
    Push configuration-mode commands via eAPI.
    Wraps commands in configure / end automatically via pyeapi node.config().
    Returns (success, results_list, error_string).
    """
    try:
        import pyeapi
        from pyeapi.client import Node

        conn = pyeapi.connect(
            transport=transport, host=host,
            username=username, password=password,
            port=port, timeout=timeout,
        )
        node = Node(conn)
        raw = node.config(commands)

        # node.config() returns a list of response dicts (one per command)
        results = []
        for cmd, resp in zip(commands, raw if raw else []):
            results.append({
                'command': cmd,
                'result': resp if isinstance(resp, dict) else {'output': str(resp)},
            })
        return True, results, None

    except Exception as exc:
        return False, [], str(exc)


def discover_switch(override_ip: str = None) -> dict:
    """
    Try to find a switch on the local network.
    Returns a dict with connection details, or {} if nothing found.
    """
    if override_ip:
        targets = [(override_ip, 80, 'http'), (override_ip, 443, 'https')]
    else:
        targets = FACTORY_TARGETS

    for ip, port, transport in targets:
        log.info(f"  Trying {transport}://{ip}:{port} ...")
        ok, results, err = _eapi_call(
            ip, port, transport, 'admin', '', ['show version'], timeout=5
        )
        if ok and results:
            rv = results[0].get('result', {})
            model   = rv.get('modelName', 'Unknown')
            version = rv.get('version', '?')
            serial  = rv.get('serialNumber', '')
            hostname = rv.get('hostname', '')
            log.info(f"  ✓ Found: {model}  EOS {version}  ({ip})")
            return {
                'switch_ip':  ip,
                'port':       port,
                'transport':  transport,
                'username':   'admin',
                'password':   '',
                'model':      model,
                'serial':     serial,
                'hostname':   hostname,
                'eos_version': version,
            }
        log.debug(f"  {ip}:{port} — {err}")

    return {}


# ── Karman-Link agent ──────────────────────────────────────────────────────────

class KarmanLink:
    def __init__(self, server_url: str, api_key: str, switch_ip: str = None):
        self.server     = server_url.rstrip('/')
        self.api_key    = api_key
        self.switch_ip  = switch_ip   # None = auto-discover
        self.session_id = None
        self.switch_info: dict = {}
        self._running   = True

        signal.signal(signal.SIGINT,  self._on_shutdown)
        signal.signal(signal.SIGTERM, self._on_shutdown)

    # ── Shutdown ───────────────────────────────────────────────────────────────

    def _on_shutdown(self, sig, frame):
        log.info("Shutting down karman-link...")
        self._running = False
        if self.session_id:
            try:
                self._post(f'/api/agent/sessions/{self.session_id}/disconnect')
            except Exception:
                pass
        sys.exit(0)

    # ── HTTP helpers ───────────────────────────────────────────────────────────

    def _post(self, path: str, data: dict = None, timeout: int = 10) -> dict:
        try:
            r = requests.post(
                f'{self.server}{path}',
                json=data or {},
                timeout=timeout,
                verify=False,
            )
            r.raise_for_status()
            return r.json()
        except requests.exceptions.HTTPError as exc:
            log.error(f'POST {path} → HTTP {exc.response.status_code}: {exc.response.text[:120]}')
            return {}
        except Exception as exc:
            log.error(f'POST {path} failed: {exc}')
            return {}

    def _get(self, path: str, timeout: int = 10) -> dict:
        try:
            r = requests.get(
                f'{self.server}{path}',
                timeout=timeout,
                verify=False,
            )
            r.raise_for_status()
            return r.json()
        except Exception as exc:
            log.error(f'GET {path} failed: {exc}')
            return {}

    # ── Connection & discovery ─────────────────────────────────────────────────

    def connect(self) -> bool:
        log.info(f"Connecting to Karman at {self.server} ...")
        resp = self._post('/api/agent/connect', {
            'api_key': self.api_key,
            'version': '1.0',
        })
        if 'error' in resp:
            log.error(f"Connection rejected: {resp['error']}")
            return False

        self.session_id = resp.get('session_id')
        log.info(f"✓ Connected  (session {self.session_id[:8]}...)")
        return True

    def discover(self) -> bool:
        log.info("Looking for switch ...")
        self.switch_info = discover_switch(override_ip=self.switch_ip)

        if not self.switch_info:
            log.warning(
                "No switch found on default factory IPs.\n"
                "  • Check the ethernet cable is plugged into Management0\n"
                "  • Confirm the switch is factory-reset (or pass --switch-ip)"
            )
            self._post(f'/api/agent/sessions/{self.session_id}/status',
                       {'status': 'no_switch'})
            return False

        self._post(f'/api/agent/sessions/{self.session_id}/status', {
            'switch_ip':       self.switch_info['switch_ip'],
            'switch_hostname': self.switch_info.get('hostname', ''),
            'switch_model':    self.switch_info.get('model', ''),
            'switch_serial':   self.switch_info.get('serial', ''),
            'switch_eos':      self.switch_info.get('eos_version', ''),
            'status':          'ready',
        })
        log.info("Switch reported to Karman — waiting for ingest command in the UI ...")
        return True

    # ── Command execution ──────────────────────────────────────────────────────

    def _conn_params(self, payload: dict) -> tuple:
        """Resolve host/port/transport/creds from payload, falling back to discovered info."""
        host      = payload.get('host')      or self.switch_info.get('switch_ip', '')
        port      = payload.get('port')      or self.switch_info.get('port', 80)
        transport = payload.get('transport') or self.switch_info.get('transport', 'http')
        username  = payload.get('username',  self.switch_info.get('username', 'admin'))
        password  = payload.get('password',  self.switch_info.get('password', ''))
        return host, int(port), transport, username, password

    def _post_result(self, command_id: str, success: bool, results: list, error: str):
        self._post(f'/api/agent/sessions/{self.session_id}/result', {
            'command_id': command_id,
            'success':    success,
            'result':     results,
            'error':      error or '',
        })

    def _handle_execute(self, cmd: dict):
        """Run enable-mode commands (show commands, write memory, etc.)."""
        command_id              = cmd['command_id']
        payload                 = cmd.get('payload', {})
        host, port, transport, username, password = self._conn_params(payload)
        commands                = payload.get('commands', [])

        log.info(f"  [execute] {commands}  →  {host}")
        success, results, error = _eapi_call(
            host, port, transport, username, password, commands
        )
        self._post_result(command_id, success, results, error)
        log.info(f"  {'✓ OK' if success else '✗ ' + str(error)}")

    def _handle_configure(self, cmd: dict):
        """Push configuration-mode commands to the switch."""
        command_id              = cmd['command_id']
        payload                 = cmd.get('payload', {})
        host, port, transport, username, password = self._conn_params(payload)
        commands                = payload.get('commands', [])

        log.info(f"  [configure] {len(commands)} lines  →  {host}")
        success, results, error = _eapi_config(
            host, port, transport, username, password, commands
        )
        self._post_result(command_id, success, results, error)
        log.info(f"  {'✓ Configuration applied' if success else '✗ ' + str(error)}")

    # ── Main polling loop ──────────────────────────────────────────────────────

    def run(self):
        if not self.connect():
            return

        self.discover()

        last_heartbeat = time.time()
        log.info("Polling for commands (Ctrl-C to quit) ...")

        while self._running:
            # Heartbeat
            if time.time() - last_heartbeat >= 15:
                self._post(f'/api/agent/sessions/{self.session_id}/heartbeat')
                last_heartbeat = time.time()

            # Poll for next command
            cmd = self._get(f'/api/agent/sessions/{self.session_id}/next-command')

            action = cmd.get('action')
            if action == 'execute':
                self._handle_execute(cmd)
            elif action == 'configure':
                self._handle_configure(cmd)
            elif action == 'wait' or not action:
                time.sleep(3)
            else:
                log.warning(f"Unknown action '{action}' — skipping")
                time.sleep(3)


# ── Entry point ────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description='karman-link — bridges a local switch to the Karman platform'
    )
    parser.add_argument(
        '--server', required=True,
        help='Karman server URL, e.g. https://karman.example.com or http://10.0.0.1:5000'
    )
    parser.add_argument(
        '--key', required=True,
        help='API key generated in Karman Admin → Agent Keys'
    )
    parser.add_argument(
        '--switch-ip', default=None,
        help='Override switch IP (default: auto-discover from 192.168.0.1)'
    )
    parser.add_argument(
        '--debug', action='store_true',
        help='Enable verbose debug logging'
    )
    args = parser.parse_args()

    if args.debug:
        logging.getLogger().setLevel(logging.DEBUG)

    agent = KarmanLink(
        server_url=args.server,
        api_key=args.key,
        switch_ip=args.switch_ip,
    )
    agent.run()


if __name__ == '__main__':
    main()
