#!/usr/bin/env python3
"""Test if web app can see configlets"""

import sys
import os
from pathlib import Path

# Add parent directory to path (same as web/app.py does)
sys.path.insert(0, str(Path(__file__).parent))

from core.configlet import ConfigletManager

# Use same DB path as web app
DB_PATH = os.path.join(Path(__file__).parent, 'custom-cvp.db')

print(f"Database path: {DB_PATH}")
print(f"Database exists: {os.path.exists(DB_PATH)}")

configlet_mgr = ConfigletManager(DB_PATH)
configlet_names = configlet_mgr.list_configlets()

print(f"\nTotal configlets: {len(configlet_names)}")
print("\nAll configlets:")
for i, name in enumerate(configlet_names, 1):
    cfg = configlet_mgr.get_configlet(name)
    if cfg:
        print(f"{i}. {cfg.name} ({cfg.configlet_type}) - {cfg.description[:50] if cfg.description else 'No description'}")

# Test what the web app does
configlets_list = []
for name in configlet_names:
    cfg = configlet_mgr.get_configlet(name)
    if cfg:
        configlets_list.append({
            'name': cfg.name,
            'type': cfg.configlet_type,
            'description': cfg.description,
            'lines': len(cfg.config.split('\n'))
        })

print(f"\nConfiglets list for web app: {len(configlets_list)} items")
