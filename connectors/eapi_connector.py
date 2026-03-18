#!/usr/bin/env python3
"""
eAPI Connector
Direct connection to Arista devices using eAPI (pyeapi)
"""

import sys
from typing import List, Dict, Optional

try:
    import pyeapi
    PYEAPI_AVAILABLE = True
except ImportError:
    PYEAPI_AVAILABLE = False
    print("Warning: pyeapi not installed. Install with: pip install pyeapi", file=sys.stderr)


class EAPIConnector:
    def __init__(self, host: str, username: str, password: str,
                 transport: str = 'https', port: int = None, timeout: int = 10):
        if not PYEAPI_AVAILABLE:
            raise ImportError("pyeapi module is required. Install with: pip install pyeapi")

        self.host = host
        self.username = username
        self.password = password
        self.transport = transport
        self.port = port or (443 if transport == 'https' else 80)
        self.timeout = timeout
        self.node = None

    def disconnect(self):
        """Close connection"""
        self.node = None

    def connect(self):
        """Establish connection to device"""
        try:
            # pyeapi.connect() returns a connection object, not a Node
            # We need to wrap it with Node to get access to enable() method
            connection = pyeapi.connect(
                transport=self.transport,
                host=self.host,
                username=self.username,
                password=self.password,
                port=self.port,
                timeout=self.timeout  # HTTP/HTTPS request timeout
            )
            # Wrap the connection with a Node object
            from pyeapi.client import Node
            self.node = Node(connection)
            return True
        except Exception as e:
            print(f"Failed to connect to {self.host}: {e}", file=sys.stderr)
            return False

    def execute_commands(self, commands: List[str], enable: bool = True) -> List[Dict]:
        """Execute list of commands"""
        if not self.node:
            self.connect()

        try:
            if enable:
                result = self.node.enable(commands)
            else:
                result = self.node.execute(commands)
            return result
        except Exception as e:
            print(f"Failed to execute commands: {e}", file=sys.stderr)
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
