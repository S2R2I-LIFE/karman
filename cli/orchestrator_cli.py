#!/usr/bin/env python3
"""
Kármán Orchestrator CLI
Main command-line interface for managing Arista devices
"""

import sys
import argparse
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from core.inventory import InventoryManager, Device, DeviceType, DeviceRole
from core.configlet import ConfigletManager, Configlet
from core.task import TaskManager, TaskType, TaskStatus
from builder import ConfigletBuilder
from validator import ConfigValidator


class OrchestratorCLI:
    def __init__(self, db_path='custom-cvp.db'):
        self.inventory = InventoryManager(db_path)
        self.configlets = ConfigletManager(db_path)
        self.tasks = TaskManager(db_path)
        self.builder = ConfigletBuilder()
        self.validator = ConfigValidator()

    def inventory_list(self, args):
        """List all devices in inventory"""
        devices = self.inventory.list_all_devices()
        print(f"\nTotal devices: {len(devices)}")
        print("-" * 80)
        for hostname in devices:
            device = self.inventory.get_device(hostname)
            print(f"{device.hostname:20} | {device.ip_address:15} | {device.role.value:10} | "
                  f"{device.site:15} | CVP: {device.cvp_managed}")

    def inventory_add(self, args):
        """Add device to inventory"""
        device = Device(
            hostname=args.hostname,
            ip_address=args.ip,
            model=args.model or "Unknown",
            serial_number=args.serial or "",
            eos_version=args.eos_version or "",
            management_type=DeviceType(args.mgmt_type),
            role=DeviceRole(args.role),
            site=args.site,
            container=args.container or "Undefined",
            cvp_managed=args.cvp_managed
        )
        self.inventory.add_device(device)
        print(f"✓ Added device: {args.hostname}")

    def inventory_import(self, args):
        """Import inventory from YAML file"""
        self.inventory.import_from_yaml(args.file)
        print(f"✓ Imported inventory from {args.file}")

    def inventory_export(self, args):
        """Export inventory to YAML file"""
        self.inventory.export_to_yaml(args.file)
        print(f"✓ Exported inventory to {args.file}")

    def configlet_list(self, args):
        """List all configlets"""
        configlets = self.configlets.list_configlets()
        print(f"\nTotal configlets: {len(configlets)}")
        print("-" * 80)
        for name in configlets:
            configlet = self.configlets.get_configlet(name)
            print(f"{configlet.name:30} | Type: {configlet.configlet_type:10} | "
                  f"Lines: {len(configlet.config.split(chr(10)))}")

    def configlet_create(self, args):
        """Create new configlet"""
        with open(args.file, 'r') as f:
            config = f.read()

        configlet = Configlet(
            name=args.name,
            config=config,
            description=args.description or "",
            configlet_type=args.type or "static"
        )
        self.configlets.create_configlet(configlet, author=args.author or "cli")
        print(f"✓ Created configlet: {args.name}")

    def configlet_update(self, args):
        """Update existing configlet"""
        with open(args.file, 'r') as f:
            config = f.read()

        self.configlets.update_configlet(
            args.name,
            config,
            author=args.author or "cli",
            reason=args.reason or "Updated via CLI"
        )
        print(f"✓ Updated configlet: {args.name}")

    def configlet_show(self, args):
        """Show configlet content"""
        configlet = self.configlets.get_configlet(args.name)
        if configlet:
            print(f"\nConfiglet: {configlet.name}")
            print("=" * 80)
            print(configlet.config)
        else:
            print(f"✗ Configlet {args.name} not found")

    def configlet_history(self, args):
        """Show configlet history"""
        history = self.configlets.get_configlet_history(args.name)
        print(f"\nHistory for configlet: {args.name}")
        print("-" * 80)
        for entry in history:
            print(f"Version {entry['version']} | {entry['changed_at']} | "
                  f"By: {entry['changed_by']} | {entry['reason']}")

    def build_config(self, args):
        """Build configuration from templates"""
        try:
            if args.bulk:
                self.builder.build_bulk(args.bulk, args.templates)
            else:
                self.builder.build_configlet(args.device, args.templates, args.output)
        except Exception as e:
            print(f"✗ Build failed: {e}")
            sys.exit(1)

    def validate_vars(self, args):
        """Validate variable file"""
        valid = self.validator.validate_device_vars(args.file)
        sys.exit(0 if valid else 1)

    def validate_config(self, args):
        """Validate configuration file"""
        valid = self.validator.validate_config_syntax(args.file)
        sys.exit(0 if valid else 1)

    def task_list(self, args):
        """List tasks"""
        status = TaskStatus(args.status) if args.status else None
        tasks = self.tasks.list_tasks(status)
        print(f"\nTotal tasks: {len(tasks)}")
        print("-" * 80)
        for task in tasks:
            print(f"ID: {task['task_id']:4} | {task['status']:12} | {task['task_type']:20} | "
                  f"{task['description'][:40]}")

    def task_show(self, args):
        """Show task details"""
        task = self.tasks.get_task(args.task_id)
        if task:
            print(f"\nTask ID: {task['task_id']}")
            print("=" * 80)
            print(f"Type: {task['task_type']}")
            print(f"Status: {task['status']}")
            print(f"Description: {task['description']}")
            print(f"Created: {task['created_at']} by {task['created_by']}")
            print(f"Devices: {', '.join(task['devices'])}")
            print("\nLogs:")
            logs = self.tasks.get_task_logs(args.task_id)
            for log in logs:
                print(f"  [{log['timestamp']}] {log['device']} - {log['log_level']}: {log['message']}")
        else:
            print(f"✗ Task {args.task_id} not found")

    def task_create(self, args):
        """Create new task"""
        devices = args.devices.split(',')
        config_changes = {}  # Would load from file in production

        task_id = self.tasks.create_task(
            TaskType(args.type),
            devices,
            args.description,
            config_changes,
            created_by=args.author or "cli"
        )
        print(f"✓ Created task ID: {task_id}")


def main():
    parser = argparse.ArgumentParser(
        description='Kármán Orchestrator CLI',
        formatter_class=argparse.RawDescriptionHelpFormatter
    )

    subparsers = parser.add_subparsers(dest='command', help='Commands')

    # Inventory commands
    inv_parser = subparsers.add_parser('inventory', help='Inventory management')
    inv_subparsers = inv_parser.add_subparsers(dest='subcommand')

    inv_list = inv_subparsers.add_parser('list', help='List devices')

    inv_add = inv_subparsers.add_parser('add', help='Add device')
    inv_add.add_argument('--hostname', required=True)
    inv_add.add_argument('--ip', required=True)
    inv_add.add_argument('--role', required=True, choices=['spine', 'leaf', 'border', 'core', 'access'])
    inv_add.add_argument('--site', required=True)
    inv_add.add_argument('--mgmt-type', default='eapi', choices=['cvp', 'eapi', 'ssh'])
    inv_add.add_argument('--model')
    inv_add.add_argument('--serial')
    inv_add.add_argument('--eos-version')
    inv_add.add_argument('--container')
    inv_add.add_argument('--cvp-managed', action='store_true')

    inv_import = inv_subparsers.add_parser('import', help='Import from YAML')
    inv_import.add_argument('file')

    inv_export = inv_subparsers.add_parser('export', help='Export to YAML')
    inv_export.add_argument('file')

    # Configlet commands
    cfg_parser = subparsers.add_parser('configlet', help='Configlet management')
    cfg_subparsers = cfg_parser.add_subparsers(dest='subcommand')

    cfg_list = cfg_subparsers.add_parser('list', help='List configlets')

    cfg_create = cfg_subparsers.add_parser('create', help='Create configlet')
    cfg_create.add_argument('--name', required=True)
    cfg_create.add_argument('--file', required=True)
    cfg_create.add_argument('--description')
    cfg_create.add_argument('--type', choices=['static', 'template', 'builder'])
    cfg_create.add_argument('--author')

    cfg_update = cfg_subparsers.add_parser('update', help='Update configlet')
    cfg_update.add_argument('--name', required=True)
    cfg_update.add_argument('--file', required=True)
    cfg_update.add_argument('--reason')
    cfg_update.add_argument('--author')

    cfg_show = cfg_subparsers.add_parser('show', help='Show configlet')
    cfg_show.add_argument('name')

    cfg_history = cfg_subparsers.add_parser('history', help='Show configlet history')
    cfg_history.add_argument('name')

    # Build commands
    build_parser = subparsers.add_parser('build', help='Build configurations')
    build_parser.add_argument('--device', help='Device variable file')
    build_parser.add_argument('--bulk', help='Bulk device list')
    build_parser.add_argument('--templates', '-t', nargs='+', required=True)
    build_parser.add_argument('--output')

    # Validate commands
    val_parser = subparsers.add_parser('validate', help='Validate configurations')
    val_subparsers = val_parser.add_subparsers(dest='subcommand')

    val_vars = val_subparsers.add_parser('vars', help='Validate variables')
    val_vars.add_argument('file')

    val_config = val_subparsers.add_parser('config', help='Validate config')
    val_config.add_argument('file')

    # Task commands
    task_parser = subparsers.add_parser('task', help='Task management')
    task_subparsers = task_parser.add_subparsers(dest='subcommand')

    task_list = task_subparsers.add_parser('list', help='List tasks')
    task_list.add_argument('--status', choices=['pending', 'in_progress', 'completed', 'failed', 'cancelled'])

    task_show = task_subparsers.add_parser('show', help='Show task')
    task_show.add_argument('task_id', type=int)

    task_create = task_subparsers.add_parser('create', help='Create task')
    task_create.add_argument('--type', required=True, choices=['config_change', 'configlet_assign', 'configlet_remove'])
    task_create.add_argument('--devices', required=True, help='Comma-separated device list')
    task_create.add_argument('--description', required=True)
    task_create.add_argument('--author')

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(1)

    cli = OrchestratorCLI()

    # Route to appropriate handler
    if args.command == 'inventory':
        if args.subcommand == 'list':
            cli.inventory_list(args)
        elif args.subcommand == 'add':
            cli.inventory_add(args)
        elif args.subcommand == 'import':
            cli.inventory_import(args)
        elif args.subcommand == 'export':
            cli.inventory_export(args)
    elif args.command == 'configlet':
        if args.subcommand == 'list':
            cli.configlet_list(args)
        elif args.subcommand == 'create':
            cli.configlet_create(args)
        elif args.subcommand == 'update':
            cli.configlet_update(args)
        elif args.subcommand == 'show':
            cli.configlet_show(args)
        elif args.subcommand == 'history':
            cli.configlet_history(args)
    elif args.command == 'build':
        cli.build_config(args)
    elif args.command == 'validate':
        if args.subcommand == 'vars':
            cli.validate_vars(args)
        elif args.subcommand == 'config':
            cli.validate_config(args)
    elif args.command == 'task':
        if args.subcommand == 'list':
            cli.task_list(args)
        elif args.subcommand == 'show':
            cli.task_show(args)
        elif args.subcommand == 'create':
            cli.task_create(args)


if __name__ == '__main__':
    main()
