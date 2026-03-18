#!/usr/bin/env python3
"""
Netmiko Connector
SSH connection to Arista devices using Netmiko (fallback option)
"""

import sys
from typing import List, Dict, Optional

try:
    from netmiko import ConnectHandler
    NETMIKO_AVAILABLE = True
except ImportError:
    NETMIKO_AVAILABLE = False
    print("Warning: netmiko not installed. Install with: pip install netmiko", file=sys.stderr)


class NetmikoConnector:
    def __init__(self, host: str, username: str, password: str,
                 secret: str = None, port: int = 22, timeout: int = 10):
        if not NETMIKO_AVAILABLE:
            raise ImportError("netmiko module is required. Install with: pip install netmiko")

        self.device = {
            'device_type': 'arista_eos',
            'host': host,
            'username': username,
            'password': password,
            'secret': secret or password,
            'port': port,
            'conn_timeout': timeout,  # TCP connection timeout
            'auth_timeout': timeout,  # Authentication timeout
            'timeout': timeout,       # General timeout
            'session_timeout': timeout * 2,  # Session timeout (slightly longer)
            'blocking_timeout': timeout,  # Blocking operations timeout
            'banner_timeout': 5,      # Fast banner timeout
        }
        self.connection = None

    def connect(self):
        """Establish SSH connection to device"""
        try:
            self.connection = ConnectHandler(**self.device)
            return True
        except Exception as e:
            print(f"Failed to connect to {self.device['host']}: {e}", file=sys.stderr)
            return False

    def disconnect(self):
        """Close SSH connection"""
        if self.connection:
            self.connection.disconnect()

    def execute_command(self, command: str, timeout: int = 30) -> str:
        """Execute single command"""
        if not self.connection:
            self.connect()

        try:
            output = self.connection.send_command(command, read_timeout=timeout)
            return output
        except Exception as e:
            print(f"Failed to execute command '{command}': {e}", file=sys.stderr)
            return ""

    def execute_commands(self, commands: List[str]) -> List[str]:
        """Execute multiple commands"""
        results = []
        for cmd in commands:
            result = self.execute_command(cmd)
            results.append(result)
        return results

    def get_running_config(self) -> str:
        """Get running configuration"""
        return self.execute_command('show running-config')

    def apply_config(self, config_lines: List[str]) -> bool:
        """Apply configuration to device"""
        if not self.connection:
            self.connect()

        try:
            output = self.connection.send_config_set(config_lines)
            return True
        except Exception as e:
            print(f"Failed to apply configuration: {e}", file=sys.stderr)
            return False

    def save_config(self) -> bool:
        """Save running config to startup config"""
        try:
            output = self.connection.save_config()
            return True
        except Exception as e:
            print(f"Failed to save configuration: {e}", file=sys.stderr)
            return False

    def get_device_info(self) -> str:
        """Get basic device information"""
        return self.execute_command('show version')

    def enter_config_mode(self):
        """Enter configuration mode"""
        if self.connection:
            self.connection.config_mode()

    def exit_config_mode(self):
        """Exit configuration mode"""
        if self.connection:
            self.connection.exit_config_mode()
