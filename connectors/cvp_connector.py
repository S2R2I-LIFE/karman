#!/usr/bin/env python3
"""
CVP Connector
Connection to Arista CloudVision Portal (CVP) for the CVP-managed devices
"""

import sys
from typing import List, Dict, Optional

try:
    from cvprac.cvp_client import CvpClient
    CVPRAC_AVAILABLE = True
except ImportError:
    CVPRAC_AVAILABLE = False
    print("Warning: cvprac not installed. Install with: pip install cvprac", file=sys.stderr)


class CVPConnector:
    def __init__(self, cvp_host: str, username: str, password: str):
        if not CVPRAC_AVAILABLE:
            raise ImportError("cvprac module is required. Install with: pip install cvprac")

        self.cvp_host = cvp_host
        self.username = username
        self.password = password
        self.client = CvpClient()

    def connect(self):
        """Establish connection to CVP"""
        try:
            self.client.connect([self.cvp_host], self.username, self.password)
            return True
        except Exception as e:
            print(f"Failed to connect to CVP: {e}", file=sys.stderr)
            return False

    def get_devices(self) -> List[Dict]:
        """Get all devices from CVP inventory"""
        try:
            inventory = self.client.api.get_inventory()
            return inventory
        except Exception as e:
            print(f"Failed to get devices: {e}", file=sys.stderr)
            return []

    def get_device_by_name(self, device_name: str) -> Optional[Dict]:
        """Get specific device by name"""
        try:
            device = self.client.api.get_device_by_name(device_name)
            return device
        except Exception as e:
            print(f"Failed to get device {device_name}: {e}", file=sys.stderr)
            return None

    def get_configlets(self) -> List[Dict]:
        """Get all configlets from CVP"""
        try:
            configlets = self.client.api.get_configlets()
            return configlets['data']
        except Exception as e:
            print(f"Failed to get configlets: {e}", file=sys.stderr)
            return []

    def create_configlet(self, name: str, config: str) -> bool:
        """Create a new configlet in CVP"""
        try:
            self.client.api.add_configlet(name, config)
            return True
        except Exception as e:
            print(f"Failed to create configlet: {e}", file=sys.stderr)
            return False

    def update_configlet(self, name: str, config: str, key: str) -> bool:
        """Update existing configlet"""
        try:
            self.client.api.update_configlet(config, key, name)
            return True
        except Exception as e:
            print(f"Failed to update configlet: {e}", file=sys.stderr)
            return False

    def apply_configlet_to_device(self, device_name: str, configlet_name: str) -> bool:
        """Apply configlet to a device"""
        try:
            device = self.get_device_by_name(device_name)
            if not device:
                return False

            # Get configlet
            configlets = self.get_configlets()
            configlet = next((c for c in configlets if c['name'] == configlet_name), None)
            if not configlet:
                print(f"Configlet {configlet_name} not found")
                return False

            # Create task to apply configlet
            self.client.api.apply_configlets_to_device(
                device['name'],
                device,
                [configlet]
            )
            return True
        except Exception as e:
            print(f"Failed to apply configlet: {e}", file=sys.stderr)
            return False

    def create_change_control(self, name: str, tasks: List[str]) -> Optional[str]:
        """Create change control with tasks"""
        try:
            cc = self.client.api.add_change_control(name, tasks)
            return cc['id']
        except Exception as e:
            print(f"Failed to create change control: {e}", file=sys.stderr)
            return None

    def execute_change_control(self, cc_id: str) -> bool:
        """Execute a change control"""
        try:
            self.client.api.execute_change_control(cc_id)
            return True
        except Exception as e:
            print(f"Failed to execute change control: {e}", file=sys.stderr)
            return False
