#!/usr/bin/env python3
"""
Configuration Validator
Validates device variables and generated configurations
"""

import yaml
import jsonschema
from jsonschema import validate
import sys
from pathlib import Path


class ConfigValidator:
    def __init__(self, schema_dir='schemas'):
        self.schema_dir = Path(schema_dir)

    def load_schema(self, schema_file):
        """Load JSON schema"""
        with open(self.schema_dir / schema_file, 'r') as f:
            return yaml.safe_load(f)

    def validate_device_vars(self, variable_file, schema_file='device-schema.json'):
        """Validate device variables against schema"""
        if not (self.schema_dir / schema_file).exists():
            print(f"Warning: Schema file {schema_file} not found, skipping validation")
            return True

        schema = self.load_schema(schema_file)

        with open(variable_file, 'r') as f:
            variables = yaml.safe_load(f)

        try:
            validate(instance=variables, schema=schema)
            print(f"✓ {variable_file} is valid")
            return True
        except jsonschema.exceptions.ValidationError as e:
            print(f"✗ {variable_file} validation failed:")
            print(f"  {e.message}")
            return False

    def validate_config_syntax(self, config_file):
        """Basic EOS syntax validation"""
        with open(config_file, 'r') as f:
            config = f.read()

        errors = []

        # Basic checks
        lines = config.split('\n')
        for i, line in enumerate(lines, 1):
            line_stripped = line.strip()

            # Check for common syntax errors
            if line_stripped.startswith('!'):
                continue

            # Check indentation for sub-commands
            if line and not line.startswith(' ') and not line.startswith('!'):
                if not self._is_top_level_command(line_stripped):
                    if i > 1 and lines[i-2].strip():
                        # Could be a sub-command without proper context
                        pass

        if errors:
            print(f"✗ Syntax issues in {config_file}:")
            for error in errors:
                print(f"  {error}")
            return False
        else:
            print(f"✓ {config_file} syntax looks good")
            return True

    @staticmethod
    def _is_top_level_command(line):
        """Check if line is a top-level command"""
        top_level = ['hostname', 'interface', 'router', 'vlan', 'ip', 'aaa',
                     'username', 'ntp', 'logging', 'mlag', 'spanning-tree',
                     'vrf', 'management', 'service', 'daemon', 'banner',
                     'no ', 'end', 'exit']
        return any(line.startswith(cmd) for cmd in top_level)


def main():
    import argparse

    parser = argparse.ArgumentParser(description='Validate Arista configurations')
    parser.add_argument('--vars', '-v', help='Validate variable file')
    parser.add_argument('--config', '-c', help='Validate generated config')
    parser.add_argument('--schema-dir', default='schemas', help='Schema directory')

    args = parser.parse_args()

    validator = ConfigValidator(schema_dir=args.schema_dir)

    if args.vars:
        valid = validator.validate_device_vars(args.vars)
        sys.exit(0 if valid else 1)
    elif args.config:
        valid = validator.validate_config_syntax(args.config)
        sys.exit(0 if valid else 1)
    else:
        print("Error: Specify --vars or --config", file=sys.stderr)
        sys.exit(1)


if __name__ == '__main__':
    main()
