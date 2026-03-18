#!/usr/bin/env python3
"""
CLI Browser Setup - One-shot script to create tables and parse showcli.txt
Combines migration and parsing into single operation
"""

import sys
import os
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

# Import our modules
from migrations.add_cli_browser import create_cli_browser_tables, verify_migration, backup_database
from core.cli_parser import CLIParser


def main():
    """Main setup function"""
    
    # Paths
    project_root = Path(__file__).parent
    db_path = project_root / 'custom-cvp.db'
    showcli_path = project_root / 'showcli.txt'
    
    print("=" * 70)
    print("CLI Browser Setup")
    print("=" * 70)
    
    # Check files exist
    if not showcli_path.exists():
        print(f"✗ Error: showcli.txt not found at {showcli_path}")
        return False
    
    print(f"✓ Found showcli.txt ({showcli_path.stat().st_size / 1024:.1f} KB)")
    
    # Step 1: Backup database if it exists
    if db_path.exists():
        print(f"\nStep 1: Backing up existing database...")
        backup_path = backup_database(str(db_path))
        if backup_path:
            print(f"✓ Backup created: {Path(backup_path).name}")
    else:
        print(f"\nStep 1: Database doesn't exist yet, will be created")
    
    # Step 2: Create tables
    print(f"\nStep 2: Creating CLI browser tables...")
    try:
        success = create_cli_browser_tables(str(db_path))
        if not success:
            print("✗ Failed to create tables")
            return False
        print("✓ Tables created successfully")
    except Exception as e:
        print(f"✗ Error creating tables: {e}")
        return False
    
    # Step 3: Verify migration
    print(f"\nStep 3: Verifying tables...")
    verify_migration(str(db_path))
    
    # Step 4: Parse and populate
    print(f"\nStep 4: Parsing showcli.txt...")
    try:
        parser = CLIParser(str(db_path))
        parsed_data = parser.parse_file(str(showcli_path))
        
        print(f"\nStep 5: Populating database...")
        success = parser.populate_database(parsed_data)
        
        if not success:
            print("✗ Failed to populate database")
            return False
            
        print("\n" + "=" * 70)
        print("✓ Setup completed successfully!")
        print("=" * 70)
        print(f"  Modes:    {len(parsed_data['modes'])}")
        print(f"  Commands: {len(parsed_data['commands'])}")
        print(f"  Lines:    {parsed_data['total_lines']}")
        print("=" * 70)
        
        return True
        
    except Exception as e:
        print(f"✗ Error during parsing/population: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == '__main__':
    success = main()
    sys.exit(0 if success else 1)
