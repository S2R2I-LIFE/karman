#!/usr/bin/env python3
"""
Import CVP Configlets
Imports configlets from CVP JSON export files into Kármán
"""

import json
import sys
import argparse
from pathlib import Path
from core.configlet import ConfigletManager, Configlet


class CVPConfigletImporter:
    def __init__(self, db_path='custom-cvp.db', configlet_dir='configlets'):
        self.configlet_mgr = ConfigletManager(db_path, configlet_dir)

    def parse_cvp_export(self, json_file):
        """Parse CVP configlet export JSON file"""
        with open(json_file, 'r') as f:
            data = json.load(f)

        configlets = []

        # Parse static configlets
        if 'data' in data and 'configlet' in data['data']:
            for cfg in data['data']['configlet']:
                configlet = {
                    'name': cfg.get('name'),
                    'config': cfg.get('config', ''),
                    'type': cfg.get('type', 'Static'),
                    'description': cfg.get('note', ''),
                    'user': cfg.get('user', 'cvp-import'),
                    'reconciled': cfg.get('reconciled', False),
                    'editable': cfg.get('editable', True)
                }
                configlets.append(configlet)

        # Parse configlet builders
        if 'data' in data and 'configletBuilder' in data['data']:
            for builder in data['data']['configletBuilder']:
                # Extract the Python script
                main_script = ''
                if 'main_script' in builder and 'data' in builder['main_script']:
                    main_script = builder['main_script']['data']

                configlet = {
                    'name': builder.get('name'),
                    'config': main_script,
                    'type': 'Builder',
                    'description': f"ConfigletBuilder: {builder.get('name')}",
                    'user': 'cvp-import',
                    'reconciled': False,
                    'editable': builder.get('editable', True)
                }
                configlets.append(configlet)

        return configlets

    def import_configlet(self, configlet_data, overwrite=False):
        """Import a single configlet"""
        name = configlet_data['name']

        # Check if configlet already exists
        existing = self.configlet_mgr.get_configlet(name)

        if existing and not overwrite:
            print(f"⚠ Skipping {name} (already exists, use --overwrite to replace)")
            return False

        # Create configlet object
        configlet = Configlet(
            name=name,
            config=configlet_data['config'],
            description=configlet_data['description'],
            configlet_type=configlet_data['type'].lower()
        )

        # Import
        if existing and overwrite:
            self.configlet_mgr.update_configlet(
                name,
                configlet_data['config'],
                author='cvp-import',
                reason='Imported from CVP export'
            )
            print(f"✓ Updated: {name}")
        else:
            self.configlet_mgr.create_configlet(configlet, author='cvp-import')
            print(f"✓ Imported: {name}")

        return True

    def import_from_directory(self, cvp_export_dir, overwrite=False, filter_name=None):
        """Import all configlets from CVP export directory"""
        cvp_dir = Path(cvp_export_dir)

        if not cvp_dir.exists():
            print(f"Error: Directory {cvp_export_dir} not found")
            return

        # Find all JSON files in directory and subdirectories
        json_files = list(cvp_dir.rglob('*.json'))

        if not json_files:
            print(f"No JSON files found in {cvp_export_dir}")
            return

        print(f"Found {len(json_files)} JSON file(s)")
        print("=" * 80)

        total_imported = 0
        total_skipped = 0

        for json_file in json_files:
            print(f"\nProcessing: {json_file.name}")
            print("-" * 80)

            try:
                configlets = self.parse_cvp_export(json_file)
                print(f"Found {len(configlets)} configlet(s) in {json_file.name}")

                for cfg_data in configlets:
                    # Apply name filter if specified
                    if filter_name and filter_name.lower() not in cfg_data['name'].lower():
                        continue

                    success = self.import_configlet(cfg_data, overwrite)
                    if success:
                        total_imported += 1
                    else:
                        total_skipped += 1

            except Exception as e:
                print(f"✗ Error processing {json_file}: {e}")

        print("\n" + "=" * 80)
        print(f"Import Summary:")
        print(f"  Imported: {total_imported}")
        print(f"  Skipped:  {total_skipped}")
        print(f"  Total:    {total_imported + total_skipped}")

    def list_cvp_configlets(self, cvp_export_dir):
        """List all configlets in CVP export without importing"""
        cvp_dir = Path(cvp_export_dir)

        if not cvp_dir.exists():
            print(f"Error: Directory {cvp_export_dir} not found")
            return

        json_files = list(cvp_dir.rglob('*.json'))

        if not json_files:
            print(f"No JSON files found in {cvp_export_dir}")
            return

        print(f"CVP Configlets in {cvp_export_dir}")
        print("=" * 80)

        all_configlets = []

        for json_file in json_files:
            try:
                configlets = self.parse_cvp_export(json_file)
                all_configlets.extend(configlets)
            except Exception as e:
                print(f"Error reading {json_file}: {e}")

        # Sort by name
        all_configlets.sort(key=lambda x: x['name'])

        print(f"\nTotal configlets: {len(all_configlets)}\n")

        for cfg in all_configlets:
            config_lines = len(cfg['config'].split('\n'))
            print(f"{cfg['name']:40} | Type: {cfg['type']:10} | Lines: {config_lines:4}")


def main():
    parser = argparse.ArgumentParser(
        description='Import CVP configlets into Kármán',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # List all configlets in CVP export
  python import_cvp_configlets.py --list /path/to/CVP/

  # Import all configlets
  python import_cvp_configlets.py --import /path/to/CVP/

  # Import with overwrite
  python import_cvp_configlets.py --import /path/to/CVP/ --overwrite

  # Import only specific configlets (by name filter)
  python import_cvp_configlets.py --import /path/to/CVP/ --filter "Leaf"
        """
    )

    parser.add_argument('--list', '-l', metavar='DIR',
                        help='List all configlets in CVP export directory')
    parser.add_argument('--import', '-i', metavar='DIR', dest='import_dir',
                        help='Import configlets from CVP export directory')
    parser.add_argument('--overwrite', '-o', action='store_true',
                        help='Overwrite existing configlets')
    parser.add_argument('--filter', '-f', metavar='NAME',
                        help='Only import configlets matching name filter')
    parser.add_argument('--db-path', default='custom-cvp.db',
                        help='Database path (default: custom-cvp.db)')
    parser.add_argument('--configlet-dir', default='configlets',
                        help='Configlet directory (default: configlets)')

    args = parser.parse_args()

    if not args.list and not args.import_dir:
        parser.print_help()
        sys.exit(1)

    importer = CVPConfigletImporter(args.db_path, args.configlet_dir)

    if args.list:
        importer.list_cvp_configlets(args.list)

    if args.import_dir:
        importer.import_from_directory(
            args.import_dir,
            overwrite=args.overwrite,
            filter_name=args.filter
        )


if __name__ == '__main__':
    main()
