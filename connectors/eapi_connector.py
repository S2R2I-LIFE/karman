#!/usr/bin/env python3
"""
eAPI Connector
Direct connection to Arista devices using eAPI (pyeapi)
"""

import socket
import sys
from typing import List, Dict, Optional

try:
    import pyeapi
    PYEAPI_AVAILABLE = True
except ImportError:
    PYEAPI_AVAILABLE = False
    print("Warning: pyeapi not installed. Install with: pip install pyeapi", file=sys.stderr)

# In-process cache: ip → 'http' or 'https' (avoids repeated SSL timeouts per process lifetime)
_TRANSPORT_CACHE: Dict[str, str] = {}


class EAPIConnector:
    def __init__(self, host: str, username: str, password: str,
                 transport: str = 'https', port: int = None, timeout: int = 10):
        if not PYEAPI_AVAILABLE:
            raise ImportError("pyeapi module is required. Install with: pip install pyeapi")

        self.host = host
        self.username = username
        self.password = password
        # Use cached transport if we've already discovered the working one for this host
        self.transport = _TRANSPORT_CACHE.get(host, transport)
        self.port = port or (443 if self.transport == 'https' else 80)
        self.timeout = timeout
        self.node = None

    def disconnect(self):
        """Close connection"""
        self.node = None

    def connect(self):
        """Establish connection to device.

        pyeapi.connect() is intentionally lazy — it creates connection objects
        without opening a socket.  The actual TCP/SSL connection happens on the
        first execute_commands() call, where transport fallback is handled.
        This method always returns True so that callers can proceed to send
        commands and let failures be handled gracefully there.

        When transport is 'https' and no cached transport exists, we use a short
        (3s) probe timeout on the first call so SSL failures are detected quickly
        before falling back to HTTP.
        """
        try:
            # If we're in HTTPS mode and haven't yet discovered the working transport
            # for this host, build the initial node with a 3s probe timeout so
            # SSL handshake failures don't burn the full timeout.
            probe_timeout = self.timeout
            if self.transport == 'https' and self.host not in _TRANSPORT_CACHE:
                probe_timeout = 3

            self.node = self._build_node(self.transport, self.port, timeout=probe_timeout)
            return True
        except Exception as e:
            print(f"Failed to connect to {self.host}: {e}", file=sys.stderr)
            return False

    def _build_node(self, transport: str, port: int, timeout: int = None):
        """Build a pyeapi Node for the given transport/port."""
        from pyeapi.client import Node
        connection = pyeapi.connect(
            transport=transport,
            host=self.host,
            username=self.username,
            password=self.password,
            port=port,
            timeout=timeout if timeout is not None else self.timeout,
        )
        return Node(connection)

    def execute_commands(self, commands: List[str], enable: bool = True) -> List[Dict]:
        """Execute list of commands, falling back from HTTPS to HTTP on SSL failure."""
        if not self.node:
            self.connect()

        def _run(node):
            if enable:
                return node.enable(commands)
            return node.execute(commands)

        try:
            return _run(self.node)
        except Exception as e:
            err = str(e).lower()
            # SSL handshake timeout or SSL error → retry over plain HTTP
            ssl_error = self.transport == 'https' and any(
                kw in err for kw in ('timed out', 'ssl', 'handshake', 'certificate', 'wrong version')
            )
            if ssl_error:
                print(f"HTTPS failed for {self.host} ({e}), retrying over HTTP", file=sys.stderr)
                try:
                    http_node = self._build_node('http', 80)
                    result = _run(http_node)
                    # Cache the working transport so future instances skip the HTTPS probe
                    self.transport = 'http'
                    self.port = 80
                    self.node = http_node
                    _TRANSPORT_CACHE[self.host] = 'http'
                    return result
                except Exception as e2:
                    print(f"HTTP fallback also failed for {self.host}: {e2}", file=sys.stderr)
                    return []
            print(f"Failed to execute commands on {self.host}: {e}", file=sys.stderr)
            return []

    def get_running_config(self) -> str:
        """Get running configuration"""
        result = self.execute_commands(['show running-config'])
        if result:
            return result[0]['result']['output']
        return ""

    def apply_config(self, config_lines: List[str], session: str = None) -> bool:
        """Apply configuration to device"""
        if not self.node:
            self.connect()

        try:
            if session:
                # Use configuration session
                commands = [f'configure session {session}'] + config_lines
                self.node.config(commands)
            else:
                # Direct configuration
                self.node.config(config_lines)
            return True
        except Exception as e:
            print(f"Failed to apply configuration: {e}", file=sys.stderr)
            return False

    def get_device_info(self) -> Dict:
        """Get basic device information"""
        try:
            result = self.execute_commands(['show version'])
            if result and len(result) > 0:
                # Handle different response structures
                if isinstance(result[0], dict):
                    if 'result' in result[0]:
                        return result[0]['result']
                    else:
                        return result[0]
                return {}
            return {}
        except Exception as e:
            print(f"Error getting device info: {e}", file=sys.stderr)
            return {}

    def get_interfaces(self) -> Dict:
        """Get interface status"""
        result = self.execute_commands(['show interfaces status'])
        if result:
            return result[0]['result']
        return {}

    def save_config(self) -> bool:
        """Save running config to startup config"""
        try:
            self.execute_commands(['copy running-config startup-config'])
            return True
        except Exception as e:
            print(f"Failed to save configuration: {e}", file=sys.stderr)
            return False

    def create_checkpoint(self, checkpoint_name: str) -> bool:
        """Create configuration checkpoint"""
        try:
            self.execute_commands([f'copy running-config flash:{checkpoint_name}.cfg'])
            return True
        except Exception as e:
            print(f"Failed to create checkpoint: {e}", file=sys.stderr)
            return False

    def diff_config(self, config_file: str) -> str:
        """Show diff between running config and file"""
        result = self.execute_commands([f'show session-config named {config_file} diffs'])
        if result:
            return result[0]['result']['output']
        return ""
