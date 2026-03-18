#!/usr/bin/env python3
"""
Check database lock - identify what's holding the database
"""

import subprocess
import sys

print("Checking for processes using custom-cvp.db...")

# On Windows/WSL, check for Python processes
try:
    result = subprocess.run(['ps', 'aux'], capture_output=True, text=True)
    lines = result.stdout.split('\n')
    
    python_procs = [line for line in lines if 'python' in line.lower() and 'custom-cvp' in line]
    
    if python_procs:
        print(f"\nFound {len(python_procs)} Python processes in custom-cvp directory:")
        for proc in python_procs:
            print(f"  {proc}")
    else:
        print("\nNo Python processes found using custom-cvp")
        
except Exception as e:
    print(f"Error checking processes: {e}")

print("\nTo kill all Python processes:")
print("  killall python3")
print("Or on Windows:")
print("  taskkill /F /IM python.exe")
